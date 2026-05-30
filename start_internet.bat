@echo off
cd /d "C:\Users\hakan\OneDrive\Masaüstü\gmail-podcast"

echo Asistan baslatiliyor...
start /min "" python app.py
timeout /t 3 /nobreak >nul

echo Cloudflare Tunnel baslatiliyor...
start /min "" cloudflared tunnel --url http://localhost:5000

echo.
echo Hazir! Cloudflare penceresi 5-10 saniye sonra URL verir.
echo O URL ile her yerden girebilirsin.
echo.
start "" "http://localhost:5000"
pause
