"""Impostazioni dell'utente (dati dello studio e logo per il report PDF).

Salvate in un file JSON nella cartella dell'utente: ~/.verify_document/impostazioni.json
(su Windows: C:\\Users\\<nome>\\.verify_document\\impostazioni.json).
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
}


def carica(percorso: Path | None = None) -> dict:
    p = percorso or FILE
    dati = dict(PREDEFINITE)
    try:
        dati.update({k: v for k, v in json.loads(p.read_text(encoding="utf-8")).items() if k in PREDEFINITE})
    except (OSError, ValueError):
        pass
    return dati


def salva(dati: dict, percorso: Path | None = None) -> Path:
    """Salva i valori indicati; quelli non indicati restano come erano."""
    p = percorso or FILE
    p.parent.mkdir(parents=True, exist_ok=True)
    pulite = carica(p)
    pulite.update({k: str(v if v is not None else "") for k, v in dati.items() if k in PREDEFINITE})
    p.write_text(json.dumps(pulite, ensure_ascii=False, indent=2), encoding="utf-8")
    return p
