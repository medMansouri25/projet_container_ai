@echo off
REM ============================================================
REM  SmartContainer_AI - Detection classe Conteneur
REM
REM  Pipeline : YOLO detects Conteneur -> borne le champ de recherche
REM             puis YOLO bic.onnx trouve NumeroBIC dans cette zone
REM
REM  Usage :
REM    trainConteneur.bat              -> yolo11s (VPS, haute precision)
REM    trainConteneur.bat browser      -> yolo11n (navigateur, ~5 Mo ONNX)
REM    trainConteneur.bat [N]          -> yolo11s, N epochs
REM    trainConteneur.bat browser [N]  -> yolo11n, N epochs
REM ============================================================
setlocal
cd /d "%~dp0"

set PY=.venv\Scripts\python
set DATASET=%~dp0Application\dataset\conteneur
set REPORTS=%~dp0Application\reports\conteneur

REM --- Parse arguments ---
set BROWSER_MODE=0
set EPOCHS=%1
if /i "%1"=="browser" (
    set BROWSER_MODE=1
    set EPOCHS=%2
)
if "%EPOCHS%"=="" set EPOCHS=40

REM --- Choix du modele selon le mode ---
if "%BROWSER_MODE%"=="1" (
    set BASE=yolo11n.pt
    set MODELS=%~dp0Application\models\conteneur_browser
    set MODE_LABEL=NAVIGATEUR [yolo11n - leger]
) else (
    set BASE=yolo11s.pt
    set MODELS=%~dp0Application\models\conteneur
    set MODE_LABEL=VPS [yolo11s - production]
)

echo.
echo ============================================================
echo   SmartContainer AI - Entrainement Conteneur
echo   MODE : %MODE_LABEL%
echo   Base : %BASE%   Epochs : %EPOCHS%
echo ============================================================

echo.
echo ============================================================
echo   ETAPE 1/3 : PREPARATION DATASET Conteneur (1 classe)
echo   Source : Application\dataset\raw\Conteneur
echo   Split 75/15/10
echo ============================================================
echo.
%PY% Application\ml\prepare_conteneur_dataset.py
if errorlevel 1 (
    echo [ERREUR] Preparation echouee. Arret.
    pause & exit /b 1
)

echo.
echo ============================================================
echo   ETAPE 2/3 : ENTRAINEMENT ( %EPOCHS% epochs, base %BASE% )
echo ============================================================
echo.
if "%BROWSER_MODE%"=="1" (
    %PY% Application\ml\train.py ^
        --dataset "%DATASET%" ^
        --models  "%MODELS%"  ^
        --reports "%REPORTS%" ^
        --base-model "%BASE%" ^
        --epochs %EPOCHS%     ^
        --batch 16            ^
        --export-onnx         ^
        --onnx-out "%~dp0frontend\models\conteneur.onnx"
) else (
    %PY% Application\ml\train.py ^
        --dataset "%DATASET%" ^
        --models  "%MODELS%"  ^
        --reports "%REPORTS%" ^
        --base-model "%BASE%" ^
        --epochs %EPOCHS%
)
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
    echo [ERREUR] Evaluation echouee (non bloquant).
)

echo.
echo ============================================================
echo   TERMINE
if "%BROWSER_MODE%"=="1" (
    echo   Modele navigateur : Application\models\conteneur_browser\
    echo   ONNX navigateur   : frontend\models\conteneur.onnx
) else (
    echo   Modele VPS        : Application\models\conteneur\
)
echo   Rapports          : Application\reports\conteneur\
echo ============================================================
pause
