"""Estrazione del testo dai documenti (PDF, immagini, file di testo).

Strategia:
1. PDF "nativi" (generati da software paghe / Entratel): testo estratto con pdfplumber.
2. PDF scansionati o immagini (JPG/PNG): OCR con Tesseract.
   Tesseract viene cercato in quest'ordine: incluso nel programma (.exe), nel PATH,
   nelle cartelle di installazione standard di Windows.
Tutto avviene in locale: nessun dato lascia il computer.
"""

from __future__ import annotations

import os
import re
import shutil
from functools import lru_cache
from pathlib import Path

ISTRUZIONI_TESSERACT = (
    "Questo documento è una scansione o una foto: per leggerlo serve l'OCR (Tesseract).\n"
    "• Programma .exe: usa la versione più recente, che include già Tesseract.\n"
    "• Da Python: installa Tesseract da https://github.com/UB-Mannheim/tesseract/wiki "
    "(seleziona la lingua «Italian» durante l'installazione), poi riapri il programma."
)

# Opzioni di Tesseract: --psm 6 legge la pagina come un blocco unico di righe, così etichetta e
# importo della stessa riga (es. "NETTO IN BUSTA   1.632,00") restano insieme.
CONFIG_OCR = "--psm 6 -c preserve_interword_spaces=1"


class ErroreEstrazione(Exception):
    pass


ESTENSIONI_IMMAGINE = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp"}
MIN_CARATTERI_PAGINA = 30  # sotto questa soglia la pagina è probabilmente una scansione


def estrai_testo(percorso: str | Path, usa_ocr: bool = True) -> str:
    p = Path(percorso)
    if not p.exists():
        raise ErroreEstrazione(f"File non trovato: {p}")
    ext = p.suffix.lower()
    if ext in {".txt", ".text"}:
        return p.read_text(encoding="utf-8", errors="replace")
    if ext == ".pdf":
        return _testo_da_pdf(p, usa_ocr)
    if ext in ESTENSIONI_IMMAGINE:
        if not usa_ocr:
            raise ErroreEstrazione("Il file è un'immagine: serve l'OCR (rimuovi --no-ocr).")
        from PIL import Image

        return _ocr_immagine(Image.open(p))
    raise ErroreEstrazione(f"Formato non supportato: {ext}")


def _testo_da_pdf(p: Path, usa_ocr: bool) -> str:
    try:
        import pdfplumber
    except ImportError as e:  # pragma: no cover
        raise ErroreEstrazione("Installa pdfplumber: pip install pdfplumber") from e

    pagine: list[str] = []
    pagine_da_ocr: list[int] = []
    with pdfplumber.open(p) as pdf:
        for i, pagina in enumerate(pdf.pages):
            # layout=True mantiene l'allineamento delle colonne (utile per i cedolini)
            testo = pagina.extract_text(layout=True) or ""
            if len(testo.strip()) < MIN_CARATTERI_PAGINA:
                pagine_da_ocr.append(i)
            pagine.append(testo)

    if pagine_da_ocr and usa_ocr:
        for i in pagine_da_ocr:
            try:
                pagine[i] = _ocr_pagina_pdf(p, i)
            except ErroreEstrazione:
                if not any(t.strip() for t in pagine):
                    raise
    testo = "\n".join(pagine)
    if not testo.strip():
        if not usa_ocr:
            raise ErroreEstrazione("PDF senza testo (scansione): attiva l'opzione OCR per leggerlo.")
        raise ErroreEstrazione(ISTRUZIONI_TESSERACT)
    return testo


def _ocr_pagina_pdf(p: Path, indice: int) -> str:
    try:
        import pypdfium2 as pdfium
    except ImportError as e:  # pragma: no cover
        raise ErroreEstrazione("Installa pypdfium2 per l'OCR dei PDF: pip install pypdfium2") from e
    pdf = pdfium.PdfDocument(str(p))
    immagine = pdf[indice].render(scale=300 / 72).to_pil()  # ~300 DPI
    return _ocr_immagine(immagine)


def _candidati_tesseract() -> list[Path]:
    from .risorse import risorsa

    nome = "tesseract.exe" if os.name == "nt" else "tesseract"
    candidati = [risorsa("tesseract") / nome]  # incluso nel programma
    nel_path = shutil.which("tesseract")
    if nel_path:
        candidati.append(Path(nel_path))
    for variabile in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
        base = os.environ.get(variabile)
        if base:
            candidati += [Path(base) / "Tesseract-OCR" / nome, Path(base) / "Programs" / "Tesseract-OCR" / nome]
    return candidati


@lru_cache(maxsize=1)
def trova_tesseract() -> tuple[str | None, str]:
    """Restituisce (percorso di tesseract, lingue da usare) oppure (None, "")."""
    try:
        import pytesseract
    except ImportError:
        return None, ""
    for candidato in _candidati_tesseract():
        if not candidato.is_file():
            continue
        cartella_dati = candidato.parent / "tessdata"
        if cartella_dati.is_dir() and candidato.parent.name == "tesseract":
            os.environ["TESSDATA_PREFIX"] = str(cartella_dati)  # dati inclusi nel programma
        pytesseract.pytesseract.tesseract_cmd = str(candidato)
        try:
            lingue = set(pytesseract.get_languages(config=""))
        except Exception:
            continue
        lingua = "ita" if "ita" in lingue else ("eng" if "eng" in lingue else "")
        return str(candidato), lingua
    return None, ""


def ocr_disponibile() -> bool:
    return trova_tesseract()[0] is not None


_CIFRA_O = re.compile(r"(?<=[\d.,])[Oo](?=[\d.,])|(?<=\d)[Oo](?=\b)|(?<=\b)[Oo](?=[.,]\d)")
_CIFRA_1 = re.compile(r"(?<=[\d.,])[lI|](?=[\d.,])")


def normalizza_ocr(testo: str) -> str:
    """Corregge gli errori tipici dell'OCR sui numeri (O→0, l/I→1, spazi dentro gli importi)."""
    testo = _CIFRA_O.sub("0", testo)
    testo = _CIFRA_1.sub("1", testo)
    # "1. 632,00" o "1.632, 00" -> "1.632,00"
    testo = re.sub(r"(?<=\d)([.,]) (?=\d{2,3}\b)", r"\1", testo)
    # simbolo dell'euro letto come "€", "E" o "C" attaccato all'importo
    testo = re.sub(r"(?<![A-Za-z])[EC€](?=\s?\d{1,3}(?:\.\d{3})*,\d{2}\b)", "€", testo)
    return testo


def _ocr_immagine(immagine) -> str:
    try:
        import pytesseract
    except ImportError as e:
        raise ErroreEstrazione(ISTRUZIONI_TESSERACT) from e
    percorso, lingua = trova_tesseract()
    if percorso is None:
        raise ErroreEstrazione(ISTRUZIONI_TESSERACT)
    from PIL import ImageOps

    immagine = ImageOps.exif_transpose(immagine).convert("L")  # foto da telefono: rotazione e scala di grigi
    if immagine.width < 1500:  # immagini piccole: ingrandire migliora molto l'OCR
        fattore = 1500 / immagine.width
        immagine = immagine.resize((int(immagine.width * fattore), int(immagine.height * fattore)))
    try:
        testo = pytesseract.image_to_string(immagine, lang=lingua or None, config=CONFIG_OCR)
    except pytesseract.TesseractError:
        testo = pytesseract.image_to_string(immagine, config=CONFIG_OCR)
    return normalizza_ocr(testo)
