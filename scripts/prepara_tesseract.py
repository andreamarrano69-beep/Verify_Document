"""Copia Tesseract (OCR) nella cartella ./tesseract, che viene inclusa nel .exe.

Uso (su Windows, con Tesseract installato da https://github.com/UB-Mannheim/tesseract/wiki):

    python scripts/prepara_tesseract.py [cartella di installazione di Tesseract]

Copia tesseract.exe con le sue DLL, i file di configurazione e le lingue eng/osd/ita.
Se la lingua italiana non è installata la scarica dal repository ufficiale tesseract-ocr/tessdata.
Tesseract è distribuito con licenza Apache 2.0 (copiata in tesseract/LICENSE-tesseract.txt).
"""

from __future__ import annotations

import os
import shutil
import sys
import urllib.request
from pathlib import Path

RADICE = Path(__file__).resolve().parent.parent
DESTINAZIONE = RADICE / "tesseract"
LINGUE = ("eng", "osd", "ita")
URL_LINGUA = "https://github.com/tesseract-ocr/tessdata/raw/main/{}.traineddata"
URL_LICENZA = "https://raw.githubusercontent.com/tesseract-ocr/tesseract/main/LICENSE"


def trova_installazione(argomento: str | None) -> Path:
    candidati = [Path(argomento)] if argomento else []
    for variabile in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
        if os.environ.get(variabile):
            base = Path(os.environ[variabile])
            candidati += [base / "Tesseract-OCR", base / "Programs" / "Tesseract-OCR"]
    eseguibile = shutil.which("tesseract")
    if eseguibile:
        candidati.append(Path(eseguibile).resolve().parent)
    for c in candidati:
        if (c / "tesseract.exe").is_file() or (c / "tesseract").is_file():
            return c
    sys.exit("Tesseract non trovato: installalo da https://github.com/UB-Mannheim/tesseract/wiki "
             "oppure indica la cartella: python scripts/prepara_tesseract.py \"C:\\percorso\\Tesseract-OCR\"")


def scarica(url: str, destinazione: Path) -> None:
    print(f"  scarico {url}")
    with urllib.request.urlopen(url, timeout=120) as risposta:
        destinazione.write_bytes(risposta.read())


def main() -> None:
    sorgente = trova_installazione(sys.argv[1] if len(sys.argv) > 1 else None)
    print(f"Tesseract trovato in: {sorgente}")
    if DESTINAZIONE.exists():
        shutil.rmtree(DESTINAZIONE)
    DESTINAZIONE.mkdir()

    if (sorgente / "tesseract.exe").is_file():
        # Windows: tesseract.exe e le sue DLL stanno nella stessa cartella di installazione
        for f in sorgente.iterdir():
            if f.is_file() and f.suffix.lower() in (".exe", ".dll") and not f.name.lower().startswith("unins"):
                shutil.copy2(f, DESTINAZIONE / f.name)
    else:
        # Linux/macOS (solo per prove): l'eseguibile usa le librerie di sistema
        shutil.copy2(sorgente / "tesseract", DESTINAZIONE / "tesseract")

    # dati: configurazioni + solo le lingue necessarie
    tessdata_src = sorgente / "tessdata"
    if not tessdata_src.is_dir():  # Linux/macOS: /usr/share/tesseract-ocr/5/tessdata
        tessdata_src = Path(os.environ.get("TESSDATA_PREFIX", "/usr/share/tesseract-ocr/5/tessdata"))
    tessdata = DESTINAZIONE / "tessdata"
    tessdata.mkdir()
    for f in tessdata_src.iterdir():
        if f.is_dir():
            shutil.copytree(f, tessdata / f.name)
        elif f.suffix != ".traineddata":
            shutil.copy2(f, tessdata / f.name)
    for lingua in LINGUE:
        file = tessdata_src / f"{lingua}.traineddata"
        if file.is_file():
            shutil.copy2(file, tessdata / file.name)
        else:
            scarica(URL_LINGUA.format(lingua), tessdata / f"{lingua}.traineddata")
    try:
        scarica(URL_LICENZA, DESTINAZIONE / "LICENSE-tesseract.txt")
    except Exception as e:  # la licenza è Apache 2.0; il download non deve bloccare la creazione
        print(f"  licenza non scaricata ({e})")

    dimensione = sum(f.stat().st_size for f in DESTINAZIONE.rglob("*") if f.is_file()) / 1024 / 1024
    lingue = sorted(f.stem for f in tessdata.glob("*.traineddata"))
    print(f"Pronto: {DESTINAZIONE} ({dimensione:.0f} MB, lingue: {', '.join(lingue)})")


if __name__ == "__main__":
    main()
