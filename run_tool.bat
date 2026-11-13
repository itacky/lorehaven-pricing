@echo off
rem Lorehaven pricing simulator - double-click to start. Close this window to stop the tool.
setlocal
cd /d "%~dp0"
set "PY="
for %%D in ("%USERPROFILE%\anaconda3" "%USERPROFILE%\miniconda3" "%LOCALAPPDATA%\anaconda3" "%LOCALAPPDATA%\miniconda3") do (
  if not defined PY if exist "%%~D\python.exe" (
    set "PY=%%~D\python.exe"
    set "PATH=%%~D;%%~D\Library\bin;%%~D\Scripts;%PATH%"
  )
)
if not defined PY (python -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul && set "PY=python")
if not defined PY (py -3 -c "import sys" >nul 2>nul && set "PY=py -3")
if not defined PY (
  echo Could not find Python 3.10 or newer. Install it from https://www.python.org and run this again.
  pause
  exit /b 1
)
%PY% -c "import sys; sys.exit(0 if (3, 10) <= sys.version_info[:2] <= (3, 13) else 1)" >nul 2>nul || (
  echo Found %PY% but it is not Python 3.10-3.13. Install Python 3.12 from https://www.python.org and run this again.
  pause
  exit /b 1
)
echo Using Python: %PY%
%PY% -c "import flask" >nul 2>nul || (
  echo Installing Flask, the only package the tool needs...
  %PY% -m pip install -r requirements-tool.txt
)
%PY% app\app.py
echo.
echo The simulator has stopped.
pause
