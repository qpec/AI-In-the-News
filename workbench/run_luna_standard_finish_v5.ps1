[CmdletBinding()]
param([switch]$CollectOnly)
$ErrorActionPreference = 'Stop'
$repository = Split-Path $PSScriptRoot -Parent
$owner = 'C:/Users/ynhan/AppData/Local/AI-In-the-News/luna-standard-finish-20261020-v5'
$amendment = Get-Content -LiteralPath (Join-Path $owner 'finish-plan.json') -Raw | ConvertFrom-Json
if ($amendment.method -ne 'luna-standard-finish-v5' -or $amendment.id -notmatch '^[a-f0-9]{64}$') { throw 'Unrecognized Standard finish amendment.' }
if (Test-Path -LiteralPath (Join-Path $owner 'STOP')) { throw 'STOP exists; preserve it.' }
$livePython = @(Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object {
    $_.CommandLine -like '*luna_standard_finish_v5.py*' -and $_.CommandLine -like "*--workspace $owner*"
})
if ($livePython.Count) { throw 'A matching Python worker is already alive, including an orphaned wrapper child.' }
$launchPath = Join-Path $owner 'launch.json'
if (Test-Path -LiteralPath $launchPath) {
    $previous = Get-Content -LiteralPath $launchPath -Raw | ConvertFrom-Json
    foreach ($workerId in @($previous.pid, $previous.worker_pid)) {
        if ($workerId) {
            $process = Get-CimInstance Win32_Process -Filter "ProcessId=$workerId"
            if ($process -and $process.CommandLine -like "*$owner*" -and $process.CommandLine -like '*luna_standard_finish_v5*') { throw 'A matching execution is still alive.' }
        }
    }
}
$integrityOwner = 'C:/Users/ynhan/AppData/Local/AI-In-the-News/luna-standard-finish-integrity-20261020-v5'
Push-Location $repository
try {
    & uv run --offline --frozen python scripts/check_luna_standard_finish_v5.py --workspace $integrityOwner --source-owner $owner --plan $amendment.plan
    if ($LASTEXITCODE -ne 0) { throw 'Integrity check failed; preserve its STOP and evidence.' }
} finally { Pop-Location }
$integrity = Get-Content -LiteralPath (Join-Path $integrityOwner 'latest-integrity.json') -Raw | ConvertFrom-Json
if (-not $integrity.integrity_passed -or -not $integrity.operational_state_matches_latest_checkpoint) { throw 'Stopped checkpoint is not verified.' }
$canStart = if ($CollectOnly) { $integrity.recovery_gates.collect_allowed } else { $integrity.recovery_gates.resume_untouched_allowed }
if (-not $canStart) { throw ('Recovery is blocked: ' + ($integrity.recovery_gates.admission_blockers -join ', ')) }
if (Test-Path -LiteralPath (Join-Path $owner 'STOP')) { throw 'STOP exists; preserve it.' }
$phase = if ($CollectOnly) { 'collect' } else { 'run' }
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$stdout = Join-Path $owner "run-$stamp.stdout.log"
$stderr = Join-Path $owner "run-$stamp.stderr.log"
$wrapper = Join-Path $repository 'scripts/run_luna_standard_finish_v5_with_key.ps1'
$arguments = @('-NoProfile', '-File', ('"' + $wrapper + '"'), '-Workspace', ('"' + $owner + '"'), '-Plan', $amendment.plan, '-Amendment', $amendment.id, '-Phase', $phase, '-AllowPaidExecution')
$worker = Start-Process -FilePath 'powershell.exe' -ArgumentList $arguments -WorkingDirectory $repository -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
$launch = @{runner='scripts/luna_standard_finish_v5.py'; pid=$worker.Id; plan=$amendment.plan; amendment=$amendment.id; phase=$phase; launched_at=[DateTimeOffset]::UtcNow.ToString('o'); stdout=$stdout; stderr=$stderr; deadline_epoch=$amendment.deadline_epoch}
$launch | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $launchPath -Encoding utf8
$identityDeadline = [DateTimeOffset]::UtcNow.AddSeconds(15)
do {
    try {
        $startupLine = Get-Content -LiteralPath $stdout -TotalCount 1 -ErrorAction SilentlyContinue
        $startup = if ($startupLine) { $startupLine | ConvertFrom-Json } else { $null }
        if ($startup -and $startup.phase -eq 'startup_preflight') {
            $pythonWorker = Get-CimInstance Win32_Process -Filter "ProcessId=$($startup.pid)"
            if ($pythonWorker -and $pythonWorker.CommandLine -like '*scripts/luna_standard_finish_v5.py*' -and $pythonWorker.CommandLine -like "*--workspace $owner*") {
                $launch.worker_pid = $pythonWorker.ProcessId
                $launch.worker_created_at = $pythonWorker.CreationDate.ToUniversalTime().ToString('o')
                $launch | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $launchPath -Encoding utf8
                break
            }
        }
    } catch {
        # The first JSON line can still be in the process of being written.
    }
    Start-Sleep -Milliseconds 200
} while ([DateTimeOffset]::UtcNow -lt $identityDeadline -and -not $worker.HasExited)
$launch | ConvertTo-Json -Depth 4
