# Post-stop existing-job GETs only; never grants new inference permission.
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Plan,
    [Parameter(Mandatory = $true)][string]$StopResultRef,
    [Parameter(Mandatory = $true)][string]$PolicyRef,
    [Parameter(Mandatory = $true)][string]$MigrationRef,
    [ValidateRange(0, 86400)][int]$MaxWaitSeconds = 1800,
    [switch]$AllowExistingJobReads
)
$ErrorActionPreference = 'Stop'
if (-not $AllowExistingJobReads) { throw 'Explicit -AllowExistingJobReads is required; new inference is forbidden.' }
Add-Type -Path (Join-Path $PSScriptRoot 'windows_key_store.cs')
if (-not [NewsKeyStore]::Exists([NewsKeyStore]::Target)) { throw 'The saved OpenAI key is unavailable.' }
Add-Type -Namespace LunaFillDiagnosticPower -Name SleepGuard -MemberDefinition '[System.Runtime.InteropServices.DllImport("kernel32.dll", SetLastError = true)] public static extern uint SetThreadExecutionState(uint flags);'
$throughputDrainArguments = @((Join-Path $PSScriptRoot 'drain_luna_budget_fill.py'), '--plan', $Plan,
    '--stop-result-ref', $StopResultRef, '--policy-ref', $PolicyRef, '--migration-ref', $MigrationRef,
    '--max-wait-seconds', $MaxWaitSeconds, '--allow-existing-job-reads')
$previousThroughputDrainKey = [Environment]::GetEnvironmentVariable('OPENAI_API_KEY', 'Process')
$throughputDrainExitCode = 1
$throughputDrainPowerGuard = $false
Push-Location (Split-Path $PSScriptRoot -Parent)
try {
    if ([LunaFillDiagnosticPower.SleepGuard]::SetThreadExecutionState([uint32]2147483649) -eq 0) {
        throw 'The temporary idle-sleep guard could not be enabled.'
    }
    $throughputDrainPowerGuard = $true
    'Temporary idle-sleep guard active for post-stop GET-only diagnosis.'
    [Environment]::SetEnvironmentVariable('OPENAI_API_KEY', [NewsKeyStore]::Load([NewsKeyStore]::Target), 'Process')
    & .venv/Scripts/python.exe @throughputDrainArguments
    $throughputDrainExitCode = $LASTEXITCODE
} finally {
    [Environment]::SetEnvironmentVariable('OPENAI_API_KEY', $previousThroughputDrainKey, 'Process')
    $previousThroughputDrainKey = $null
    if ($throughputDrainPowerGuard) {
        [LunaFillDiagnosticPower.SleepGuard]::SetThreadExecutionState([uint32]2147483648) | Out-Null
        'Temporary idle-sleep guard released.'
    }
    Pop-Location
}
exit $throughputDrainExitCode
