@echo off
cd /d "%~dp0"

where python >nul 2>nul
if %ERRORLEVEL%==0 (
  set PYTHON=python
) else (
  where py >nul 2>nul
  if %ERRORLEVEL%==0 (
    set PYTHON=py -3
  ) else (
    echo Python 3 was not found. Install it from https://www.python.org/downloads/ then try again.
    pause
    exit /b 1
  )
)

%PYTHON% run.py
if errorlevel 1 pause
exit /b %ERRORLEVEL%
