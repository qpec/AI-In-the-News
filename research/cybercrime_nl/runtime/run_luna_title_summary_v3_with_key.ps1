[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$Workspace)
$ErrorActionPreference = 'Stop'
$titleSummaryRepository = Split-Path (Split-Path (Split-Path $PSScriptRoot -Parent) -Parent) -Parent
Add-Type -Path (Join-Path $titleSummaryRepository 'scripts/windows_key_store.cs')
if (-not [NewsKeyStore]::Exists([NewsKeyStore]::Target)) { throw 'The saved OpenAI key is unavailable.' }
$previousTitleSummaryKey = [Environment]::GetEnvironmentVariable('OPENAI_API_KEY', 'Process')
$titleSummaryExitCode = 1
Push-Location $titleSummaryRepository
try {
    [Environment]::SetEnvironmentVariable('OPENAI_API_KEY', [NewsKeyStore]::Load([NewsKeyStore]::Target), 'Process')
    & uv run --offline --frozen python -u research/cybercrime_nl/runtime/luna_title_summary_run_v3.py run --workspace $Workspace --allow-paid-execution
    $titleSummaryExitCode = $LASTEXITCODE
} finally {
    [Environment]::SetEnvironmentVariable('OPENAI_API_KEY', $previousTitleSummaryKey, 'Process')
    $previousTitleSummaryKey = $null
    Pop-Location
}
exit $titleSummaryExitCode
