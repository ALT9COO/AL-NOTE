@echo off
chcp 65001 >nul
setlocal EnableExtensions
cd /d "%~dp0"

if not exist "%~dp0.venv\Scripts\python.exe" (
  echo [오류] 가상환경이 없습니다: .venv
  pause
  exit /b 1
)

echo.
echo === AL-Note 를 백그라운드에서 켭니다 ===
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\al-note-start.ps1"
set ERR=%ERRORLEVEL%

echo.
if not "%ERR%"=="0" (
  echo 아직 완전히 준비되지 않았을 수 있습니다. 1~2분 후 https://localhost:3001 을 열어보세요.
  echo 상태 확인: 서버_상태.bat  ^|  로그: logs\supervisor.log
)
echo.
pause
exit /b %ERR%
