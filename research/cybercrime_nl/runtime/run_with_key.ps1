[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$Workspace,
    [ValidateSet('operational','run')][string]$Action = 'operational'
)
$ErrorActionPreference = 'Stop'
$cyberRepository = Split-Path (Split-Path (Split-Path $PSScriptRoot -Parent) -Parent) -Parent
Add-Type -Path (Join-Path $cyberRepository 'scripts/windows_key_store.cs')
if (-not [NewsKeyStore]::Exists([NewsKeyStore]::Target)) { throw 'The saved OpenAI key is unavailable.' }
$previousCyberScreenKey = [Environment]::GetEnvironmentVariable('OPENAI_API_KEY', 'Process')
$cyberScreenExitCode = 1
Push-Location $cyberRepository
try {
    [Environment]::SetEnvironmentVariable('OPENAI_API_KEY', [NewsKeyStore]::Load([NewsKeyStore]::Target), 'Process')
    & uv run --offline --frozen python -u research/cybercrime_nl/runtime/run_screening.py $Action --workspace $Workspace --allow-paid-execution
    $cyberScreenExitCode = $LASTEXITCODE
} finally {
    [Environment]::SetEnvironmentVariable('OPENAI_API_KEY', $previousCyberScreenKey, 'Process')
    $previousCyberScreenKey = $null
    Pop-Location
}
exit $cyberScreenExitCode
