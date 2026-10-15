# Scope the stored API credential to the query embedding; Codex receives no API key.
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$InputPath,
    [Parameter(Mandatory = $true)][string]$Versions,
    [Parameter(Mandatory = $true)][string]$OutputPath,
    [switch]$AllowPaidExecution,
    [string]$Workspace
)
$ErrorActionPreference = 'Stop'
if (-not $AllowPaidExecution) { throw 'Explicit -AllowPaidExecution and a concrete run approval are required.' }
Add-Type -Path (Join-Path $PSScriptRoot 'windows_key_store.cs')
if (-not [NewsKeyStore]::Exists([NewsKeyStore]::Target)) { throw 'The application credential is unavailable.' }
$previous = [Environment]::GetEnvironmentVariable('OPENAI_API_KEY', 'Process')
$exitCode = 1
Push-Location (Split-Path $PSScriptRoot -Parent)
try {
    [Environment]::SetEnvironmentVariable('OPENAI_API_KEY', [NewsKeyStore]::Load([NewsKeyStore]::Target), 'Process')
    $arguments = @('run', '--frozen', 'python', (Join-Path $PSScriptRoot 'run_rag_query.py'),
        '--input', $InputPath, '--versions', $Versions, '--output', $OutputPath, '--allow-paid-execution')
    if ($Workspace) { $arguments += @('--workspace', $Workspace) }
    & uv @arguments
    $exitCode = $LASTEXITCODE
} finally {
    [Environment]::SetEnvironmentVariable('OPENAI_API_KEY', $previous, 'Process')
    $previous = $null
    Pop-Location
}
exit $exitCode
