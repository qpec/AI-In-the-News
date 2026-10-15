[CmdletBinding()]
param([Parameter(Mandatory = $true)][int]$Index, [switch]$AllowPaidExecution, [switch]$Continuation)
$ErrorActionPreference = 'Stop'
if (-not $AllowPaidExecution) { throw 'Explicit -AllowPaidExecution required.' }
Add-Type -Path (Join-Path $PSScriptRoot 'windows_key_store.cs')
$previous = [Environment]::GetEnvironmentVariable('EVENTREGISTRY_API_KEY', 'Process')
try {
    [Environment]::SetEnvironmentVariable('EVENTREGISTRY_API_KEY', [NewsKeyStore]::Load([NewsKeyStore]::NewsApiTarget), 'Process')
    $pilotScript = if ($Continuation) { 'continue_newsapi_pilot.py' } else { 'run_newsapi_pilot.py' }
    & uv run --frozen python (Join-Path $PSScriptRoot $pilotScript) --execute --index $Index
    $resultCode = $LASTEXITCODE
} finally {
    [Environment]::SetEnvironmentVariable('EVENTREGISTRY_API_KEY', $previous, 'Process')
}
exit $resultCode
