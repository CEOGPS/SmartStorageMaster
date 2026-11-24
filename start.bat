@echo off
REM Double-click to start Storage Manager Pro (backend + web UI) and open it.
cd /d "%~dp0"
where node >nul 2>nul || (echo Node.js was not found. Install it from https://nodejs.org and run this again. & pause & exit /b 1)
node scripts\launch.mjs %*
if errorlevel 1 (echo. & echo The app stopped with an error. See the messages above. & pause)
