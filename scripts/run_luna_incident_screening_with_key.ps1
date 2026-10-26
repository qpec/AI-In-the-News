[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$Workspace)
$ErrorActionPreference = 'Stop'
Add-Type -Path (Join-Path $PSScriptRoot 'windows_key_store.cs')
if (-not [NewsKeyStore]::Exists([NewsKeyStore]::Target)) { throw 'The saved OpenAI key is unavailable.' }
$previousScreeningKey = [Environment]::GetEnvironmentVariable('OPENAI_API_KEY', 'Process')
$screeningExitCode = 1
Push-Location (Split-Path $PSScriptRoot -Parent)
try {
    [Environment]::SetEnvironmentVariable('OPENAI_API_KEY', [NewsKeyStore]::Load([NewsKeyStore]::Target), 'Process')
    & uv run --offline --frozen python -u workbench/run_luna_incident_screening.py run --workspace $Workspace --allow-paid-execution
    $screeningExitCode = $LASTEXITCODE
} finally {
    [Environment]::SetEnvironmentVariable('OPENAI_API_KEY', $previousScreeningKey, 'Process')
    $previousScreeningKey = $null
    Pop-Location
}
exit $screeningExitCode
