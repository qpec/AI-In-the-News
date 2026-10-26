[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$Workspace)
$ErrorActionPreference = 'Stop'
$auditRepository = Split-Path (Split-Path (Split-Path $PSScriptRoot -Parent) -Parent) -Parent
Add-Type -Path (Join-Path $auditRepository 'scripts/windows_key_store.cs')
if (-not [NewsKeyStore]::Exists([NewsKeyStore]::Target)) { throw 'The saved OpenAI key is unavailable.' }
$previousAuditKey = [Environment]::GetEnvironmentVariable('OPENAI_API_KEY', 'Process')
$auditExitCode = 1
Push-Location $auditRepository
try {
    [Environment]::SetEnvironmentVariable('OPENAI_API_KEY', [NewsKeyStore]::Load([NewsKeyStore]::Target), 'Process')
    & uv run --offline --frozen python -u research/cybercrime_nl/runtime/luna_unresolved_audit.py run --workspace $Workspace --allow-paid-execution
    $auditExitCode = $LASTEXITCODE
} finally {
    [Environment]::SetEnvironmentVariable('OPENAI_API_KEY', $previousAuditKey, 'Process')
    $previousAuditKey = $null
    Pop-Location
}
exit $auditExitCode
