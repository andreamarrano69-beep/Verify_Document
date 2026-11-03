"""Estrazione del testo dai documenti (PDF, immagini, file di testo).

Strategia:
1. PDF "nativi" (generati da software paghe / Entratel): testo estratto con pdfplumber.
2. PDF scansionati o immagini (JPG/PNG): OCR con Tesseract, se installato.
Tutto avviene in locale: nessun dato lascia il computer.
"""

from __future__ import annotations

from pathlib import Path


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
        raise ErroreEstrazione(
            "Nessun testo trovato nel PDF (probabile scansione). Installa Tesseract per l'OCR."
        )
    return testo


def _ocr_pagina_pdf(p: Path, indice: int) -> str:
    try:
        import pypdfium2 as pdfium
    except ImportError as e:  # pragma: no cover
        raise ErroreEstrazione("Installa pypdfium2 per l'OCR dei PDF: pip install pypdfium2") from e
    pdf = pdfium.PdfDocument(str(p))
    immagine = pdf[indice].render(scale=300 / 72).to_pil()  # ~300 DPI
    return _ocr_immagine(immagine)


def _ocr_immagine(immagine) -> str:
    try:
        import pytesseract
    except ImportError as e:
        raise ErroreEstrazione(
            "OCR non disponibile: installa Tesseract (con lingua 'ita') e 'pip install pytesseract'."
        ) from e
    try:
        return pytesseract.image_to_string(immagine, lang="ita")
    except pytesseract.TesseractError:
        return pytesseract.image_to_string(immagine)
    except pytesseract.TesseractNotFoundError as e:
        raise ErroreEstrazione("Programma Tesseract non trovato nel sistema.") from e
