# Register Windows logon autostart: scheduled task + Startup folder shortcut.
$ErrorActionPreference = "Continue"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$AutoStart = Join-Path $PSScriptRoot "al-note-autostart.ps1"
$TaskName = "AL-Note"
$Pwsh = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"

$arg = "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$AutoStart`""

$taskOk = $false
try {
  $action = New-ScheduledTaskAction -Execute $Pwsh -Argument $arg -WorkingDirectory $Root
  $trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
  $trigger.Delay = "PT45S"
  $principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
  $settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -DontStopOnIdleEnd `
    -StartWhenAvailable `
    -RestartCount 5 `
    -RestartInterval (New-TimeSpan -Minutes 2) `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -MultipleInstances IgnoreNew
  Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
  $taskOk = $true
} catch {
  Write-Output ("scheduled task failed: " + $_.Exception.Message)
}

$startup = [Environment]::GetFolderPath("Startup")
$lnkPath = Join-Path $startup "AL-Note.lnk"
try {
  $wsh = New-Object -ComObject WScript.Shell
  $sc = $wsh.CreateShortcut($lnkPath)
  $sc.TargetPath = $Pwsh
  $sc.Arguments = $arg
  $sc.WorkingDirectory = $Root
  $sc.WindowStyle = 7
  $sc.Description = "AL-Note background supervisor"
  $sc.Save()
  Write-Output "startup shortcut: $lnkPath"
} catch {
  Write-Output ("startup shortcut failed: " + $_.Exception.Message)
}

if ($taskOk) {
  Write-Output "registered scheduled task $TaskName (45s delay after logon)"
} else {
  Write-Output "scheduled task not registered; startup shortcut will still run at logon"
}
