# Windows logon entry: wait for project files, then start supervisor if needed.
$ErrorActionPreference = "Continue"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$LogDir = Join-Path $Root "logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$AutoLog = Join-Path $LogDir "autostart.log"
$Supervisor = Join-Path $PSScriptRoot "al-note-supervisor.ps1"
$PidFile = Join-Path $LogDir "supervisor.pid"

function Write-AutoLog([string]$Message) {
  $line = "{0} {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
  Add-Content -Path $AutoLog -Value $line -Encoding UTF8
}

function Test-SupervisorRunning {
  if (-not (Test-Path $PidFile)) { return $false }
  $spid = (Get-Content $PidFile -ErrorAction SilentlyContinue | Select-Object -First 1).Trim()
  if ($spid -notmatch '^\d+$') { return $false }
  return $null -ne (Get-Process -Id ([int]$spid) -ErrorAction SilentlyContinue)
}

function Test-ProjectReady {
  $python = Join-Path $Root ".venv\Scripts\python.exe"
  $next = Join-Path $Root "frontend\node_modules\next\dist\bin\next"
  return ((Test-Path $python) -and (Test-Path $next))
}

Write-AutoLog "autostart begin user=$env:USERNAME"

for ($i = 0; $i -lt 90; $i++) {
  if (Test-ProjectReady) { break }
  Start-Sleep -Seconds 2
}

if (-not (Test-ProjectReady)) {
  Write-AutoLog "ERROR project files not ready after 180s (OneDrive sync?)"
  exit 1
}

if (Test-SupervisorRunning) {
  Write-AutoLog "supervisor already running"
  exit 0
}

try {
  $c8000 = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
  $c3001 = Get-NetTCPConnection -LocalPort 3001 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($c8000 -and $c3001) {
    Write-AutoLog "ports already listening (8000=$($c8000.OwningProcess), 3001=$($c3001.OwningProcess)); starting supervisor only"
  }
} catch {}

$supArgs = "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$Supervisor`""
Start-Process -FilePath "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe" `
  -ArgumentList $supArgs `
  -WorkingDirectory $Root `
  -WindowStyle Hidden | Out-Null

Write-AutoLog "supervisor launch requested"
exit 0
