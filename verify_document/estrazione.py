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
    "(seleziona la lingua «Italian» durante l'installazione), poi riapri il programma.\n"
    "• Per capire cosa manca: python -m verify_document.diagnosi"
)

# Opzioni di Tesseract: --psm 6 legge la pagina come un blocco unico di righe, così etichetta e
# importo della stessa riga (es. "NETTO IN BUSTA   1.632,00") restano insieme.
CONFIG_OCR = "--psm 6 -c preserve_interword_spaces=1"


class ErroreEstrazione(Exception):
    pass


ESTENSIONI_IMMAGINE = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp"}
MIN_CARATTERI_PAGINA = 30  # sotto questa soglia la pagina è probabilmente una scansione


def estrai_testo(percorso: str | Path, usa_ocr: bool = True) -> str:
    return estrai_documento(percorso, usa_ocr)[0]


def estrai_documento(percorso: str | Path, usa_ocr: bool = True) -> tuple[str, list]:
    """Restituisce (testo, parole con posizione). Per i file .txt le parole non ci sono."""
    p = Path(percorso)
    if not p.exists():
        raise ErroreEstrazione(f"File non trovato: {p}")
    ext = p.suffix.lower()
    if ext in {".txt", ".text"}:
        return p.read_text(encoding="utf-8", errors="replace"), []
    if ext == ".pdf":
        return _da_pdf(p, usa_ocr)
    if ext in ESTENSIONI_IMMAGINE:
        if not usa_ocr:
            raise ErroreEstrazione("Il file è un'immagine: serve l'OCR (rimuovi --no-ocr).")
        from PIL import Image

        return _ocr_parole(Image.open(p))
    raise ErroreEstrazione(f"Formato non supportato: {ext}")


DPI_OCR = 300
SPAZIO_TRA_PAGINE = 50  # punti: le pagine vengono "impilate" in un'unica colonna di coordinate


def _da_pdf(p: Path, usa_ocr: bool) -> tuple[str, list]:
    try:
        import pdfplumber
    except ImportError as e:  # pragma: no cover
        raise ErroreEstrazione("Installa pdfplumber: pip install pdfplumber") from e
    from .layout import Parola

    pagine: list[str] = []
    parole_pagine: list[list[Parola]] = []
    altezze: list[float] = []
    pagine_da_ocr: list[int] = []
    with pdfplumber.open(p) as pdf:
        for i, pagina in enumerate(pdf.pages):
            # layout=True mantiene l'allineamento delle colonne (utile per i cedolini)
            testo = pagina.extract_text(layout=True) or ""
            if len(testo.strip()) < MIN_CARATTERI_PAGINA:
                pagine_da_ocr.append(i)
            pagine.append(testo)
            altezze.append(float(pagina.height))
            parole_pagine.append([Parola(w["text"], w["x0"], w["x1"], w["top"], w["bottom"])
                                  for w in pagina.extract_words(x_tolerance=1.5, y_tolerance=2)])

    errore_ocr = None
    if pagine_da_ocr and usa_ocr:
        for i in pagine_da_ocr:
            try:
                pagine[i], parole_pagine[i] = _ocr_pagina_pdf(p, i)
            except ErroreEstrazione as e:
                errore_ocr = e
    testo = "\n".join(pagine)
    if not testo.strip():
        if not usa_ocr:
            raise ErroreEstrazione("PDF senza testo (scansione): attiva l'opzione OCR per leggerlo.")
        raise errore_ocr or ErroreEstrazione(ISTRUZIONI_TESSERACT)

    parole, scostamento = [], 0.0
    for altezza, parole_pagina in zip(altezze, parole_pagine):
        for w in parole_pagina:
            parole.append(Parola(w.testo, w.x0, w.x1, w.top + scostamento, w.bottom + scostamento))
        scostamento += altezza + SPAZIO_TRA_PAGINE
    return testo, parole


