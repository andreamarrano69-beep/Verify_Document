@echo off
REM Avvia l'interfaccia grafica di Verify Document (doppio clic)
cd /d "%~dp0"
if exist ".venv\Scripts\pythonw.exe" (
    start "" ".venv\Scripts\pythonw.exe" -m verify_document.gui
) else (
    start "" pythonw -m verify_document.gui
)
