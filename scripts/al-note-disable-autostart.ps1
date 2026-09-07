# Disable / remove AL-Note logon autostart. Does not stop running servers.
$ErrorActionPreference = "Continue"
Unregister-ScheduledTask -TaskName "AL-Note" -Confirm:$false -ErrorAction SilentlyContinue
$lnkPath = Join-Path ([Environment]::GetFolderPath("Startup")) "AL-Note.lnk"
if (Test-Path $lnkPath) {
  Remove-Item $lnkPath -Force -ErrorAction SilentlyContinue
}
Write-Output "autostart disabled"
