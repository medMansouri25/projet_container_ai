@echo off
REM ============================================================
REM  SmartContainer_AI - Lance le backend et ouvre le Labo,
REM  l'application, et prepare le chargement de l'extension
REM  Usage : lancer_tout.bat
REM ============================================================
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo.
    echo [ERREUR] .venv introuvable. Lance d'abord setup.bat.
    echo.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo   Demarrage du backend Flask (nouvelle fenetre)
echo ============================================================
echo.
start "SmartContainer AI - Backend Flask" cmd /k ".venv\Scripts\python.exe Application\backend\app.py"

echo Attente du demarrage du serveur (chargement des modeles, ~30-60s)...
set RETRIES=0
:wait_backend
set /a RETRIES+=1
curl -s -o nul -w "%%{http_code}" http://localhost:5000/labo > "%TEMP%\_bic_status.txt" 2>nul
set /p STATUS=<"%TEMP%\_bic_status.txt"
if "%STATUS%"=="200" goto backend_ready
if %RETRIES% GEQ 60 (
    echo.
    echo [ATTENTION] Le serveur ne repond toujours pas apres 2 minutes.
    echo Verifie la fenetre "SmartContainer AI - Backend Flask" pour une erreur.
    echo Ouverture des pages quand meme...
    goto backend_ready
)
timeout /t 2 /nobreak >nul
goto wait_backend

:backend_ready
del "%TEMP%\_bic_status.txt" >nul 2>nul
echo.
echo [OK] Backend disponible sur http://localhost:5000
echo.

echo ============================================================
echo   Ouverture des pages
echo ============================================================
echo.
echo   - Labo (local)        : http://localhost:5000/labo
echo   - Application (prod)  : https://containerai-marsamaroc.vercel.app/capture.html
echo   - Extension           : dossier ouvert dans l'explorateur (voir ci-dessous)
echo.
start "" "http://localhost:5000/labo"
start "" "https://containerai-marsamaroc.vercel.app/capture.html"
start "" "%~dp0Application\Extension"

echo ============================================================
echo   Extension "BIC Detector"
echo ============================================================
echo.
echo Si elle n'est pas deja chargee dans ton navigateur :
echo   1. Ouvre chrome://extensions  (ou edge://extensions)
echo   2. Active le "mode developpeur"
echo   3. Clique "Charger l'extension non empaquetee"
echo   4. Selectionne le dossier qui vient de s'ouvrir dans l'explorateur
echo      ( %~dp0Application\Extension )
echo   5. Epingle l'icone BIC Detector dans la barre d'outils
echo.
echo Une fois chargee, elle reste installee : plus besoin de refaire
echo cette manip aux prochains lancements (juste garder le backend actif).
echo.
echo ============================================================
echo   Le backend tourne dans l'autre fenetre - ne la ferme pas.
echo   Ctrl+C dans cette fenetre-la pour l'arreter.
echo ============================================================
echo.
pause
