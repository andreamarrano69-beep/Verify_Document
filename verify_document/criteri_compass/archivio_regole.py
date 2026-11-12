"""Regole Compass: incluse nel programma oppure aggiornate dalla cartella condivisa dell'ufficio.

- le regole incluse sono i moduli Python in criteri_compass/regole/ (commentati con le pagine dei PDF)
- per aggiornare i criteri su tutti i PC senza ricreare il programma: in ⚙ Impostazioni → «Esporta le regole
  nella cartella condivisa» si creano i file  <cartella condivisa>/regole/<nome>.json ; da quel momento tutti
  i PC leggono quei file (si modificano con un editor di testo, es. Blocco note)
- si usa JSON e non Python perché un file nella cartella condivisa non deve poter eseguire codice sui PC
- se un .json è illeggibile si usano le regole incluse e l'errore viene segnalato (ultimo_errore)
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from types import SimpleNamespace

PACCHETTO = __package__ + ".regole"
CARTELLA_JSON = "regole"            # sottocartella della cartella condivisa
ultimo_errore: dict[str, str] = {}  # nome regole -> messaggio (per avvisare nell'interfaccia)


def _a_tuple(valore):
    """JSON non ha le tuple: le liste tornano tuple (età e anzianità sono confrontate come (anni, mesi, giorni))."""
    if isinstance(valore, list):
        return tuple(_a_tuple(v) for v in valore)
    if isinstance(valore, dict):
        return {k: _a_tuple(v) for k, v in valore.items()}
    return valore


def _pubblici(modulo) -> dict:
    """Costanti del modulo da esportare (REQUISITI_GENERALI, COMPAGNIE, note...)."""
    return {k: v for k, v in vars(modulo).items()
            if k.isupper() and not k.startswith("_") and isinstance(v, (dict, list, tuple, str, int, float))}


def incluse(nome: str):
    return importlib.import_module(f"{PACCHETTO}.{nome}")


def file_json(nome: str, cartella: str | Path | None) -> Path | None:
    if not cartella:
        return None
    return Path(cartella) / CARTELLA_JSON / f"{nome}.json"


def carica(nome: str, cartella: str | Path | None = None):
    """Regole con gli stessi attributi del modulo (REQUISITI_GENERALI, COMPAGNIE, ...)."""
    ultimo_errore.pop(nome, None)
    percorso = file_json(nome, cartella)
    if percorso is not None:
        try:
            if percorso.is_file():
                dati = json.loads(percorso.read_text(encoding="utf-8"))
                regole = SimpleNamespace(**{k: _a_tuple(v) for k, v in dati.items() if not k.startswith("_")})
                if not hasattr(regole, "REQUISITI_GENERALI") or not hasattr(regole, "COMPAGNIE"):
                    raise ValueError("mancano REQUISITI_GENERALI o COMPAGNIE")
                regole._origine = str(percorso)
                return regole
        except (OSError, ValueError) as e:
            ultimo_errore[nome] = f"{percorso}: {e} — uso le regole incluse nel programma"
    modulo = incluse(nome)
    return modulo


def origine(regole) -> str:
    return getattr(regole, "_origine", "regole incluse nel programma")


def esporta(cartella: str | Path, nomi: list[str], sovrascrivi: bool = False) -> list[Path]:
    """Scrive le regole incluse come .json nella cartella condivisa. Restituisce i file scritti."""
    destinazione = Path(cartella) / CARTELLA_JSON
    destinazione.mkdir(parents=True, exist_ok=True)
    scritti = []
    for nome in nomi:
        f = destinazione / f"{nome}.json"
        if f.exists() and not sovrascrivi:
            continue
        modulo = incluse(nome)
        dati = {"_descrizione": (modulo.__doc__ or "").strip(),
                "_nota": "Età e anzianità: [anni, mesi, giorni]. Livelli: OK, PREACC, KO, VERIFICA. "
                         "Dopo una modifica premere «Aggiorna» o riaprire la verifica.",
                **_pubblici(modulo)}
        f.write_text(json.dumps(dati, ensure_ascii=False, indent=2), encoding="utf-8")
        scritti.append(f)
    return scritti
