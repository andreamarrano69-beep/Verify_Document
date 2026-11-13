"""Impostazioni dell'utente (dati dello studio e logo per il report PDF, cartella condivisa, assistente AI).

Salvate in un file JSON nella cartella dell'utente: ~/.verify_document/impostazioni.json
(su Windows: C:\\Users\\<nome>\\.verify_document\\impostazioni.json).

Impostazioni dell'ufficio: il file «config_ufficio.json» nella cartella del programma (scritto dal setup,
es. con la cartella condivisa del server) fornisce i valori iniziali per tutti gli utenti del PC;
ciò che l'utente salva nelle sue impostazioni ha la precedenza.
"""

from __future__ import annotations

import json
from pathlib import Path

CARTELLA = Path.home() / ".verify_document"
FILE = CARTELLA / "impostazioni.json"

PREDEFINITE = {
    "studio": "",        # nome dello studio / agenzia
    "indirizzo": "",
    "contatti": "",      # telefono, email, sito
    "partita_iva": "",
    "operatore": "",     # chi firma il report
    "logo": "",          # percorso di un'immagine PNG/JPG
    "note": "",          # testo aggiuntivo in fondo al report
    "cartella_apertura": "",         # cartella proposta da «Apri documenti» (es. scansioni)
    "ultima_cartella": "",           # ultima cartella usata (se cartella_apertura è vuota)
    "archivio": "",                  # cartella dell'archivio documenti (vuota = predefinita)
    "archivia_automaticamente": "1",  # "1" = salva una copia dei documenti aperti
    "oscura_dati_esportati": "1",     # "1" = report PDF ed esportazioni senza dati personali
    # --- ufficio: cartella condivisa del server (archivio clienti, regole Compass, documenti per l'AI) ---
    "cartella_condivisa": "",        # es. \\\\SERVER\\Condivisa\\VerifyDocument (vuota = niente condivisione)
    # --- assistente AI (facoltativo, Ollama sul PC o su un altro PC della rete) ---
    "ollama_host": "http://localhost:11434",
    "modello_ai": "qwen2.5:1.5b",          # 8 GB di RAM: 1.5b; 16 GB: qwen2.5:3b
    "modello_embedding": "nomic-embed-text",
}

FILE_UFFICIO = "config_ufficio.json"


def file_ufficio() -> Path:
    """config_ufficio.json accanto al programma (.exe) o nella cartella del progetto."""
    import sys

    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / FILE_UFFICIO
    return Path(__file__).resolve().parent.parent / FILE_UFFICIO


def _leggi(p: Path) -> dict:
    try:
        return {k: v for k, v in json.loads(p.read_text(encoding="utf-8")).items() if k in PREDEFINITE}
    except (OSError, ValueError):
        return {}


def carica(percorso: Path | None = None) -> dict:
    p = percorso or FILE
    dati = dict(PREDEFINITE)
    ufficio = _leggi(file_ufficio()) if percorso is None else {}  # i file di prova non usano l'ufficio
    dati.update({k: v for k, v in ufficio.items() if v not in ("", None)})
    # un valore vuoto dell'utente non cancella quello dell'ufficio (es. cartella condivisa)
    dati.update({k: v for k, v in _leggi(p).items() if v not in ("", None) or not ufficio.get(k)})
    return dati


def salva(dati: dict, percorso: Path | None = None) -> Path:
    """Salva i valori indicati; quelli non indicati restano come erano."""
    p = percorso or FILE
    p.parent.mkdir(parents=True, exist_ok=True)
    # solo i valori scelti dall'utente: i predefiniti e quelli dell'ufficio non vengono copiati nel file,
    # così un cambio della configurazione dell'ufficio arriva a tutti gli utenti
    pulite = _leggi(p)
    pulite.update({k: str(v if v is not None else "") for k, v in dati.items() if k in PREDEFINITE})
    p.write_text(json.dumps(pulite, ensure_ascii=False, indent=2), encoding="utf-8")
    return p
