[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$Workspace)
$ErrorActionPreference = 'Stop'
$snippetRepository = Split-Path (Split-Path (Split-Path $PSScriptRoot -Parent) -Parent) -Parent
Add-Type -Path (Join-Path $snippetRepository 'scripts/windows_key_store.cs')
if (-not [NewsKeyStore]::Exists([NewsKeyStore]::Target)) { throw 'The saved OpenAI key is unavailable.' }
$previousSnippetKey = [Environment]::GetEnvironmentVariable('OPENAI_API_KEY', 'Process')
$snippetExitCode = 1
Push-Location $snippetRepository
try {
    [Environment]::SetEnvironmentVariable('OPENAI_API_KEY', [NewsKeyStore]::Load([NewsKeyStore]::Target), 'Process')
    & uv run --offline --frozen python -u research/cybercrime_nl/runtime/luna_snippet_run_v2.py run --workspace $Workspace --allow-paid-execution
    $snippetExitCode = $LASTEXITCODE
} finally {
    [Environment]::SetEnvironmentVariable('OPENAI_API_KEY', $previousSnippetKey, 'Process')
    $previousSnippetKey = $null
    Pop-Location
}
exit $snippetExitCode
