@echo off
REM Lionel Agent launcher - starts the governed Telegram door.
REM Reads ADMIN_TELEGRAM_ID / TELEGRAM_BOT_TOKEN from the repo .env file.
setlocal
set REPO=%~dp0..
cd /d "%REPO%"
".venv\Scripts\python.exe" -m interfaces.telegram_door
