@echo off
REM ============================================================
REM  SmartContainer_AI - Moteur de lecture CARACTERE (36 classes)
REM  Architecture du tuteur : YOLO detecte chaque caractere.
REM  Enchaine : preparation dataset -> entrainement -> evaluation
REM  Usage : train_char.bat [epochs]   (defaut : 40)
REM ============================================================
setlocal
cd /d "%~dp0"

set EPOCHS=%1
if "%EPOCHS%"=="" set EPOCHS=40

set PY=.venv\Scripts\python
set DATASET=%~dp0Application\dataset\char
set MODELS=%~dp0Application\models\char
set REPORTS=%~dp0Application\reports\char
REM yolo11s : petit modele, ~2-3x plus rapide que yolo11m sur CPU (VPS AMD)
REM pour une tache simple (detection de caracteres nets)
set BASE=yolo11s.pt

echo.
echo ============================================================
echo   ETAPE 1/3 : PREPARATION DU DATASET CARACTERE
echo   (nettoyage .npy, extraction valid, appariement labels)
echo ============================================================
echo.
%PY% Application\ml\prepare_char_dataset.py
if errorlevel 1 (
    echo.
    echo [ERREUR] Preparation echouee. Arret.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo   ETAPE 2/3 : ENTRAINEMENT ( %EPOCHS% epochs, 36 classes, base yolo11s )
echo   Modele : Application\models\char\best_v1.pt
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
echo   ETAPE 3/3 : EVALUATION SUR LE TEST DU TUTEUR (613 img)
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
echo   Modele  : Application\models\char\best_v1.pt
echo   Rapports: Application\reports\char\
echo ============================================================
pause
