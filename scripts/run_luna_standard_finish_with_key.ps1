[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$Workspace,
    [Parameter(Mandatory=$true)][string]$Plan,
    [Parameter(Mandatory=$true)][string]$Amendment,
    [ValidateSet('run','collect')][string]$Phase = 'run',
    [switch]$AllowPaidExecution
)
$ErrorActionPreference = 'Stop'
if (-not $AllowPaidExecution -or $Plan -notmatch '^[a-f0-9]{64}$' -or $Amendment -notmatch '^[a-f0-9]{64}$') { throw 'Exact plan, amendment and explicit execution flag required.' }
Add-Type -Path (Join-Path $PSScriptRoot 'windows_key_store.cs')
if (-not [NewsKeyStore]::Exists([NewsKeyStore]::Target)) { throw 'The saved OpenAI key is unavailable.' }
$previousStandardKey = [Environment]::GetEnvironmentVariable('OPENAI_API_KEY', 'Process')
$standardExitCode = 1
Push-Location (Split-Path $PSScriptRoot -Parent)
try {
    [Environment]::SetEnvironmentVariable('OPENAI_API_KEY', [NewsKeyStore]::Load([NewsKeyStore]::Target), 'Process')
    & .venv/Scripts/python.exe -u scripts/luna_standard_finish.py $Phase --workspace $Workspace --plan $Plan --amendment $Amendment --allow-paid-execution
    $standardExitCode = $LASTEXITCODE
} finally {
    [Environment]::SetEnvironmentVariable('OPENAI_API_KEY', $previousStandardKey, 'Process')
    $previousStandardKey = $null
    Pop-Location
}
exit $standardExitCode
