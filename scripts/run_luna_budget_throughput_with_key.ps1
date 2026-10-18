# Same authorized Batch budget, saved key, and temporary idle-sleep prevention.
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Plan,
    [string]$PolicyRef,
    [string]$DiagnosticRef,
    [string]$PriorAckRef,
    [string]$StopResultRef,
    [string[]]$AssessmentIds,
    [switch]$AllowPaidExecution
)
$ErrorActionPreference = 'Stop'
if (-not $AllowPaidExecution) { throw 'Explicit -AllowPaidExecution is required.' }
if ($PolicyRef) {
    if ($DiagnosticRef -or $PriorAckRef -or $StopResultRef -or $AssessmentIds) { throw 'Use one policy reference or exact registration inputs.' }
} elseif (-not $DiagnosticRef -or -not $PriorAckRef -or -not $StopResultRef -or -not $AssessmentIds) {
    throw 'Exact diagnostic, prior acknowledgment, stopped result and assessment IDs are required.'
}
Add-Type -Path (Join-Path $PSScriptRoot 'windows_key_store.cs')
if (-not [NewsKeyStore]::Exists([NewsKeyStore]::Target)) { throw 'The saved OpenAI key is unavailable.' }
Add-Type -Namespace LunaThroughputPower -Name SleepGuard -MemberDefinition '[System.Runtime.InteropServices.DllImport("kernel32.dll", SetLastError = true)] public static extern uint SetThreadExecutionState(uint flags);'
$throughputArguments = @((Join-Path $PSScriptRoot 'run_luna_budget_throughput.py'), '--plan', $Plan, '--allow-paid-execution')
if ($PolicyRef) {
    $throughputArguments += @('--policy-ref', $PolicyRef)
} else {
    $throughputArguments += @('--diagnostic-ref', $DiagnosticRef, '--prior-ack-ref', $PriorAckRef,
        '--stop-result-ref', $StopResultRef, '--assessment-ids') + $AssessmentIds
}
$previousThroughputKey = [Environment]::GetEnvironmentVariable('OPENAI_API_KEY', 'Process')
$throughputExitCode = 1
$throughputPowerGuard = $false
Push-Location (Split-Path $PSScriptRoot -Parent)
try {
    if ([LunaThroughputPower.SleepGuard]::SetThreadExecutionState([uint32]2147483649) -eq 0) {
        throw 'The temporary idle-sleep guard could not be enabled.'
    }
    $throughputPowerGuard = $true
    'Temporary idle-sleep guard active for the bounded throughput controller.'
    [Environment]::SetEnvironmentVariable('OPENAI_API_KEY', [NewsKeyStore]::Load([NewsKeyStore]::Target), 'Process')
    & .venv/Scripts/python.exe @throughputArguments
    $throughputExitCode = $LASTEXITCODE
} finally {
    [Environment]::SetEnvironmentVariable('OPENAI_API_KEY', $previousThroughputKey, 'Process')
    $previousThroughputKey = $null
    if ($throughputPowerGuard) {
        [LunaThroughputPower.SleepGuard]::SetThreadExecutionState([uint32]2147483648) | Out-Null
        'Temporary idle-sleep guard released.'
    }
    Pop-Location
}
exit $throughputExitCode
