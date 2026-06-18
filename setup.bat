@echo off
setlocal

echo ============================================================
echo  ProjetContainer_AI - Installation de l'environnement
echo ============================================================
echo.

REM Verifier que Python 3.11 est disponible
python --version 2>nul | findstr "3.11" >nul
if %ERRORLEVEL% NEQ 0 (
    echo [ERREUR] Python 3.11 requis. Telecharger depuis python.org
    echo          ou : winget install Python.Python.3.11
    pause
    exit /b 1
)
echo [OK] Python 3.11 detecte

REM Creer le venv
echo.
echo [1/3] Creation du venv...
python -m venv .venv
call .venv\Scripts\activate.bat
echo [OK] .venv cree et active

REM Installer PyTorch CUDA 12.8 (GPU NVIDIA recommande)
echo.
echo [2/3] Installation PyTorch CUDA 12.8...
echo       (necessite NVIDIA GPU + driver 520+)
echo       Pour CPU uniquement : modifier l index-url ci-dessous
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128 --quiet
if %ERRORLEVEL% NEQ 0 (
    echo [WARN] Installation GPU echouee, tentative CPU...
    pip install torch torchvision torchaudio --quiet
)
echo [OK] PyTorch installe

REM Installer les autres dependances
echo.
echo [3/3] Installation des dependances du projet...
pip install ^
    ultralytics==8.4.68 ^
    easyocr==1.7.2 ^
    opencv-python==4.13.0.92 ^
    flask==3.1.3 ^
    flask-cors==6.0.5 ^
    numpy==2.4.6 ^
    Pillow==12.2.0 ^
    pytest==9.1.0 ^
    --quiet
echo [OK] Dependances installees

echo.
echo ============================================================
echo  Installation terminee !
echo  Activer l environnement : .venv\Scripts\activate.bat
echo  Lancer les tests OCR    : python -m pytest TestYolo\testFruit\ocr\
echo  Lancer les tests pipeline: python -m pytest TestYolo\testFruit\pipeline\
echo ============================================================
endlocal
