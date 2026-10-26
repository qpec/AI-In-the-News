[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$Workspace)
$ErrorActionPreference = 'Stop'
Add-Type -Path (Join-Path $PSScriptRoot 'windows_key_store.cs')
if (-not [NewsKeyStore]::Exists([NewsKeyStore]::Target)) { throw 'The saved OpenAI key is unavailable.' }
$previousIncidentResilientKey = [Environment]::GetEnvironmentVariable('OPENAI_API_KEY', 'Process')
$incidentResilientExitCode = 1
Push-Location (Split-Path $PSScriptRoot -Parent)
try {
    [Environment]::SetEnvironmentVariable('OPENAI_API_KEY', [NewsKeyStore]::Load([NewsKeyStore]::Target), 'Process')
    & uv run --offline --frozen python -u workbench/run_luna_decisions_incident_resilient.py --workspace $Workspace --allow-paid-execution
    $incidentResilientExitCode = $LASTEXITCODE
} finally {
    [Environment]::SetEnvironmentVariable('OPENAI_API_KEY', $previousIncidentResilientKey, 'Process')
    $previousIncidentResilientKey = $null
    Pop-Location
}
exit $incidentResilientExitCode
