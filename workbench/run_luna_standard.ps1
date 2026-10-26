param()
$ErrorActionPreference = 'Stop'
$repository = Split-Path -Parent $PSScriptRoot
$runRoot = 'C:\Users\ynhan\AppData\Local\AI-In-the-News\luna-standard-full-corpus-20261018-v2'
$parentPlan = 'a962e5ece9d3fc558a67e0e0999e14399d52d0dadf41a0ee72bd861003865fd1'
$plan = $null
$downscalePlanPath = Join-Path $runRoot 'downscale-plan.json'
if (Test-Path -LiteralPath $downscalePlanPath) {
    $registered = Get-Content -LiteralPath $downscalePlanPath -Raw | ConvertFrom-Json
    if ($registered.parent_plan -ne $parentPlan -or $registered.id -notmatch '^[a-f0-9]{64}$') {
        throw 'Downscale plan cache has unexpected parent or identity.'
    }
    $plan = $registered.id
}
$control = Join-Path $runRoot 'launch.json'
if (Test-Path -LiteralPath (Join-Path $runRoot 'STOP')) {
    throw 'STOP file exists; preserve the user stop.'
}
if (Test-Path -LiteralPath $control) {
    $previous = Get-Content -LiteralPath $control -Raw | ConvertFrom-Json
    foreach ($processId in @($previous.pid, $previous.worker_pid) | Where-Object { $_ }) {
        $running = Get-CimInstance Win32_Process -Filter "ProcessId = $processId"
        if ($running -and $running.CommandLine -match 'luna_standard_(corpus|capacity|recovery|paced|downscaled)\.py' -and
            $running.CommandLine.Contains($runRoot)) {
            @{state='already_running'; pid=$processId; plan=$previous.plan} | ConvertTo-Json
            exit 0
        }
    }
}
$authorization = 'Prepare full corpus standard Luna. Remaining articles in both corpora. Run full and ensure it keeps running. Check new result integrity every hour. Test two and three additional workers: four, six and seven total, then continue at the measured setting. Fix and continue. There is a problem, it is not working. Find problem and comtinue. I believe we have been throttled. Fix it by downscaling if needed'
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$stdout = Join-Path $runRoot "run-$stamp.stdout.log"
$stderr = Join-Path $runRoot "run-$stamp.stderr.log"
$arguments = @('-u', 'scripts/luna_standard_downscaled.py', 'continue', '--workspace', $runRoot,
    '--plan', $parentPlan, '--authorization-text', ('"' + $authorization + '"'))
$process = Start-Process -FilePath (Join-Path $repository '.venv\Scripts\python.exe') `
    -ArgumentList $arguments -WorkingDirectory $repository -WindowStyle Hidden `
    -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
$value = @{pid=$process.Id; plan=$plan; parent_plan=$parentPlan; runner='scripts/luna_standard_downscaled.py';
    launched_at=(Get-Date).ToUniversalTime().ToString('o');
    stdout=$stdout; stderr=$stderr; authorization=$authorization}
$value | ConvertTo-Json | Set-Content -LiteralPath $control -Encoding utf8
$value | ConvertTo-Json
