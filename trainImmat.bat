@echo off
REM ============================================================
REM  SmartContainer_AI - Detection PLAQUE d'immatriculation
REM
REM  Usage :
REM    trainImmat.bat              -> yolo11s (VPS, haute precision)
REM    trainImmat.bat browser      -> yolo11n (navigateur, ~5 Mo ONNX)
REM    trainImmat.bat [N]          -> yolo11s, N epochs
REM    trainImmat.bat browser [N]  -> yolo11n, N epochs
REM ============================================================
setlocal
cd /d "%~dp0"

set PY=.venv\Scripts\python
set DATASET=%~dp0Application\dataset\plaque
set REPORTS=%~dp0Application\reports\plaque

REM --- Parse arguments ---
set BROWSER_MODE=0
set EPOCHS=%1
if /i "%1"=="browser" (
    set BROWSER_MODE=1
    set EPOCHS=%2
)
if "%EPOCHS%"=="" set EPOCHS=60

REM --- Choix du modele selon le mode ---
if "%BROWSER_MODE%"=="1" (
    REM yolo11n : nano, ~5 Mo ONNX — uniquement pour le repere de cadrage
    REM dans le navigateur (la detection VPS reste sur yolo11s)
    set BASE=yolo11n.pt
    set MODELS=%~dp0Application\models\plaque_browser
    set MODE_LABEL=NAVIGATEUR [yolo11n - leger]
) else (
    REM yolo11s : small, 19 Mo .pt — precision maximale pour la prod VPS
    set BASE=yolo11s.pt
    set MODELS=%~dp0Application\models\plaque
    set MODE_LABEL=VPS [yolo11s - production]
)

echo.
echo ============================================================
echo   MODE : %MODE_LABEL%
echo   Base : %BASE%   Epochs : %EPOCHS%
echo ============================================================

echo.
echo ============================================================
echo   ETAPE 1/3 : NETTOYAGE + SPLIT 70/20/10 DU DATASET PLAQUE
echo ============================================================
echo.
%PY% Application\ml\prepare_plaque_dataset.py
if errorlevel 1 (
    echo [ERREUR] Preparation echouee. Arret.
    pause & exit /b 1
)

echo.
echo ============================================================
echo   ETAPE 2/3 : ENTRAINEMENT ( %EPOCHS% epochs, base %BASE% )
echo ============================================================
echo.
%PY% Application\ml\train.py ^
    --dataset "%DATASET%" ^
    --models  "%MODELS%"  ^
    --reports "%REPORTS%" ^
    --base-model "%BASE%" ^
    --epochs %EPOCHS%
if errorlevel 1 (
    echo [ERREUR] Entrainement echoue.
    pause & exit /b 1
)

echo.
echo ============================================================
echo   ETAPE 3/3 : EVALUATION SUR LE SPLIT TEST
echo ============================================================
echo.
%PY% Application\ml\evaluate.py ^
    --dataset "%DATASET%" ^
    --models  "%MODELS%"  ^
    --reports "%REPORTS%" ^
    --split test
if errorlevel 1 (
    echo [ERREUR] Evaluation echouee.
    pause & exit /b 1
)

REM --- Export ONNX automatique en mode browser ---
if "%BROWSER_MODE%"=="1" (
    echo.
    echo ============================================================
    echo   ETAPE 4/4 : EXPORT ONNX -> frontend/models/plaque.onnx
    echo ============================================================
    echo.
    %PY% Application\ml\export_onnx.py --target plaque_browser
    if errorlevel 1 (
        echo [ERREUR] Export ONNX echoue.
        pause & exit /b 1
    )
    echo.
    echo   frontend/models/plaque.onnx mis a jour.
    echo   Lance : git add frontend/models/plaque.onnx ^&^& git push
)

echo.
echo ============================================================
echo   TERMINE
if "%BROWSER_MODE%"=="1" (
    echo   Modele navigateur : Application\models\plaque_browser\
    echo   ONNX browser      : frontend\models\plaque.onnx
) else (
    echo   Modele VPS        : Application\models\plaque\
)
echo   Rapports          : Application\reports\plaque\
echo ============================================================
pause
