@echo off
setlocal
cd /d "%~dp0"
echo PokerChip Research v4.5 - Python 3.12 to 3.14
python --version
if errorlevel 1 goto failed
if not exist ".venv\Scripts\python.exe" python -m venv .venv
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m pip install -r requirements-lock.txt
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m pip check
if errorlevel 1 goto failed
echo Setup complete. Open RUN.cmd.
pause
exit /b 0
:failed
echo Setup failed. Check Python installation and the message above.
pause
exit /b 1
