# Load the saved credential only for this explicitly authorized Batch process.
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Plan,
    [ValidateSet('submit', 'status', 'poll', 'bulk', 'workflow')][string]$Phase = 'submit',
    [string]$ContinuationRef,
    [switch]$AllowPaidExecution
)
$ErrorActionPreference = 'Stop'
if (-not $AllowPaidExecution) { throw 'Explicit -AllowPaidExecution is required.' }
if ($ContinuationRef -and $Phase -ne 'workflow') { throw 'A continuation reference is supported only by the workflow controller.' }
Add-Type -Path (Join-Path $PSScriptRoot 'windows_key_store.cs')
if (-not [NewsKeyStore]::Exists([NewsKeyStore]::Target)) { throw 'The saved OpenAI key is unavailable.' }
$previousBatchKey = [Environment]::GetEnvironmentVariable('OPENAI_API_KEY', 'Process')
$batchExitCode = 1
Push-Location (Split-Path $PSScriptRoot -Parent)
try {
    [Environment]::SetEnvironmentVariable('OPENAI_API_KEY', [NewsKeyStore]::Load([NewsKeyStore]::Target), 'Process')
    if ($Phase -eq 'poll') {
        & .venv/Scripts/python.exe (Join-Path $PSScriptRoot 'poll_luna_budget_batch.py') --plan $Plan --allow-paid-execution
    } elseif ($Phase -eq 'bulk') {
        & .venv/Scripts/python.exe (Join-Path $PSScriptRoot 'execute_luna_budget_wave.py') --plan $Plan --allow-paid-execution
    } elseif ($Phase -eq 'workflow') {
        if ($ContinuationRef) {
            & .venv/Scripts/python.exe (Join-Path $PSScriptRoot 'run_luna_budget_workflow.py') --plan $Plan --allow-paid-execution --continuation-ref $ContinuationRef
        } else {
            & .venv/Scripts/python.exe (Join-Path $PSScriptRoot 'run_luna_budget_workflow.py') --plan $Plan --allow-paid-execution
        }
    } else {
        & .venv/Scripts/python.exe (Join-Path $PSScriptRoot 'execute_luna_budget_batch.py') $Phase --plan $Plan --allow-paid-execution
    }
    $batchExitCode = $LASTEXITCODE
} finally {
    [Environment]::SetEnvironmentVariable('OPENAI_API_KEY', $previousBatchKey, 'Process')
    $previousBatchKey = $null
    Pop-Location
}
exit $batchExitCode
