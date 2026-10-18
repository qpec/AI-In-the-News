# Same authorized Batch budget, saved key, and temporary idle-sleep prevention.
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Plan,
    [Parameter(Mandatory = $true)][string]$PolicyRef,
    [string]$MigrationRef,
    [string]$HandoffRef,
    [string]$HandoffWorkspace,
    [switch]$AllowPaidExecution
)
$ErrorActionPreference = 'Stop'
if (-not $AllowPaidExecution) { throw 'Explicit -AllowPaidExecution is required.' }
if ($MigrationRef) {
    if ($HandoffRef -or $HandoffWorkspace) { throw 'Use one migration reference or exact handoff inputs.' }
} elseif (-not $HandoffRef -or -not $HandoffWorkspace) {
    throw 'Exact handoff reference and metadata workspace are required.'
}
Add-Type -Path (Join-Path $PSScriptRoot 'windows_key_store.cs')
if (-not [NewsKeyStore]::Exists([NewsKeyStore]::Target)) { throw 'The saved OpenAI key is unavailable.' }
Add-Type -Namespace LunaFillPower -Name SleepGuard -MemberDefinition '[System.Runtime.InteropServices.DllImport("kernel32.dll", SetLastError = true)] public static extern uint SetThreadExecutionState(uint flags);'
$throughputArguments = @((Join-Path $PSScriptRoot 'run_luna_budget_fill.py'), '--plan', $Plan, '--allow-paid-execution')
$throughputArguments += @('--policy-ref', $PolicyRef)
if ($MigrationRef) {
    $throughputArguments += @('--migration-ref', $MigrationRef)
} else {
    $throughputArguments += @('--handoff-ref', $HandoffRef, '--handoff-workspace', $HandoffWorkspace)
}
$previousThroughputKey = [Environment]::GetEnvironmentVariable('OPENAI_API_KEY', 'Process')
$throughputExitCode = 1
$throughputPowerGuard = $false
Push-Location (Split-Path $PSScriptRoot -Parent)
try {
    if ([LunaFillPower.SleepGuard]::SetThreadExecutionState([uint32]2147483649) -eq 0) {
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
        [LunaFillPower.SleepGuard]::SetThreadExecutionState([uint32]2147483648) | Out-Null
        'Temporary idle-sleep guard released.'
    }
    Pop-Location
}
exit $throughputExitCode
