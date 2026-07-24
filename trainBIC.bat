@echo off
REM ============================================================
REM  SmartContainer_AI - Detection zone NumeroBIC (Code BIC)
REM
REM  Pipeline : YOLO detects NumeroBIC zone -> crop -> EasyOCR
REM
REM  Usage :
REM    trainBIC.bat              -> yolo11s (VPS, haute precision)
REM    trainBIC.bat browser      -> yolo11n (navigateur, ~5 Mo ONNX)
REM    trainBIC.bat [N]          -> yolo11s, N epochs
REM    trainBIC.bat browser [N]  -> yolo11n, N epochs
REM ============================================================
setlocal
cd /d "%~dp0"

set PY=.venv\Scripts\python
set DATASET=%~dp0Application\dataset\bic
set REPORTS=%~dp0Application\reports\bic

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
    REM yolo11n : nano, ~5 Mo ONNX - leger pour le navigateur
    set BASE=yolo11n.pt
    set MODELS=%~dp0Application\models\bic_browser
    set MODE_LABEL=NAVIGATEUR [yolo11n - leger]
) else (
    REM yolo11s : small, precision maximale pour la prod VPS
    set BASE=yolo11s.pt
    set MODELS=%~dp0Application\models\bic
    set MODE_LABEL=VPS [yolo11s - production]
)

echo.
echo ============================================================
echo   SmartContainer AI - Entrainement NumeroBIC
echo   MODE : %MODE_LABEL%
echo   Base : %BASE%   Epochs : %EPOCHS%
echo ============================================================

echo.
echo ============================================================
echo   ETAPE 1/3 : PREPARATION DATASET NumeroBIC (1 classe)
echo   Source : Application\dataset\raw\NumeroBIC
echo   Remapping classe 2 -> 0 + split 75/15/10
echo ============================================================
echo.
%PY% Application\ml\prepare_bic_dataset.py
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
    REM --batch 16 : evite CUDA OOM en mode auto-detect
    %PY% Application\ml\train.py ^
        --dataset "%DATASET%" ^
        --models  "%MODELS%"  ^
        --reports "%REPORTS%" ^
        --base-model "%BASE%" ^
        --epochs %EPOCHS%     ^
        --batch 16            ^
        --export-onnx         ^
        --onnx-out "%~dp0frontend\models\bic.onnx"
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
    echo   Modele navigateur : Application\models\bic_browser\
    echo   ONNX navigateur   : frontend\models\bic.onnx
    echo   A deployer sur le VPS : scp frontend/models/bic.onnx VPS:/models/
) else (
    echo   Modele VPS        : Application\models\bic\
    echo   Relancer avec : trainBIC.bat browser  pour exporter le ONNX navigateur
)
echo   Rapports          : Application\reports\bic\
echo ============================================================
pause
