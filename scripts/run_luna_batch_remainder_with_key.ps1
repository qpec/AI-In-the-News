[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$Workspace,
    [Parameter(Mandatory=$true)][string]$Plan,
    [ValidateSet('run','collect')][string]$Phase = 'run',
    [switch]$AllowPaidExecution
)
$ErrorActionPreference = 'Stop'
if (-not $AllowPaidExecution -or $Plan -notmatch '^[a-f0-9]{64}$') { throw 'An exact approved plan and explicit execution flag are required.' }
Add-Type -Path (Join-Path $PSScriptRoot 'windows_key_store.cs')
if (-not [NewsKeyStore]::Exists([NewsKeyStore]::Target)) { throw 'The saved OpenAI key is unavailable.' }
$previousRemainderKey = [Environment]::GetEnvironmentVariable('OPENAI_API_KEY', 'Process')
$remainderExitCode = 1
Push-Location (Split-Path $PSScriptRoot -Parent)
try {
    [Environment]::SetEnvironmentVariable('OPENAI_API_KEY', [NewsKeyStore]::Load([NewsKeyStore]::Target), 'Process')
    & .venv/Scripts/python.exe -u scripts/luna_batch_remainder.py $Phase --workspace $Workspace --plan $Plan --allow-paid-execution
    $remainderExitCode = $LASTEXITCODE
} finally {
    [Environment]::SetEnvironmentVariable('OPENAI_API_KEY', $previousRemainderKey, 'Process')
    $previousRemainderKey = $null
    Pop-Location
}
exit $remainderExitCode
