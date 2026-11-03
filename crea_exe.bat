@echo off
REM ===================================================================
REM  Crea VerifyDocument.exe (doppio clic). Da rifare a ogni modifica.
REM  Risultato: dist\VerifyDocument\VerifyDocument.exe
REM             dist\VerifyDocument-<versione>-windows.zip
REM ===================================================================
cd /d "%~dp0"
set PY=python
if exist ".venv\Scripts\python.exe" set PY=.venv\Scripts\python.exe

echo [1/5] Installazione librerie e PyInstaller...
%PY% -m pip install --quiet -r requirements-dev.txt pyinstaller
if errorlevel 1 goto errore

echo [2/5] Test automatici...
%PY% -m unittest discover -s tests
if errorlevel 1 goto errore

echo [3/5] Creazione del programma (1-3 minuti)...
%PY% -m PyInstaller VerifyDocument.spec --noconfirm --clean --log-level WARN
if errorlevel 1 goto errore

echo [4/5] Autotest del programma creato...
start "" /wait "dist\VerifyDocument\VerifyDocument.exe" --autotest
set ESITO=%errorlevel%
type "%TEMP%\verify_document_autotest.log"
echo.
if not "%ESITO%"=="0" goto errore

echo [5/5] Creazione dello zip da distribuire...
for /f %%v in ('%PY% -c "import verify_document; print(verify_document.__version__)"') do set VER=%%v
powershell -NoProfile -Command "Compress-Archive -Path dist\VerifyDocument -DestinationPath dist\VerifyDocument-%VER%-windows.zip -Force"

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
