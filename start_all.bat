@echo off
setlocal
cd /d "%~dp0"
if not exist "cd_cpi_server\backend\.venv\Scripts\python.exe" goto missing
if not exist "cpi_server\backend\.venv\Scripts\python.exe" goto missing
if not exist "cd_cpi_server\frontend\node_modules" goto missing
if not exist "cpi_server\frontend\node_modules" goto missing
if not exist "dm_server\frontend\node_modules" goto missing
set "DM_PYTHON=..\..\cpi_server\backend\.venv\Scripts\python.exe"
if exist "dm_server\backend\.venv\Scripts\python.exe" set "DM_PYTHON=.venv\Scripts\python.exe"
where npm.cmd >nul 2>&1
if errorlevel 1 goto missing
where wt.exe >nul 2>&1
if errorlevel 1 goto terminal_missing
wt.exe -w new ^
 new-tab --title "Dossier MCP - 8004" --suppressApplicationTitle -d "%~dp0cd_cpi_server\mcp" cmd.exe /k "..\backend\.venv\Scripts\python.exe server.py" ; ^
 new-tab --title "Dossier Backend - 8003" --suppressApplicationTitle -d "%~dp0cd_cpi_server\backend" cmd.exe /k ".venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8003" ; ^
 new-tab --title "Dossier Frontend - 8081" --suppressApplicationTitle -d "%~dp0cd_cpi_server\frontend" cmd.exe /k "npm.cmd run dev" ; ^
 new-tab --title "CPI Backend - 8002" --suppressApplicationTitle -d "%~dp0cpi_server\backend" cmd.exe /k ".venv\Scripts\python.exe -m uvicorn main:app --reload --host 127.0.0.1 --port 8002" ; ^
 new-tab --title "CPI Frontend - 5173" --suppressApplicationTitle -d "%~dp0cpi_server\frontend" cmd.exe /k "npm.cmd run dev" ; ^
 new-tab --title "DM Backend - 8005" --suppressApplicationTitle -d "%~dp0dm_server\backend" cmd.exe /k "%DM_PYTHON% -m uvicorn main:app --reload --reload-dir . --reload-dir ..\..\cpi_server\backend\app --host 127.0.0.1 --port 8005" ; ^
 new-tab --title "DM Frontend - 5174" --suppressApplicationTitle -d "%~dp0dm_server\frontend" cmd.exe /k "npm.cmd run dev"
if errorlevel 1 goto terminal_failed
echo Seven server tabs opened in one Windows Terminal window. Startup may take a moment.
echo Credit Dossier: http://localhost:8081
echo Credit Policy Intelligence: http://localhost:5173
echo Data Manufacturing: http://localhost:5174
echo Keep the server tabs open. Double-click stop_all.bat to stop all seven servers.
exit /b 0
:terminal_missing
echo Windows Terminal is required for tabs. Install it and run this file again.
pause
exit /b 1
:terminal_failed
echo Windows Terminal could not open the server tabs. Check that it is installed and working.
pause
exit /b 1
:missing
echo Dependencies are missing. Follow the setup instructions in the root run.md first.
pause
exit /b 1
