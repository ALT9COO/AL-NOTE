# Start supervisor in background, register logon autostart, wait until healthy.
param(
  [switch]$SkipAutostartRegister
)

$ErrorActionPreference = "Continue"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Supervisor = Join-Path $PSScriptRoot "al-note-supervisor.ps1"
$StopScript = Join-Path $PSScriptRoot "al-note-stop.ps1"
$RegisterScript = Join-Path $PSScriptRoot "al-note-register-autostart.ps1"
$LogDir = Join-Path $Root "logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

& $StopScript | Out-Null
Start-Sleep -Seconds 2

if (-not $SkipAutostartRegister) {
  try {
    & $RegisterScript
  } catch {
    Write-Host "[warn] autostart not registered:" $_.Exception.Message
  }
}

$supArgs = "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$Supervisor`""
Start-Process -FilePath "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe" `
  -ArgumentList $supArgs `
  -WorkingDirectory $Root `
  -WindowStyle Hidden | Out-Null

function Test-Listen([int]$Port) {
  try {
    $c = New-Object System.Net.Sockets.TcpClient
    $iar = $c.BeginConnect("127.0.0.1", $Port, $null, $null)
    $ok = $iar.AsyncWaitHandle.WaitOne(500)
    $connected = $ok -and $c.Connected
    try { $c.Close() } catch {}
    return $connected
  } catch {
    return $false
  }
}

function Test-Url([string]$Url, [int]$TimeoutSec = 4) {
  try {
    $code = & curl.exe -k -s -o NUL -w "%{http_code}" --max-time $TimeoutSec $Url 2>$null
    $n = 0
    if ([int]::TryParse("$code", [ref]$n)) {
      return ($n -ge 200 -and $n -lt 500)
    }
  } catch {}
  return $false
}

$apiOk = $false
$webOk = $false
for ($i = 0; $i -lt 120; $i++) {
  if (-not $apiOk -and (Test-Listen 8000)) {
    $apiOk = Test-Url "http://127.0.0.1:8000/api/health" 3
  }
  if (-not $webOk -and (Test-Listen 3001)) {
    $webOk = Test-Url "https://127.0.0.1:3001/" 8
  }
  if ($apiOk -and $webOk) { break }
  Start-Sleep -Seconds 1
}

$ips = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
  Where-Object { $_.IPAddress -notmatch '^(127\.|169\.254\.)' -and $_.PrefixOrigin -ne 'WellKnown' } |
  Select-Object -ExpandProperty IPAddress -Unique

Write-Host ""
if ($apiOk) { Write-Host "[ok] API  127.0.0.1:8000  (internal only)" } else { Write-Host "[..] API still starting  (see logs\api.log / logs\supervisor.log)" }
if ($webOk) { Write-Host "[ok] Web  https://localhost:3001" } else { Write-Host "[..] Web still starting  (first compile can take ~2 min; see logs\web.log)" }
Write-Host ""
Write-Host "This PC:     https://localhost:3001"
foreach ($ip in $ips) {
  Write-Host ("LAN:         https://{0}:3001" -f $ip)
}
Write-Host ""
Write-Host "Self-signed cert: phone/PC will show a security warning — Advanced → Continue."
Write-Host "Running in background. Windows logon will start it again (45s after login)."
Write-Host "Stop now:            서버_끄기.bat"
Write-Host "Disable autostart:   자동시작_끄기.bat"
Write-Host "Check status:        서버_상태.bat"
Write-Host ""

if ($apiOk -and $webOk) { exit 0 }
if ($apiOk -or $webOk) { exit 2 }
exit 1
