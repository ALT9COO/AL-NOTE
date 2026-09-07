# AL-Note hidden supervisor: keeps local API and HTTPS Web (3001) running.
# Started by 서버_켜기.bat or Windows logon (scheduled task + Startup shortcut).
$ErrorActionPreference = "Continue"

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$LogDir = Join-Path $Root "logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$SupLog = Join-Path $LogDir "supervisor.log"
$PidFile = Join-Path $LogDir "supervisor.pid"
$ApiLog = Join-Path $LogDir "api.log"
$WebLog = Join-Path $LogDir "web.log"

function Write-SupLog([string]$Message) {
  $line = "{0} {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
  Add-Content -Path $SupLog -Value $line -Encoding UTF8
}

function Get-ListenPid([int]$Port) {
  try {
    $c = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
      Select-Object -First 1
    if ($c) { return [int]$c.OwningProcess }
  } catch {}
  return $null
}

function Test-PortOpen([int]$Port) {
  return $null -ne (Get-ListenPid $Port)
}

function Test-ApiHealthy {
  # Long STT can block /api/health. If the port is still listening, leave it alone.
  return (Test-PortOpen 8000)
}

function Test-WebHealthy {
  return (Test-PortOpen 3001)
}

$mutex = New-Object System.Threading.Mutex($false, "Global\ALNoteSupervisor")
try {
  $owned = $mutex.WaitOne(0)
} catch [System.Threading.AbandonedMutexException] {
  $owned = $true
}
if (-not $owned) {
  Write-SupLog "another supervisor is already running; exiting"
  exit 0
}

$PID | Set-Content -Path $PidFile -Encoding ASCII
Write-SupLog "supervisor start pid=$PID root=$Root"

$Python = Join-Path $Root ".venv\Scripts\python.exe"
$NodeCandidates = @(
  (Get-Command node.exe -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source),
  "$env:ProgramFiles\nodejs\node.exe",
  "${env:ProgramFiles(x86)}\nodejs\node.exe"
)
$Node = $NodeCandidates | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
$BackendDir = Join-Path $Root "backend"
$FrontendDir = Join-Path $Root "frontend"
$NextRel = "node_modules\next\dist\bin\next"

if ($Node) {
  $env:Path = "$(Split-Path $Node -Parent);$env:Path"
}
$env:PYTHONUNBUFFERED = "1"
$env:PYTHONIOENCODING = "utf-8"

function Stop-Tree([int]$ProcessId) {
  if ($ProcessId -le 0) { return }
  & taskkill.exe /PID $ProcessId /T /F 2>$null | Out-Null
}

function Stop-ListenPort([int]$Port) {
  $seen = @{}
  Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
    ForEach-Object {
      $id = [int]$_.OwningProcess
      if ($id -gt 0 -and -not $seen.ContainsKey($id)) {
        $seen[$id] = $true
        Stop-Tree $id
      }
    }
}

function Start-HiddenCmd([string]$CommandLine, [string]$WorkDir, [string]$LogFile) {
  $banner = "echo.>> `"$LogFile`" & echo ===== {0} =====>> `"$LogFile`"" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss")
  $full = "$banner & $CommandLine >> `"$LogFile`" 2>&1"
  $psi = New-Object System.Diagnostics.ProcessStartInfo
  $psi.FileName = "$env:SystemRoot\System32\cmd.exe"
  $psi.Arguments = "/c $full"
  $psi.WorkingDirectory = $WorkDir
  $psi.UseShellExecute = $true
  $psi.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Hidden
  $psi.CreateNoWindow = $true
  [void][System.Diagnostics.Process]::Start($psi)
}

function Get-LanOrigin {
  $ip = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
    Where-Object { $_.IPAddress -notmatch '^(127\.|169\.254\.|0\.)' -and $_.PrefixOrigin -ne "WellKnown" } |
    Select-Object -ExpandProperty IPAddress -Unique |
    Select-Object -First 1
  if ($ip) { return "https://${ip}:3001" }
  return ""
}

function Start-Api {
  if (-not (Test-Path $Python)) {
    Write-SupLog "ERROR python missing: $Python"
    return
  }
  $origin = Get-LanOrigin
  if ($origin) {
    $env:PUBLIC_BASE_URL = $origin
    Write-SupLog "api public origin $origin"
  }
  Stop-ListenPort 8000
  Start-Sleep -Milliseconds 500
  Write-SupLog "starting api"
  $cmd = "`"$Python`" -m uvicorn main:app --host 127.0.0.1 --port 8000"
  Start-HiddenCmd $cmd $BackendDir $ApiLog
}

