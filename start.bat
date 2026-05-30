@echo off
cd /d "C:\Users\hakan\OneDrive\Masaüstü\gmail-podcast"
curl -s http://127.0.0.1:5000 >nul 2>&1
if %errorlevel% == 0 (
    start "" "http://127.0.0.1:5000"
) else (
    start /min "" python app.py
    timeout /t 3 /nobreak >nul
    start "" "http://127.0.0.1:5000"
)
