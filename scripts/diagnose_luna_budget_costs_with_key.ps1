# GET-only cost diagnostic; no inference admission or credential output.
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Plan,
    [Parameter(Mandatory = $true)][string]$StopResultRef,
    [Parameter(Mandatory = $true)][string]$PriorAckRef,
    [Parameter(Mandatory = $true)][string]$PhaseContinuationRef,
    [ValidateRange(0, 86400)][int]$MaxWaitSeconds = 1800,
    [switch]$AllowExistingJobReads
)
$ErrorActionPreference = 'Stop'
if (-not $AllowExistingJobReads) { throw 'Explicit -AllowExistingJobReads is required; inference continuation is forbidden.' }
Add-Type -Path (Join-Path $PSScriptRoot 'windows_key_store.cs')
if (-not [NewsKeyStore]::Exists([NewsKeyStore]::Target)) { throw 'The saved OpenAI key is unavailable.' }
Add-Type -Namespace LunaBatchCostDiagnosticPower -Name SleepGuard -MemberDefinition '[System.Runtime.InteropServices.DllImport("kernel32.dll", SetLastError = true)] public static extern uint SetThreadExecutionState(uint flags);'
$diagnosticArguments = @((Join-Path $PSScriptRoot 'diagnose_luna_budget_costs.py'), '--plan', $Plan,
    '--stop-result-ref', $StopResultRef, '--prior-ack-ref', $PriorAckRef,
    '--phase-continuation-ref', $PhaseContinuationRef, '--max-wait-seconds', $MaxWaitSeconds,
    '--allow-existing-job-reads')
$previousDiagnosticKey = [Environment]::GetEnvironmentVariable('OPENAI_API_KEY', 'Process')
$diagnosticExitCode = 1
$diagnosticPowerGuard = $false
Push-Location (Split-Path $PSScriptRoot -Parent)
try {
    if ([LunaBatchCostDiagnosticPower.SleepGuard]::SetThreadExecutionState([uint32]2147483649) -eq 0) {
        throw 'The temporary idle-sleep guard could not be enabled.'
    }
    $diagnosticPowerGuard = $true
    'Temporary idle-sleep guard active for GET-only cost diagnosis; display sleep remains allowed.'
    [Environment]::SetEnvironmentVariable('OPENAI_API_KEY', [NewsKeyStore]::Load([NewsKeyStore]::Target), 'Process')
    & .venv/Scripts/python.exe @diagnosticArguments
    $diagnosticExitCode = $LASTEXITCODE
} finally {
    [Environment]::SetEnvironmentVariable('OPENAI_API_KEY', $previousDiagnosticKey, 'Process')
    $previousDiagnosticKey = $null
    if ($diagnosticPowerGuard) {
        [LunaBatchCostDiagnosticPower.SleepGuard]::SetThreadExecutionState([uint32]2147483648) | Out-Null
        'Temporary idle-sleep guard released.'
    }
    Pop-Location
}
exit $diagnosticExitCode
