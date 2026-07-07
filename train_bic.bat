@echo off
REM ============================================================
REM  SmartContainer_AI - Entrainement + Evaluation NumeroBIC
REM  Usage : train_bic.bat [epochs]   (defaut : 12)
REM ============================================================
setlocal
cd /d "%~dp0"

set EPOCHS=%1
if "%EPOCHS%"=="" set EPOCHS=12

set PY=.venv\Scripts\python
set DATASET=%~dp0Application\datasetEnt
set MODELS=%~dp0Application\models\bic
set REPORTS=%~dp0Application\reports\bic

echo.
echo ============================================================
echo   ETAPE 1/2 : ENTRAINEMENT NumeroBIC (%EPOCHS% epochs)
echo   Dataset : Application\datasetEnt (5838 train / 451 valid)
echo ============================================================
echo.

%PY% Application\ml\train.py --dataset "%DATASET%" --models "%MODELS%" --reports "%REPORTS%" --epochs %EPOCHS%
if errorlevel 1 (
    echo.
    echo [ERREUR] L'entrainement a echoue. Evaluation annulee.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo   ETAPE 2/2 : EVALUATION DU MODELE
echo ============================================================
echo.

%PY% Application\ml\evaluate.py --dataset "%DATASET%" --models "%MODELS%" --reports "%REPORTS%"
if errorlevel 1 (
    echo.
    echo [ERREUR] L'evaluation a echoue.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo   TERMINE - modele : Application\models\bic\
echo   rapports : Application\reports\bic\
echo ============================================================
pause
