# Existing-job GET-only drain. Never grants permission for new inference.
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Plan,
    [Parameter(Mandatory = $true)][string]$StopResultRef,
    [Parameter(Mandatory = $true)][string]$PriorAckRef,
    [ValidateRange(0, 86400)][int]$MaxWaitSeconds = 1800,
    [switch]$AllowExistingJobReads
)
$ErrorActionPreference = 'Stop'
if (-not $AllowExistingJobReads) { throw 'Explicit -AllowExistingJobReads is required; new inference is forbidden.' }
Add-Type -Path (Join-Path $PSScriptRoot 'windows_key_store.cs')
if (-not [NewsKeyStore]::Exists([NewsKeyStore]::Target)) { throw 'The saved OpenAI key is unavailable.' }
$chainDrainArguments = @((Join-Path $PSScriptRoot 'drain_luna_budget_recovery_chain.py'), '--plan', $Plan,
    '--stop-result-ref', $StopResultRef, '--prior-ack-ref', $PriorAckRef,
    '--max-wait-seconds', $MaxWaitSeconds.ToString(), '--allow-existing-job-reads')
$previousChainDrainKey = [Environment]::GetEnvironmentVariable('OPENAI_API_KEY', 'Process')
$chainDrainExitCode = 1
Push-Location (Split-Path $PSScriptRoot -Parent)
try {
    [Environment]::SetEnvironmentVariable('OPENAI_API_KEY', [NewsKeyStore]::Load([NewsKeyStore]::Target), 'Process')
    & .venv/Scripts/python.exe @chainDrainArguments
    $chainDrainExitCode = $LASTEXITCODE
} finally {
    [Environment]::SetEnvironmentVariable('OPENAI_API_KEY', $previousChainDrainKey, 'Process')
    $previousChainDrainKey = $null
    Pop-Location
}
exit $chainDrainExitCode
