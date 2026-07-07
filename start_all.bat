claud@echo off
echo ==========================================
echo   NSE Bot - Starting All Services
echo ==========================================
echo.

:: Kill any leftover processes from a previous run
echo [0/4] Cleaning up old processes...
taskkill /F /IM ngrok.exe >nul 2>&1
taskkill /F /FI "WINDOWTITLE eq WhatsApp Bot" >nul 2>&1
taskkill /F /FI "WINDOWTITLE eq NSE Scraper" >nul 2>&1
taskkill /F /FI "WINDOWTITLE eq NSE Website Backend" >nul 2>&1
ping 127.0.0.1 -n 3 > nul

:: 1. Start Node.js NSE + BSE Scraper v2 (includes download worker internally)
echo [1/4] Starting NSE + BSE Scraper v2 (Node.js)...
start "NSE Scraper" cmd /k "cd /d "d:\prathmesh\shares\nse-announcement-downloader v2" && node server.js"

:: Wait for scraper to initialize
ping 127.0.0.1 -n 4 > nul

:: 2. Start Website Backend (port 3001)
echo [2/4] Starting NSE Website Backend (Node.js, port 3001)...
start "NSE Website Backend" cmd /k "cd /d d:\prathmesh\shares\nse-website\subscription-portal\backend && node src/server.js"

:: Wait for website backend to come up
ping 127.0.0.1 -n 4 > nul

:: 3. Start Python WhatsApp Bot (using explicit Python 3.10 path)
echo [3/4] Starting WhatsApp Bot (Python Flask, port 5000)...
start "WhatsApp Bot" cmd /k "cd /d d:\prathmesh\shares && C:\Users\prath\AppData\Local\Programs\Python\Python310\python.exe Bot.py"

:: Wait for Flask to be up
ping 127.0.0.1 -n 8 > nul

:: 4. Start ngrok tunnel (port 5000 — Flask serves both webhook + portal)
echo [4/4] Starting ngrok tunnel on port 5000 with static domain...
start "ngrok Tunnel" cmd /k "ngrok http --domain=sensitive-fortyish-phung.ngrok-free.dev 5000"

:: Wait for ngrok to initialize fully
ping 127.0.0.1 -n 6 > nul

echo.
echo ==========================================
echo   ALL SERVICES RUNNING!
echo ==========================================
echo.
echo  WhatsApp Webhook URL (for Meta):
echo  https://sensitive-fortyish-phung.ngrok-free.dev/webhook
echo.
echo  Subscription Portal URL (send this link on WhatsApp):
echo  https://sensitive-fortyish-phung.ngrok-free.dev/portal
echo.
echo  Verify Token: nse_bot_secret_2024
echo.
echo  NSE + BSE Scraper v2:
echo    Monitors NSE + BSE in parallel every 30s
echo    Download worker runs inside the same process
echo.
echo  NOTE: Build the React frontend first if you haven't:
echo    cd nse-website\subscription-portal\frontend
echo    npm run build
echo ==========================================
echo.
pause