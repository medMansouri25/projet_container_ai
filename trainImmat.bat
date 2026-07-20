@echo off
REM ============================================================
REM  SmartContainer_AI - Detection PLAQUE d'immatriculation (marocaine)
REM  Dataset Roboflow moroccan-dataset (1 classe : immatriculation).
REM  Enchaine : nettoyage + split 70/20/10 -> entrainement -> evaluation
REM  Usage : trainImmat.bat [epochs]   (defaut : 40)
REM ============================================================
setlocal
cd /d "%~dp0"

set EPOCHS=%1
if "%EPOCHS%"=="" set EPOCHS=40

set PY=.venv\Scripts\python
set DATASET=%~dp0Application\dataset\plaque
set MODELS=%~dp0Application\models\plaque
set REPORTS=%~dp0Application\reports\plaque
REM yolo11s : petit modele, rapide sur CPU (VPS AMD) ; la detection d'une
REM zone plaque (1 classe, texte net) ne justifie pas yolo11m
set BASE=yolo11s.pt

echo.
echo ============================================================
echo   ETAPE 1/3 : NETTOYAGE + SPLIT 70/20/10 DU DATASET PLAQUE
echo   (paires image+label, anti-fuite par source, classe -^> immatriculation)
echo ============================================================
echo.
%PY% Application\ml\prepare_plaque_dataset.py
if errorlevel 1 (
    echo.
    echo [ERREUR] Preparation echouee. Arret.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo   ETAPE 2/3 : ENTRAINEMENT ( %EPOCHS% epochs, 1 classe, base yolo11s )
echo   Modele : Application\models\plaque\best_v1.pt
echo ============================================================
echo.
%PY% Application\ml\train.py --dataset "%DATASET%" --models "%MODELS%" --reports "%REPORTS%" --base-model "%BASE%" --epochs %EPOCHS%
if errorlevel 1 (
    echo.
    echo [ERREUR] Entrainement echoue. Evaluation annulee.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo   ETAPE 3/3 : EVALUATION SUR LE SPLIT TEST
echo ============================================================
echo.
%PY% Application\ml\evaluate.py --dataset "%DATASET%" --models "%MODELS%" --reports "%REPORTS%" --split test
if errorlevel 1 (
    echo.
    echo [ERREUR] Evaluation echouee.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo   TERMINE
echo   Modele  : Application\models\plaque\best_v1.pt
echo   Rapports: Application\reports\plaque\
echo ============================================================
pause
