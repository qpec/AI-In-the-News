# Inject a stored credential only into the existing audited embedding launcher.
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Context,
    [Parameter(Mandatory = $true)][string]$Plan,
    [Parameter(Mandatory = $true)][string]$ApprovalPolicy,
    [switch]$AllowPaidExecution,
    [ValidateRange(0, 1000000)][int]$MaxRequests = 1,
    [string]$Actor = 'codex:embedding-execution',
    [string]$Workspace
)
$ErrorActionPreference = 'Stop'
if (-not $AllowPaidExecution) { throw 'Explicit -AllowPaidExecution and a registered approval policy are required.' }
Add-Type -Path (Join-Path $PSScriptRoot 'windows_key_store.cs')
if (-not [NewsKeyStore]::Exists([NewsKeyStore]::Target)) { throw 'Save an OpenAI key with set_openai_key.ps1 first.' }
$previous = [Environment]::GetEnvironmentVariable('OPENAI_API_KEY', 'Process')
$exitCode = 1
Push-Location (Split-Path $PSScriptRoot -Parent)
try {
    [Environment]::SetEnvironmentVariable('OPENAI_API_KEY', [NewsKeyStore]::Load([NewsKeyStore]::Target), 'Process')
    $arguments = @('run', '--frozen', 'python', (Join-Path $PSScriptRoot 'run_embeddings.py'),
        '--context', $Context, '--plan', $Plan, '--approval-policy', $ApprovalPolicy,
        '--allow-paid-execution', '--max-requests', $MaxRequests, '--actor', $Actor)
    if ($Workspace) { $arguments += @('--workspace', $Workspace) }
    & uv @arguments
    $exitCode = $LASTEXITCODE
} finally {
    [Environment]::SetEnvironmentVariable('OPENAI_API_KEY', $previous, 'Process')
    $previous = $null
    Pop-Location
}
exit $exitCode
