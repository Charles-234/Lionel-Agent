# Installs a per-user Windows Scheduled Task that starts Lionel's Telegram
# door at logon. Safe to re-run; the task is replaced on each install.
# The bot token never appears here - it stays in the repo .env file.

$repo = Split-Path -Parent $PSScriptRoot
$bat  = Join-Path $repo "scripts\start_lionel.bat"

$account = "$env:USERDOMAIN\$env:USERNAME"
$action    = New-ScheduledTaskAction -Execute $bat -WorkingDirectory $repo
$trigger   = New-ScheduledTaskTrigger -AtLogOn
$principal = New-ScheduledTaskPrincipal -UserId $account -LogonType Interactive
$settings  = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable

try {
    Register-ScheduledTask -TaskName "LionelAgentDoor" `
        -Action $action -Trigger $trigger -Principal $principal `
        -Settings $settings -Force -ErrorAction Stop
    Write-Output "Installed: LionelAgentDoor ($account) starts at logon -> $bat"
} catch {
    Write-Output "INSTALL FAILED: $($_.Exception.Message)"
    exit 1
}
