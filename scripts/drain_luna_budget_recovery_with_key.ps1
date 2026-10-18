# Existing-job GET-only drain; saved credentials remain process-local.
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
if (-not $AllowExistingJobReads) { throw 'Explicit -AllowExistingJobReads is required; new inference is forbidden.' }
Add-Type -Path (Join-Path $PSScriptRoot 'windows_key_store.cs')
if (-not [NewsKeyStore]::Exists([NewsKeyStore]::Target)) { throw 'The saved OpenAI key is unavailable.' }
Add-Type -Namespace LunaBatchDrainPower -Name SleepGuard -MemberDefinition '[System.Runtime.InteropServices.DllImport("kernel32.dll", SetLastError = true)] public static extern uint SetThreadExecutionState(uint flags);'
$drainArguments = @((Join-Path $PSScriptRoot 'drain_luna_budget_recovery.py'), '--plan', $Plan,
    '--stop-result-ref', $StopResultRef, '--prior-ack-ref', $PriorAckRef,
    '--phase-continuation-ref', $PhaseContinuationRef, '--max-wait-seconds', $MaxWaitSeconds,
    '--allow-existing-job-reads')
$previousDrainKey = [Environment]::GetEnvironmentVariable('OPENAI_API_KEY', 'Process')
$drainExitCode = 1
$drainPowerGuard = $false
Push-Location (Split-Path $PSScriptRoot -Parent)
try {
    if ([LunaBatchDrainPower.SleepGuard]::SetThreadExecutionState([uint32]2147483649) -eq 0) {
        throw 'The temporary idle-sleep guard could not be enabled.'
    }
    $drainPowerGuard = $true
    'Temporary idle-sleep guard active for existing-job drain; display sleep remains allowed.'
    [Environment]::SetEnvironmentVariable('OPENAI_API_KEY', [NewsKeyStore]::Load([NewsKeyStore]::Target), 'Process')
    & .venv/Scripts/python.exe @drainArguments
    $drainExitCode = $LASTEXITCODE
} finally {
    [Environment]::SetEnvironmentVariable('OPENAI_API_KEY', $previousDrainKey, 'Process')
    $previousDrainKey = $null
    if ($drainPowerGuard) {
        [LunaBatchDrainPower.SleepGuard]::SetThreadExecutionState([uint32]2147483648) | Out-Null
        'Temporary idle-sleep guard released.'
    }
    Pop-Location
}
exit $drainExitCode
