"""Diagnosi dell'OCR: spiega perché Tesseract non viene trovato.

    python -m verify_document.diagnosi
"""

from __future__ import annotations

import os
import sys


def diagnosi_ocr() -> list[str]:
    righe = [f"Python in uso: {sys.executable}"]
    in_venv = sys.prefix != getattr(sys, "base_prefix", sys.prefix)
    righe.append(f"Ambiente virtuale (.venv) attivo: {'sì' if in_venv else 'NO'}")
    try:
        import pytesseract
        righe.append(f"Libreria pytesseract: installata ({getattr(pytesseract, '__version__', '?')})")
    except ImportError:
        righe.append("Libreria pytesseract: NON INSTALLATA  ->  esegui:  pip install -r requirements.txt")
        return righe

    from .estrazione import _candidati_tesseract

    trovato = False
    for candidato in _candidati_tesseract():
        if not candidato.is_file():
            righe.append(f"  [assente]  {candidato}")
            continue
        cartella_dati = candidato.parent / "tessdata"
        ambiente = dict(os.environ)
        if cartella_dati.is_dir() and candidato.parent.name == "tesseract":
            os.environ["TESSDATA_PREFIX"] = str(cartella_dati)
        pytesseract.pytesseract.tesseract_cmd = str(candidato)
        try:
            versione = pytesseract.get_tesseract_version()
            lingue = sorted(pytesseract.get_languages(config=""))
            righe.append(f"  [OK]       {candidato}  (versione {versione}, lingue: {', '.join(lingue)})")
            if "ita" not in lingue:
                righe.append("             manca l'italiano  ->  esegui:  python scripts\\prepara_tesseract.py")
            trovato = True
        except Exception as e:
            righe.append(f"  [ERRORE]   {candidato}: {type(e).__name__}: {e}")
        finally:
            os.environ.clear()
            os.environ.update(ambiente)
    righe.append("ESITO: OCR utilizzabile" if trovato else "ESITO: OCR NON utilizzabile (vedi righe sopra)")
    return righe


if __name__ == "__main__":
    print("\n".join(diagnosi_ocr()))