function Start-Web {
  if (-not $Node) {
    Write-SupLog "ERROR node.exe not found"
    return
  }
  $nextAbs = Join-Path $FrontendDir $NextRel
  if (-not (Test-Path $nextAbs)) {
    Write-SupLog "ERROR next binary missing: $nextAbs"
    return
  }
  $keyPem = Join-Path $FrontendDir "certs\dev-key.pem"
  $certPem = Join-Path $FrontendDir "certs\dev-cert.pem"
  $certScript = Join-Path $PSScriptRoot "ensure-https-cert.ps1"
  try {
    & $certScript
  } catch {
    Write-SupLog "ERROR https cert: $($_.Exception.Message)"
    if (-not ((Test-Path $keyPem) -and (Test-Path $certPem))) {
      return
    }
    Write-SupLog "using existing https cert files"
  }
  if (-not (Test-Path $keyPem) -or -not (Test-Path $certPem)) {
    Write-SupLog "ERROR https cert files missing"
    return
  }
  Stop-ListenPort 3001
  Start-Sleep -Milliseconds 500
  $origin = Get-LanOrigin
  if ($origin) {
    $env:ALNOTE_PUBLIC_ORIGIN = $origin
    Write-SupLog "web public origin $origin"
  }
  Write-SupLog "starting web node=$Node https=:3001"
  $cmd = "`"$Node`" `"$NextRel`" dev -H 0.0.0.0 -p 3001 --experimental-https --experimental-https-key certs/dev-key.pem --experimental-https-cert certs/dev-cert.pem"
  Start-HiddenCmd $cmd $FrontendDir $WebLog
}

$apiStartedAt = $null
$webStartedAt = $null
$apiBackoff = 5
$webBackoff = 5
$apiGraceSec = 30
$webGraceSec = 120

try {
  while ($true) {
    if (Test-ApiHealthy) {
      $apiStartedAt = $null
      $apiBackoff = 5
    } else {
      $now = Get-Date
      if ($null -eq $apiStartedAt) {
        Write-SupLog "api down; starting"
        Start-Api
        $apiStartedAt = $now
      } elseif (($now - $apiStartedAt).TotalSeconds -ge $apiGraceSec) {
        Write-SupLog "api not healthy after ${apiGraceSec}s; restart in ${apiBackoff}s"
        Start-Sleep -Seconds $apiBackoff
        if ($apiBackoff -lt 60) { $apiBackoff = [Math]::Min(60, $apiBackoff + 5) }
        Start-Api
        $apiStartedAt = Get-Date
      }
    }

    if (Test-WebHealthy) {
      $webStartedAt = $null
      $webBackoff = 5
    } else {
      $now = Get-Date
      if ($null -eq $webStartedAt) {
        Write-SupLog "web down; starting"
        Start-Web
        $webStartedAt = $now
      } elseif (($now - $webStartedAt).TotalSeconds -ge $webGraceSec) {
        Write-SupLog "web not healthy after ${webGraceSec}s; restart in ${webBackoff}s"
        Start-Sleep -Seconds $webBackoff
        if ($webBackoff -lt 60) { $webBackoff = [Math]::Min(60, $webBackoff + 5) }
        Start-Web
        $webStartedAt = Get-Date
      }
    }

    Start-Sleep -Seconds 8
  }
} finally {
  Write-SupLog "supervisor stopping"
  try { $mutex.ReleaseMutex() } catch {}
  $mutex.Dispose()
  if (Test-Path $PidFile) {
    Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
  }
}
