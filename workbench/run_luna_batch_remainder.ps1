param([switch]$CollectOnly)
$ErrorActionPreference = 'Stop'
$repository = Split-Path -Parent $PSScriptRoot
$runRoot = 'C:\Users\ynhan\AppData\Local\AI-In-the-News\luna-batch-remainder-20261019-v1'
$registered = Get-Content -LiteralPath (Join-Path $runRoot 'plan.json') -Raw | ConvertFrom-Json
if ($registered.id -notmatch '^[a-f0-9]{64}$' -or $registered.method -ne 'luna-batch-remainder-20261019-v1') { throw 'Unexpected Batch plan.' }
if (Test-Path -LiteralPath (Join-Path $runRoot 'STOP')) { throw 'Preserve the Batch STOP; do not restart automatically.' }
$control = Join-Path $runRoot 'launch.json'
if (Test-Path -LiteralPath $control) {
    $previous = Get-Content -LiteralPath $control -Raw | ConvertFrom-Json
    foreach ($processId in @($previous.pid, $previous.worker_pid) | Where-Object { $_ }) {
        $running = Get-CimInstance Win32_Process -Filter "ProcessId = $processId"
        if ($running -and $running.CommandLine -match '(run_luna_batch_remainder_with_key\.ps1|luna_batch_remainder\.py)' -and $running.CommandLine.Contains($runRoot)) {
            @{state='already_running'; pid=$processId; plan=$registered.id} | ConvertTo-Json
            exit 0
        }
    }
}
$phase = if ($CollectOnly) { 'collect' } else { 'run' }
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$stdout = Join-Path $runRoot "run-$stamp.stdout.log"
$stderr = Join-Path $runRoot "run-$stamp.stderr.log"
$wrapper = Join-Path $repository 'scripts/run_luna_batch_remainder_with_key.ps1'
$arguments = @('-NoProfile', '-File', ('"' + $wrapper + '"'), '-Workspace', ('"' + $runRoot + '"'), '-Plan', $registered.id, '-Phase', $phase, '-AllowPaidExecution')
$process = Start-Process -FilePath 'powershell.exe' -ArgumentList $arguments -WorkingDirectory $repository -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
$value = @{pid=$process.Id; plan=$registered.id; runner='scripts/luna_batch_remainder.py'; phase=$phase;
    launched_at=[DateTimeOffset]::UtcNow.ToString('o'); stdout=$stdout; stderr=$stderr; deadline=$registered.deadline}
$value | ConvertTo-Json | Set-Content -LiteralPath $control -Encoding utf8
$value | ConvertTo-Json
