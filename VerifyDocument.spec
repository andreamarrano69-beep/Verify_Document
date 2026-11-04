# -*- mode: python ; coding: utf-8 -*-
# Configurazione di PyInstaller per creare VerifyDocument.exe
#
#   python -m PyInstaller VerifyDocument.spec --noconfirm --clean
#
# Risultato: cartella dist/VerifyDocument/ con VerifyDocument.exe e i file necessari
# (va distribuita intera, ad esempio come .zip).

from PyInstaller.utils.hooks import collect_all, collect_submodules

import os

datas = [("esempi", "esempi"), ("assets", "assets")]

# OCR: se è stata preparata la cartella ./tesseract (scripts/prepara_tesseract.py) viene inclusa
if os.path.isdir("tesseract"):
    datas.append(("tesseract", "tesseract"))
    print("Tesseract (OCR) incluso nel programma")
else:
    print("ATTENZIONE: cartella 'tesseract' assente: il programma non potrà leggere scansioni e foto")
binaries = []
hiddenimports = collect_submodules("verify_document")

# librerie con file di dati o DLL da includere (pdfium.dll, font di reportlab, cmap di pdfminer)
for pacchetto in ("pypdfium2", "pypdfium2_raw", "pdfplumber", "pdfminer", "reportlab", "tkinterdnd2",
                  "pytesseract", "send2trash"):
    try:
        d, b, h = collect_all(pacchetto)
    except Exception:
        continue  # pacchetto opzionale non installato
    datas += d
    binaries += b
    hiddenimports += h

a = Analysis(
    ["avvia_gui.py"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["numpy", "pandas", "scipy", "matplotlib", "IPython", "pytest", "pypdf"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="VerifyDocument",
    console=False,          # nessuna finestra nera del terminale
    icon="assets/icona.ico",
    upx=False,              # UPX aumenta i falsi allarmi degli antivirus
)

coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="VerifyDocument")
