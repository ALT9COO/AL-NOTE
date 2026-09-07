@echo off
chcp 65001 >nul
setlocal EnableExtensions
cd /d "%~dp0"

echo.
echo === AL-Note 자동시작을 끕니다 ===
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\al-note-disable-autostart.ps1"

echo.
echo 로그인 시 자동 기동을 해제했습니다. 지금 돌아가는 서버는 그대로입니다.
echo 서버까지 끄려면 서버_끄기.bat 을 실행하세요.
echo.
pause
