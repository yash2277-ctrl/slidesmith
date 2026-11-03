@echo off
setlocal
title SlideSmith (phone access)
cd /d "%~dp0"

set SLIDESMITH_LAN=1
rem ---- find Python -------------------------------------------------------
set "PY=python"
%PY% -c "import sys" >nul 2>nul
if errorlevel 1 set "PY=py"
%PY% -c "import sys" >nul 2>nul
if errorlevel 1 (
  echo.
  echo  Python was not found.
  echo  Install Python 3.10 or newer from https://www.python.org/downloads/
  echo  and tick "Add python.exe to PATH" during setup, then run this file again.
  echo.
  pause
  exit /b 1
)

rem ---- already running? just open it -------------------------------------
powershell -NoProfile -Command "try { Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 http://127.0.0.1:8000/api/status | Out-Null; exit 0 } catch { exit 1 }" >nul 2>nul
if not errorlevel 1 (
  echo SlideSmith is already running. For phone access, close the other SlideSmith window first, then run this again.
  if not "%NO_BROWSER%"=="1" start "" http://127.0.0.1:8000
  exit /b 0
)

rem ---- install packages the first time or when requirements change -------
if not exist data mkdir data
fc /b requirements.txt data\.deps-installed >nul 2>nul
if errorlevel 1 (
  echo Installing required packages, first run only - this can take a minute...
  %PY% -m pip install --disable-pip-version-check -q -r requirements.txt
  if errorlevel 1 (
    echo.
    echo  Installing packages failed. Check your internet connection and try again.
    pause
    exit /b 1
  )
  copy /y requirements.txt data\.deps-installed >nul
)

rem ---- start ---------------------------------------------------------------
echo.
echo  SlideSmith is running at http://127.0.0.1:8000
echo  Your browser will open automatically. Close this window to stop SlideSmith.
echo.
%PY% app.py
if errorlevel 1 (
  echo.
  echo  SlideSmith stopped with an error - see the messages above.
  pause
)
