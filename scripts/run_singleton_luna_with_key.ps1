# Inject the saved credential into this bounded, plan-authorized API process only.
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Workspace,
    [Parameter(Mandatory = $true)][string]$Plan,
    [switch]$AllowPaidExecution
)
$ErrorActionPreference = 'Stop'
if (-not $AllowPaidExecution) { throw 'Explicit -AllowPaidExecution is required.' }
Add-Type -Path (Join-Path $PSScriptRoot 'windows_key_store.cs')
if (-not [NewsKeyStore]::Exists([NewsKeyStore]::Target)) { throw 'The saved OpenAI key is unavailable.' }
$previous = [Environment]::GetEnvironmentVariable('OPENAI_API_KEY', 'Process')
$exitCode = 1
Push-Location (Split-Path $PSScriptRoot -Parent)
try {
    [Environment]::SetEnvironmentVariable('OPENAI_API_KEY', [NewsKeyStore]::Load([NewsKeyStore]::Target), 'Process')
    & .venv/Scripts/python.exe (Join-Path $PSScriptRoot 'singleton_luna_api.py') --workspace $Workspace --phase execute --plan $Plan --allow-paid-execution
    $exitCode = $LASTEXITCODE
} finally {
    [Environment]::SetEnvironmentVariable('OPENAI_API_KEY', $previous, 'Process')
    $previous = $null
    Pop-Location
}
exit $exitCode
