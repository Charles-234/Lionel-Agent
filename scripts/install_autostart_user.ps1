$startup = [Environment]::GetFolderPath("Startup")
$lnk = Join-Path $startup "LionelAgentDoor.lnk"

$wsh = New-Object -ComObject WScript.Shell
$sc = $wsh.CreateShortcut($lnk)
$sc.TargetPath = "D:\Phantom-agent\scripts\start_lionel.bat"
$sc.WorkingDirectory = "D:\Phantom-agent"
$sc.WindowStyle = 7   # minimized
$sc.Description = "Lionel agent Telegram door - starts at logon"
$sc.Save()

if (Test-Path $lnk) {
    Write-Output "Installed: $lnk -> start_lionel.bat at logon"
} else {
    Write-Output "INSTALL FAILED"
    exit 1
}