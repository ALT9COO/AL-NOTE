@echo off
chcp 65001 >nul
setlocal EnableExtensions
cd /d "%~dp0"

if /I not "%~1"=="nopause" (
  echo.
  echo === AL-Note 서버를 끕니다 ===
  echo.
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\al-note-stop.ps1"

if /I not "%~1"=="nopause" (
  echo 백그라운드 감시 프로세스와 포트 3001 을 종료했습니다.
  echo 다음 로그인에도 자동으로 켜지지 않게 하려면 자동시작_끄기.bat 을 실행하세요.
  echo.
  pause
)
