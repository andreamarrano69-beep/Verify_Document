@echo off
REM ===================================================================
REM  Crea VerifyDocument.exe (doppio clic). Da rifare a ogni modifica.
REM  Risultato: dist\VerifyDocument\VerifyDocument.exe
REM             dist\VerifyDocument-<versione>-windows.zip
REM  Per includere lOCR serve Tesseract installato sul PC:
REM  https://github.com/UB-Mannheim/tesseract/wiki
REM ===================================================================
cd /d "%~dp0"
set PY=python
if exist ".venv\Scripts\python.exe" set PY=.venv\Scripts\python.exe

echo [1/6] Installazione librerie e PyInstaller...
%PY% -m pip install --quiet -r requirements-dev.txt pyinstaller
if errorlevel 1 goto errore

echo [2/6] Preparazione OCR (Tesseract)...
%PY% scripts\prepara_tesseract.py
if errorlevel 1 (
    echo.
    echo ATTENZIONE: Tesseract non trovato. Il programma non potra leggere scansioni e foto.
    echo Installalo da https://github.com/UB-Mannheim/tesseract/wiki e rilancia questo file.
    choice /m "Continuare comunque senza OCR"
    if errorlevel 2 goto errore
)

echo [3/6] Test automatici...
%PY% -m unittest discover -s tests
if errorlevel 1 goto errore

echo [4/6] Creazione del programma (1-3 minuti)...
%PY% -m PyInstaller VerifyDocument.spec --noconfirm --clean --log-level WARN
if errorlevel 1 goto errore

echo [5/6] Autotest del programma creato...
start "" /wait "dist\VerifyDocument\VerifyDocument.exe" --autotest
set ESITO=%errorlevel%
type "%TEMP%\verify_document_autotest.log"
echo.
if not "%ESITO%"=="0" goto errore

echo [6/6] Creazione dello zip da distribuire...
for /f %%v in ('%PY% -c "import verify_document; print(verify_document.__version__)"') do set VER=%%v
powershell -NoProfile -Command "Compress-Archive -Path dist\VerifyDocument -DestinationPath dist\VerifyDocument-%VER%-windows.zip -Force"

set ISCC=C:\Program Files (x86)\Inno Setup 6\ISCC.exe
if exist "%ISCC%" (
    echo [+] Creazione del setup per i PC dell'ufficio...
    "%ISCC%" /Q /DVersione=%VER% installer\VerifyDocument.iss
    if errorlevel 1 goto errore
    echo        Setup: dist\VerifyDocument-Setup-%VER%.exe
) else (
    echo [i] Inno Setup non installato: niente setup.exe ^(https://jrsoftware.org/isinfo.php^)
)

echo.
echo FATTO! Programma: dist\VerifyDocument\VerifyDocument.exe
echo        Da distribuire: dist\VerifyDocument-%VER%-windows.zip
pause
exit /b 0

:errore
echo.
echo ERRORE: creazione interrotta. Leggi i messaggi qui sopra.
pause
exit /b 1
