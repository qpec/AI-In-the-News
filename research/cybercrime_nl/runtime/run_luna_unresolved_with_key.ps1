[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$Workspace)
$ErrorActionPreference = 'Stop'
$resolutionRepository = Split-Path (Split-Path (Split-Path $PSScriptRoot -Parent) -Parent) -Parent
Add-Type -Path (Join-Path $resolutionRepository 'scripts/windows_key_store.cs')
if (-not [NewsKeyStore]::Exists([NewsKeyStore]::Target)) { throw 'The saved OpenAI key is unavailable.' }
$previousResolutionKey = [Environment]::GetEnvironmentVariable('OPENAI_API_KEY', 'Process')
$resolutionExitCode = 1
Push-Location $resolutionRepository
try {
    [Environment]::SetEnvironmentVariable('OPENAI_API_KEY', [NewsKeyStore]::Load([NewsKeyStore]::Target), 'Process')
    & uv run --offline --frozen python -u research/cybercrime_nl/runtime/luna_unresolved_run.py run --workspace $Workspace --allow-paid-execution
    $resolutionExitCode = $LASTEXITCODE
} finally {
    [Environment]::SetEnvironmentVariable('OPENAI_API_KEY', $previousResolutionKey, 'Process')
    $previousResolutionKey = $null
    Pop-Location
}
exit $resolutionExitCode
