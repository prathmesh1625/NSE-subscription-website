@echo off
echo Creating nse_ingestion database...
"C:\Program Files\PostgreSQL\16\bin\psql.exe" -U postgres -p 5433 -c "CREATE DATABASE nse_ingestion;" 2>nul || "C:\PostgreSQL\bin\psql.exe" -U postgres -p 5433 -c "CREATE DATABASE nse_ingestion;" 2>nul
echo.
echo Done! Now run the Node.js scraper schema:
echo   cd nse-announcement-downloader
echo   node server.js
pause
