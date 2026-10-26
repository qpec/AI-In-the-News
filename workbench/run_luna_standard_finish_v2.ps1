[CmdletBinding()]
param([switch]$CollectOnly)
$ErrorActionPreference = 'Stop'
$repository = Split-Path $PSScriptRoot -Parent
$owner = 'C:/Users/ynhan/AppData/Local/AI-In-the-News/luna-standard-finish-20261020-v2'
$amendment = Get-Content -LiteralPath (Join-Path $owner 'finish-plan.json') -Raw | ConvertFrom-Json
if ($amendment.method -ne 'luna-standard-finish-v2' -or $amendment.id -notmatch '^[a-f0-9]{64}$') { throw 'Unrecognized Standard finish amendment.' }
if (Test-Path -LiteralPath (Join-Path $owner 'STOP')) { throw 'STOP exists; preserve it.' }
$launchPath = Join-Path $owner 'launch.json'
if (Test-Path -LiteralPath $launchPath) {
    $previous = Get-Content -LiteralPath $launchPath -Raw | ConvertFrom-Json
    foreach ($workerId in @($previous.pid, $previous.worker_pid)) {
        if ($workerId) {
            $process = Get-CimInstance Win32_Process -Filter "ProcessId=$workerId"
            if ($process -and $process.CommandLine -like "*$owner*" -and $process.CommandLine -like '*luna_standard_finish_v2*') { throw 'A matching execution is still alive.' }
        }
    }
}
$phase = if ($CollectOnly) { 'collect' } else { 'run' }
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$stdout = Join-Path $owner "run-$stamp.stdout.log"
$stderr = Join-Path $owner "run-$stamp.stderr.log"
$wrapper = Join-Path $repository 'scripts/run_luna_standard_finish_v2_with_key.ps1'
$arguments = @('-NoProfile', '-File', ('"' + $wrapper + '"'), '-Workspace', ('"' + $owner + '"'), '-Plan', $amendment.plan, '-Amendment', $amendment.id, '-Phase', $phase, '-AllowPaidExecution')
$worker = Start-Process -FilePath 'powershell.exe' -ArgumentList $arguments -WorkingDirectory $repository -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
$launch = @{runner='scripts/luna_standard_finish_v2.py'; pid=$worker.Id; plan=$amendment.plan; amendment=$amendment.id; phase=$phase; launched_at=[DateTimeOffset]::UtcNow.ToString('o'); stdout=$stdout; stderr=$stderr; deadline_epoch=$amendment.deadline_epoch}
$launch | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $launchPath -Encoding utf8
$launch | ConvertTo-Json -Depth 4
