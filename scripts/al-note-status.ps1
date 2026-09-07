# Print AL-Note server / supervisor status.
$ErrorActionPreference = "Continue"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$PidFile = Join-Path $Root "logs\supervisor.pid"
$SupLog = Join-Path $Root "logs\supervisor.log"

function Test-Port([int]$Port) {
  try {
    $c = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($c) { return [int]$c.OwningProcess }
  } catch {}
  return $null
}

function Test-Url([string]$Url) {
  try {
    $code = & curl.exe -k -s -o NUL -w "%{http_code}" --max-time 4 $Url 2>$null
    $n = 0
    if ([int]::TryParse("$code", [ref]$n)) {
      return ($n -ge 200 -and $n -lt 500)
    }
  } catch {}
  return $false
}

Write-Host ""
Write-Host "=== AL-Note status ==="
Write-Host ""

$supRunning = $false
if (Test-Path $PidFile) {
  $spid = (Get-Content $PidFile -ErrorAction SilentlyContinue | Select-Object -First 1).Trim()
  if ($spid -match '^\d+$' -and (Get-Process -Id ([int]$spid) -ErrorAction SilentlyContinue)) {
    $supRunning = $true
    Write-Host "[ok] Supervisor PID $spid"
  } else {
    Write-Host "[--] Supervisor not running (stale pid file?)"
  }
} else {
  Write-Host "[--] Supervisor not running"
}

$apiPid = Test-Port 8000
$webPid = Test-Port 3001
$apiOk = $apiPid -and (Test-Url "http://127.0.0.1:8000/api/health")
$webOk = $webPid -and (Test-Url "https://127.0.0.1:3001/")

if ($apiOk) { Write-Host "[ok] API  127.0.0.1:8000  (internal)" } else { Write-Host "[!!] API  internal down" }
if ($webOk) { Write-Host "[ok] Web  :3001 HTTPS  (pid $webPid)" } else { Write-Host "[!!] Web  :3001  down" }

$task = Get-ScheduledTask -TaskName "AL-Note" -ErrorAction SilentlyContinue
$lnk = Join-Path ([Environment]::GetFolderPath("Startup")) "AL-Note.lnk"
if ($task) { Write-Host "[ok] Autostart task: $($task.State)" } else { Write-Host "[--] Autostart task not registered" }
if (Test-Path $lnk) { Write-Host "[ok] Startup shortcut present" } else { Write-Host "[--] Startup shortcut missing" }

if (Test-Path $SupLog) {
  Write-Host ""
  Write-Host "Recent supervisor log:"
  Get-Content $SupLog -Tail 5 -ErrorAction SilentlyContinue | ForEach-Object { Write-Host "  $_" }
}

Write-Host ""
if (-not $supRunning -or -not $apiOk -or -not $webOk) {
  Write-Host "Fix: run 서버_켜기.bat"
} else {
  Write-Host "Open: https://localhost:3001"
}
Write-Host ""

if ($apiOk -and $webOk -and $supRunning) { exit 0 }
exit 1
