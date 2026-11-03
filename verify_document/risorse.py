"""Percorsi dei file inclusi nel programma (esempi, icona), sia dal codice sorgente sia dal .exe."""

from __future__ import annotations

import sys
from pathlib import Path


def cartella_base() -> Path:
    # nel .exe creato con PyInstaller i file sono estratti in sys._MEIPASS
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent.parent


def risorsa(relativo: str) -> Path:
    return cartella_base() / relativo


def e_eseguibile() -> bool:
    return bool(getattr(sys, "frozen", False))
