# Stop AL-Note supervisor and anything listening on 3001 / 8000.
$ErrorActionPreference = "Continue"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$PidFile = Join-Path $Root "logs\supervisor.pid"

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

if (Test-Path $PidFile) {
  $spid = (Get-Content $PidFile -ErrorAction SilentlyContinue | Select-Object -First 1).Trim()
  if ($spid -match '^\d+$') {
    Stop-Tree ([int]$spid)
  }
}

Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
  Where-Object {
    $_.Name -match '^(powershell|pwsh)\.exe$' -and
    $_.CommandLine -and
    $_.CommandLine -like '*al-note-supervisor.ps1*'
  } |
  ForEach-Object {
    Stop-Tree $_.ProcessId
  }

Start-Sleep -Milliseconds 400
Stop-ListenPort 3001
Stop-ListenPort 8000

Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
  Where-Object {
    $_.Name -eq 'python.exe' -and
    $_.CommandLine -and
    $_.CommandLine -like '*uvicorn*' -and
    $_.CommandLine -like '*8000*'
  } |
  ForEach-Object {
    Stop-Tree $_.ProcessId
  }

$marker = $Root
Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
  Where-Object {
    $_.Name -eq 'node.exe' -and
    $_.CommandLine -and
    ($_.CommandLine -like '*next*dev*' -or $_.CommandLine -like '* -p 3001*') -and
    $_.CommandLine -like "*$marker*"
  } |
  ForEach-Object {
    Stop-Tree $_.ProcessId
  }

exit 0
