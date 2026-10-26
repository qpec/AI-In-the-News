[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$Workspace
)
$ErrorActionPreference = 'Stop'
$dossierRepository = Split-Path (Split-Path (Split-Path $PSScriptRoot -Parent) -Parent) -Parent
Add-Type -Path (Join-Path $dossierRepository 'scripts/windows_key_store.cs')
if (-not [NewsKeyStore]::Exists([NewsKeyStore]::Target)) { throw 'The saved OpenAI key is unavailable.' }
$previousDossierKey = [Environment]::GetEnvironmentVariable('OPENAI_API_KEY', 'Process')
$dossierExitCode = 1
Push-Location $dossierRepository
try {
    [Environment]::SetEnvironmentVariable('OPENAI_API_KEY', [NewsKeyStore]::Load([NewsKeyStore]::Target), 'Process')
    & uv run --offline --frozen python -u research/cybercrime_nl/runtime/run_summary_fidelity_diagnostic_v2.py run --workspace $Workspace --allow-paid-execution
    $dossierExitCode = $LASTEXITCODE
} finally {
    [Environment]::SetEnvironmentVariable('OPENAI_API_KEY', $previousDossierKey, 'Process')
    $previousDossierKey = $null
    Pop-Location
}
exit $dossierExitCode
