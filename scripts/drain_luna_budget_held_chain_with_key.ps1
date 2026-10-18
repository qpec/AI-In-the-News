# Post-stop existing-job GETs only; no inference authorization or key output.
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Plan,
    [Parameter(Mandatory = $true)][string]$StopResultRef,
    [Parameter(Mandatory = $true)][string]$HeldAckRef,
    [string]$HeldRunRef,
    [string]$HeldFinishRef,
    [ValidateRange(0, 86400)][int]$MaxWaitSeconds = 1800,
    [switch]$AllowExistingJobReads
)
$ErrorActionPreference = 'Stop'
if (-not $AllowExistingJobReads) { throw 'Explicit -AllowExistingJobReads is required; new inference is forbidden.' }
Add-Type -Path (Join-Path $PSScriptRoot 'windows_key_store.cs')
if (-not [NewsKeyStore]::Exists([NewsKeyStore]::Target)) { throw 'The saved OpenAI key is unavailable.' }
Add-Type -Namespace LunaHeldChainDiagnosticPower -Name SleepGuard -MemberDefinition '[System.Runtime.InteropServices.DllImport("kernel32.dll", SetLastError = true)] public static extern uint SetThreadExecutionState(uint flags);'
$heldDiagnosticArguments = @((Join-Path $PSScriptRoot 'drain_luna_budget_held_chain.py'), '--plan', $Plan,
    '--stop-result-ref', $StopResultRef, '--held-ack-ref', $HeldAckRef,
    '--max-wait-seconds', $MaxWaitSeconds, '--allow-existing-job-reads')
if ($HeldRunRef) { $heldDiagnosticArguments += @('--held-run-ref', $HeldRunRef) }
if ($HeldFinishRef) { $heldDiagnosticArguments += @('--held-finish-ref', $HeldFinishRef) }
$previousHeldDiagnosticKey = [Environment]::GetEnvironmentVariable('OPENAI_API_KEY', 'Process')
$heldDiagnosticExitCode = 1
$heldDiagnosticPowerGuard = $false
Push-Location (Split-Path $PSScriptRoot -Parent)
try {
    if ([LunaHeldChainDiagnosticPower.SleepGuard]::SetThreadExecutionState([uint32]2147483649) -eq 0) {
        throw 'The temporary idle-sleep guard could not be enabled.'
    }
    $heldDiagnosticPowerGuard = $true
    'Temporary idle-sleep guard active for post-stop GET-only diagnosis.'
    [Environment]::SetEnvironmentVariable('OPENAI_API_KEY', [NewsKeyStore]::Load([NewsKeyStore]::Target), 'Process')
    & .venv/Scripts/python.exe @heldDiagnosticArguments
    $heldDiagnosticExitCode = $LASTEXITCODE
} finally {
    [Environment]::SetEnvironmentVariable('OPENAI_API_KEY', $previousHeldDiagnosticKey, 'Process')
    $previousHeldDiagnosticKey = $null
    if ($heldDiagnosticPowerGuard) {
        [LunaHeldChainDiagnosticPower.SleepGuard]::SetThreadExecutionState([uint32]2147483648) | Out-Null
        'Temporary idle-sleep guard released.'
    }
    Pop-Location
}
exit $heldDiagnosticExitCode
