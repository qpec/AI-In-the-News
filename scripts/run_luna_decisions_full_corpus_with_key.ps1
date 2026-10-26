[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$Workspace)
$ErrorActionPreference = 'Stop'
Add-Type -Path (Join-Path $PSScriptRoot 'windows_key_store.cs')
if (-not [NewsKeyStore]::Exists([NewsKeyStore]::Target)) { throw 'The saved OpenAI key is unavailable.' }
$previousDecisionsKey = [Environment]::GetEnvironmentVariable('OPENAI_API_KEY', 'Process')
$decisionsExitCode = 1
Push-Location (Split-Path $PSScriptRoot -Parent)
try {
    [Environment]::SetEnvironmentVariable('OPENAI_API_KEY', [NewsKeyStore]::Load([NewsKeyStore]::Target), 'Process')
    & uv run --offline --frozen python -u workbench/run_luna_decisions_full_corpus_paced.py --workspace $Workspace --allow-paid-execution
    $decisionsExitCode = $LASTEXITCODE
} finally {
    [Environment]::SetEnvironmentVariable('OPENAI_API_KEY', $previousDecisionsKey, 'Process')
    $previousDecisionsKey = $null
    Pop-Location
}
exit $decisionsExitCode
