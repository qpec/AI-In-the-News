[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$Workspace)
$ErrorActionPreference = 'Stop'
$recallRepository = Split-Path (Split-Path (Split-Path $PSScriptRoot -Parent) -Parent) -Parent
Add-Type -Path (Join-Path $recallRepository 'scripts/windows_key_store.cs')
if (-not [NewsKeyStore]::Exists([NewsKeyStore]::Target)) { throw 'The saved OpenAI key is unavailable.' }
$previousRecallKey = [Environment]::GetEnvironmentVariable('OPENAI_API_KEY', 'Process')
$recallExitCode = 1
Push-Location $recallRepository
try {
    [Environment]::SetEnvironmentVariable('OPENAI_API_KEY', [NewsKeyStore]::Load([NewsKeyStore]::Target), 'Process')
    & uv run --offline --frozen python -u research/cybercrime_nl/runtime/luna_recall_run_v2.py run --workspace $Workspace --allow-paid-execution
    $recallExitCode = $LASTEXITCODE
} finally {
    [Environment]::SetEnvironmentVariable('OPENAI_API_KEY', $previousRecallKey, 'Process')
    $previousRecallKey = $null
    Pop-Location
}
exit $recallExitCode
