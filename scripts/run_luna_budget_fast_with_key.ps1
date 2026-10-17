# Use the saved credential only in this explicitly authorized Batch process.
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Plan,
    [Parameter(Mandatory = $true)][string]$ContinuationRef,
    [Parameter(Mandatory = $true)][string]$DiagnosticRef,
    [ValidateRange(1, 20000000)][long]$QueueTokenCap = 20000000,
    [ValidateRange(1, 16)][int]$CountWorkers = 16,
    [switch]$AllowPaidExecution
)
$ErrorActionPreference = 'Stop'
if (-not $AllowPaidExecution) { throw 'Explicit -AllowPaidExecution is required.' }
Add-Type -Path (Join-Path $PSScriptRoot 'windows_key_store.cs')
if (-not [NewsKeyStore]::Exists([NewsKeyStore]::Target)) { throw 'The saved OpenAI key is unavailable.' }
$previousFastBatchKey = [Environment]::GetEnvironmentVariable('OPENAI_API_KEY', 'Process')
$fastBatchExitCode = 1
Push-Location (Split-Path $PSScriptRoot -Parent)
try {
    [Environment]::SetEnvironmentVariable('OPENAI_API_KEY', [NewsKeyStore]::Load([NewsKeyStore]::Target), 'Process')
    & .venv/Scripts/python.exe (Join-Path $PSScriptRoot 'run_luna_budget_fast.py') --plan $Plan --continuation-ref $ContinuationRef --diagnostic-ref $DiagnosticRef --queue-token-cap $QueueTokenCap --count-workers $CountWorkers --allow-paid-execution
    $fastBatchExitCode = $LASTEXITCODE
} finally {
    [Environment]::SetEnvironmentVariable('OPENAI_API_KEY', $previousFastBatchKey, 'Process')
    $previousFastBatchKey = $null
    Pop-Location
}
exit $fastBatchExitCode
