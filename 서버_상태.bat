@echo off

chcp 65001 >nul

setlocal EnableExtensions

cd /d "%~dp0"



powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\al-note-status.ps1"

set ERR=%ERRORLEVEL%



echo.

pause

exit /b %ERR%

