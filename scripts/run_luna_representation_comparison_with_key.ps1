[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$Workspace,
    [Parameter(Mandatory=$true)][ValidateSet('development','test')][string]$Split
)
$ErrorActionPreference = 'Stop'
Add-Type -Path (Join-Path $PSScriptRoot 'windows_key_store.cs')
if (-not [NewsKeyStore]::Exists([NewsKeyStore]::Target)) { throw 'The saved OpenAI key is unavailable.' }
$previousComparisonKey = [Environment]::GetEnvironmentVariable('OPENAI_API_KEY', 'Process')
$comparisonExitCode = 1
Push-Location (Split-Path $PSScriptRoot -Parent)
try {
    [Environment]::SetEnvironmentVariable('OPENAI_API_KEY', [NewsKeyStore]::Load([NewsKeyStore]::Target), 'Process')
    & .venv/Scripts/python.exe -u workbench/run_luna_representation_comparison.py run --workspace $Workspace --split $Split --allow-paid-execution
    $comparisonExitCode = $LASTEXITCODE
} finally {
    [Environment]::SetEnvironmentVariable('OPENAI_API_KEY', $previousComparisonKey, 'Process')
    $previousComparisonKey = $null
    Pop-Location
}
exit $comparisonExitCode