def _ocr_pagina_pdf(p: Path, indice: int) -> tuple[str, list]:
    try:
        import pypdfium2 as pdfium
    except ImportError as e:  # pragma: no cover
        raise ErroreEstrazione("Installa pypdfium2 per l'OCR dei PDF: pip install pypdfium2") from e
    pdf = pdfium.PdfDocument(str(p))
    try:
        immagine = pdf[indice].render(scale=DPI_OCR / 72).to_pil()
    finally:
        pdf.close()
    # coordinate riportate in punti PDF, come per le pagine con testo
    return _ocr_parole(immagine, pixel_per_punto=DPI_OCR / 72)


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
    # "320.15" -> "320,15", "1.632.00" -> "1.632,00" (punto letto al posto della virgola; non tocca le date)
    testo = re.sub(r"(?<![\d.,])(\d{1,3}(?:\.\d{3})*)\.(\d{2})(?!\.?\d)", r"\1,\2", testo)
    # "1. 632,00" o "1.632, 00" -> "1.632,00"
    testo = re.sub(r"(?<=\d)([.,]) (?=\d{2,3}\b)", r"\1", testo)
    # simbolo dell'euro letto come "€", "E" o "C" attaccato all'importo
    testo = re.sub(r"(?<![A-Za-z])[EC€](?=\s?\d{1,3}(?:\.\d{3})*,\d{2}\b)", "€", testo)
    return testo


VARIANTI_OCR = (("pulita", 6), ("pulita", 11), ("grigia", 6))
SOGLIA_FIDUCIA = 35


def _combina_letture(letture: list[list[tuple]]) -> list[tuple]:
    """La prima lettura è la principale; le altre aggiungono solo parole dove la principale non ha letto nulla."""
    def sovrapposte(a, b):
        _, _, x, y, w, h = a
        _, _, x2, y2, w2, h2 = b
        ix = min(x + w, x2 + w2) - max(x, x2)
        iy = min(y + h, y2 + h2) - max(y, y2)
        return ix > 0 and iy > 0 and ix * iy > 0.2 * min(w * h, w2 * h2)

    scelte = list(letture[0]) if letture else []
    for lettura in letture[1:]:
        aggiunte = [c for c in lettura if c[1] >= 60 and not any(sovrapposte(c, s) for s in scelte)]
        scelte += aggiunte
    return scelte


def _ocr_immagine(immagine) -> str:
    return _ocr_parole(immagine)[0]


def _ocr_parole(immagine, pixel_per_punto: float | None = None) -> tuple[str, list]:
    """OCR con pre-elaborazione dell'immagine; restituisce (testo con colonne, parole con posizione)."""
    try:
        import pytesseract
    except ImportError as e:
        raise ErroreEstrazione(ISTRUZIONI_TESSERACT) from e
    percorso, lingua = trova_tesseract()
    if percorso is None:
        raise ErroreEstrazione(ISTRUZIONI_TESSERACT)
    from PIL import ImageOps

    from .layout import Parola, testo_da_parole
    from .preelaborazione import prepara_per_ocr

    grigia = ImageOps.exif_transpose(immagine).convert("L")
    larghezza_originale = grigia.width
    varianti = prepara_per_ocr(grigia, pytesseract, lingua)
    fattore = varianti.fattore  # ingrandimento applicato
    if pixel_per_punto is None:  # immagini (JPG/PNG): coordinate riportate a "punti" di un A4
        pixel_per_punto = larghezza_originale / 595.0

    # Lettura principale sull'immagine pulita (senza linee); le altre letture riempiono solo le zone in cui la
    # principale non ha riconosciuto nulla (es. testo molto chiaro rimasto fuori dalla soglia).
    letture = []
    for img, psm in VARIANTI_OCR:
        candidati = []
        immagine_ocr = varianti.pulita if img == "pulita" else varianti.grigia
        dati = pytesseract.image_to_data(immagine_ocr, lang=lingua or None, output_type=pytesseract.Output.DICT,
                                         config=f"--psm {psm} -c preserve_interword_spaces=1")
        for testo, conf, x, y, w, h in zip(dati["text"], dati["conf"], dati["left"], dati["top"],
                                           dati["width"], dati["height"]):
            testo, conf = (testo or "").strip(), float(conf)
            if not testo or conf < SOGLIA_FIDUCIA or w <= 0 or h <= 0:
                continue
            if not re.search(r"[A-Za-zÀ-ÿ0-9]", testo):
                continue  # residui di linee e macchie ("|", "—", "_")
            candidati.append((testo, conf, x, y, w, h))
        letture.append(candidati)
    migliori = _combina_letture(letture)

    scala = 1.0 / (fattore * pixel_per_punto)
    parole = [Parola(normalizza_ocr(t), x * scala, (x + w) * scala, y * scala, (y + h) * scala)
              for t, _, x, y, w, h in migliori]
    return normalizza_ocr(testo_da_parole(parole)), parole
