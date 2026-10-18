# Saved-key launcher with a temporary idle-sleep guard for its child lifetime.
[CmdletBinding(DefaultParameterSetName = 'ExistingAck')]
param(
    [Parameter(Mandatory = $true)][string]$Plan,
    [Parameter(Mandatory = $true, ParameterSetName = 'ExistingAck')][string]$AckRef,
    [Parameter(Mandatory = $true, ParameterSetName = 'Diagnose')][string]$DiagnosticRef,
    [Parameter(Mandatory = $true, ParameterSetName = 'Diagnose')][string]$PriorAckRef,
    [Parameter(Mandatory = $true, ParameterSetName = 'Diagnose')][string]$StopResultRef,
    [Parameter(Mandatory = $true, ParameterSetName = 'Diagnose')][string]$HeldAssessmentId,
    [Parameter(Mandatory = $true, ParameterSetName = 'Diagnose')][string]$SettledAssessmentId,
    [switch]$AllowPaidExecution
)
$ErrorActionPreference = 'Stop'
if (-not $AllowPaidExecution) { throw 'Explicit -AllowPaidExecution is required.' }
Add-Type -Path (Join-Path $PSScriptRoot 'windows_key_store.cs')
if (-not [NewsKeyStore]::Exists([NewsKeyStore]::Target)) { throw 'The saved OpenAI key is unavailable.' }
Add-Type -Namespace LunaBatchHeldCostPower -Name SleepGuard -MemberDefinition '[System.Runtime.InteropServices.DllImport("kernel32.dll", SetLastError = true)] public static extern uint SetThreadExecutionState(uint flags);'
$recoveryArguments = @((Join-Path $PSScriptRoot 'run_luna_budget_held_cost.py'), '--plan', $Plan, '--allow-paid-execution')
if ($PSCmdlet.ParameterSetName -eq 'ExistingAck') {
    $recoveryArguments += @('--ack-ref', $AckRef)
} else {
    $recoveryArguments += @('--diagnostic-ref', $DiagnosticRef, '--prior-ack-ref', $PriorAckRef, '--stop-result-ref', $StopResultRef)
    $recoveryArguments += @('--held-assessment-id', $HeldAssessmentId, '--settled-assessment-id', $SettledAssessmentId)
}
$previousRecoveryKey = [Environment]::GetEnvironmentVariable('OPENAI_API_KEY', 'Process')
$recoveryExitCode = 1
$recoveryPowerGuard = $false
Push-Location (Split-Path $PSScriptRoot -Parent)
try {
    if ([LunaBatchHeldCostPower.SleepGuard]::SetThreadExecutionState([uint32]2147483649) -eq 0) {
        throw 'The temporary idle-sleep guard could not be enabled.'
    }
    $recoveryPowerGuard = $true
    'Temporary idle-sleep guard active for this recovery controller; display sleep remains allowed.'
    [Environment]::SetEnvironmentVariable('OPENAI_API_KEY', [NewsKeyStore]::Load([NewsKeyStore]::Target), 'Process')
    & .venv/Scripts/python.exe @recoveryArguments
    $recoveryExitCode = $LASTEXITCODE
} finally {
    [Environment]::SetEnvironmentVariable('OPENAI_API_KEY', $previousRecoveryKey, 'Process')
    $previousRecoveryKey = $null
    if ($recoveryPowerGuard) {
        [LunaBatchHeldCostPower.SleepGuard]::SetThreadExecutionState([uint32]2147483648) | Out-Null
        'Temporary idle-sleep guard released.'
    }
    Pop-Location
}
exit $recoveryExitCode
