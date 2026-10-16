# Existing Windows credential store; the key remains process-local and unlogged.
[CmdletBinding()]
param([switch]$AllowPaidExecution, [string]$DependencyProject)
$ErrorActionPreference = 'Stop'
if (-not $AllowPaidExecution) { throw 'Concrete user approval and -AllowPaidExecution are required.' }
Add-Type -Path (Join-Path $PSScriptRoot 'windows_key_store.cs')
if (-not [NewsKeyStore]::Exists([NewsKeyStore]::Target)) { throw 'Save the OpenAI key using the existing local key form first.' }
$priorKey = [Environment]::GetEnvironmentVariable('OPENAI_API_KEY', 'Process')
$priorPath = $env:PYTHONPATH
$exitCode = 1
$executionProject = Split-Path $PSScriptRoot -Parent
Push-Location $executionProject
try {
    [Environment]::SetEnvironmentVariable('OPENAI_API_KEY', [NewsKeyStore]::Load([NewsKeyStore]::Target), 'Process')
    $env:PYTHONPATH = Join-Path $executionProject 'src'
    $arguments = @('run', '--offline', '--frozen')
    if ($DependencyProject) { $arguments += @('--project', $DependencyProject) }
    $arguments += @('python', (Join-Path $PSScriptRoot 'run_catalog_embeddings.py'), '--allow-paid-execution')
    & uv @arguments
    $exitCode = $LASTEXITCODE
} finally {
    [Environment]::SetEnvironmentVariable('OPENAI_API_KEY', $priorKey, 'Process')
    $priorKey = $null
    $env:PYTHONPATH = $priorPath
    Pop-Location
}
exit $exitCode
