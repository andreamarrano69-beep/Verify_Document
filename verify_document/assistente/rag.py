"""Ricerca nei documenti dell'ufficio (OAM, Compass, note) e risposta con l'AI locale.

- documenti: <cartella condivisa>/documenti_ai  (sottocartelle OAM, Compass, Note, ...)
  oppure ~/.verify_document/documenti_ai se la cartella condivisa non è impostata
- testo letto con lo stesso motore del programma (PDF con testo, scansioni con OCR, immagini, .txt/.md)
  più i file Word (.docx)
- l'indice (pezzi di testo + vettori) è salvato nella cartella dei documenti, così lo crea un solo PC e gli altri
  lo riusano; una copia resta anche sul PC (se la cartella condivisa non è raggiungibile)
- a ogni domanda: i pezzi più simili alla domanda (solo dell'area scelta: OAM, Compass o tutti) vengono dati
  all'AI con l'istruzione di rispondere SOLO da quei documenti e di citare la fonte
"""

from __future__ import annotations

import json
import os
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator

from . import ollama_http

VERSIONE_INDICE = 1
ESTENSIONI = {".pdf", ".docx", ".txt", ".md", ".png", ".jpg", ".jpeg", ".tif", ".tiff"}
NOME_INDICE = ".indice_ai.json"
DIMENSIONE_PEZZO = 800
SOVRAPPOSIZIONE = 150
PEZZI_DA_USARE = 4

# pulsante -> prima cartella dentro documenti_ai (None = tutti i documenti)
AREE = {"OAM": "OAM", "Compass": "Compass", "Generale": None}

ISTRUZIONI = """Sei un assistente per un collaboratore di agente in attività finanziaria in Italia.
Rispondi in italiano, in modo chiaro e preciso.
Usa SOLO le informazioni contenute nei DOCUMENTI forniti.
Se la risposta non è nei documenti, dillo chiaramente: "Non trovo questa informazione nei documenti."
Non inventare numeri, tassi, scadenze o norme.
Ogni documento ha un'etichetta con il suo percorso: se inizia con "OAM" è una regola dell'Organismo Agenti e
Mediatori; se inizia con "Compass" è un documento di Compass (contratti, condizioni, criteri, privacy).
Tieni distinte le due cose e dì da quale fonte arriva ogni informazione.
Alla fine indica da quale documento hai preso l'informazione."""

ISTRUZIONI_SPIEGA = (
    "Sei un assistente per un collaboratore che istruisce pratiche di cessione del quinto. Ti viene dato il risultato "
    "di una verifica già calcolata. Riassumilo in italiano in massimo 8 righe: con quali compagnie la pratica è "
    "fattibile, i motivi principali per cui le altre non lo sono, e cosa conviene fare (es. ridurre la durata, chiedere "
    "pre-accettazione, recuperare documenti). NON rifare calcoli e NON inventare numeri: usa solo quelli presenti.")


@dataclass
class Configurazione:
    cartella: Path                 # cartella dei documenti
    host: str = "http://localhost:11434"
    modello: str = "qwen2.5:1.5b"
    modello_embedding: str = "nomic-embed-text"
    indice_locale: Path | None = None


def configurazione(impostazioni: dict) -> Configurazione:
    base = Path.home() / ".verify_document"
    condivisa = impostazioni.get("cartella_condivisa") or ""
    cartella = Path(condivisa) / "documenti_ai" if condivisa else base / "documenti_ai"
    return Configurazione(cartella=cartella, host=impostazioni.get("ollama_host") or "http://localhost:11434",
                          modello=impostazioni.get("modello_ai") or "qwen2.5:1.5b",
                          modello_embedding=impostazioni.get("modello_embedding") or "nomic-embed-text",
                          indice_locale=base / "indice_ai.json")


# ------------------------------------------------------------------ lettura documenti
def _testo_docx(p: Path) -> str:
    with zipfile.ZipFile(p) as z:
        xml = z.read("word/document.xml").decode("utf-8", errors="ignore")
    xml = re.sub(r"</w:p>", "\n", xml)
    return re.sub(r"<[^>]+>", "", xml)


def leggi_file(p: Path, usa_ocr: bool = True) -> str:
    est = p.suffix.lower()
    if est in (".txt", ".md"):
        return p.read_text(encoding="utf-8", errors="ignore")
    if est == ".docx":
        return _testo_docx(p)
    from ..estrazione import estrai_testo

    return estrai_testo(p, usa_ocr=usa_ocr)


def dividi_in_pezzi(testo: str) -> list[str]:
    testo = " ".join(testo.split())
    pezzi, inizio = [], 0
    while inizio < len(testo):
        pezzi.append(testo[inizio:inizio + DIMENSIONE_PEZZO])
        inizio += DIMENSIONE_PEZZO - SOVRAPPOSIZIONE
    return [p for p in pezzi if len(p.strip()) > 50]


def elenco_file(cartella: Path) -> dict[str, float]:
    """Percorso relativo -> data di modifica (relativo: uguale da tutti i PC, anche con lettere di unità diverse)."""
    if not cartella.is_dir():
        return {}
    out = {}
    for f in sorted(cartella.rglob("*")):
        if f.is_file() and f.suffix.lower() in ESTENSIONI and not f.name.startswith("."):
            out[f.relative_to(cartella).as_posix()] = round(os.path.getmtime(f), 1)
    return out


# ------------------------------------------------------------------ indice
@dataclass
class Indice:
    pezzi: list[dict]
    matrice: object   # numpy array

    def documenti(self, area: str = "Generale") -> int:
        return len({self.pezzi[i]["fonte"] for i in self.indici_area(area)})

    def indici_area(self, area: str) -> list[int]:
        cartella = AREE.get(area)
        if cartella is None:
            return list(range(len(self.pezzi)))
        return [i for i, p in enumerate(self.pezzi) if p["fonte"].split("/")[0].lower() == cartella.lower()]


def _firma(cfg: Configurazione) -> dict:
    return {"versione": VERSIONE_INDICE, "modello": cfg.modello_embedding, "file": elenco_file(cfg.cartella)}


def _leggi_indice(p: Path | None) -> dict | None:
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p and p.is_file() else None
    except (OSError, ValueError):
        return None


def _scrivi_indice(p: Path, dati: dict) -> None:
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(p.name + ".tmp")
        tmp.write_text(json.dumps(dati), encoding="utf-8")
        os.replace(tmp, p)  # scrittura «tutta o niente»: un altro PC non legge mai un file a metà
    except OSError:
        pass


def _calcola_vettori(cfg: Configurazione, testi: list[str], prefisso: str) -> list[list[float]]:
    vettori = []
    for i in range(0, len(testi), 16):
        vettori += ollama_http.embed(cfg.host, cfg.modello_embedding, [prefisso + t for t in testi[i:i + 16]])
    return vettori


def carica_indice(cfg: Configurazione, avanzamento: Callable[[str], None] = lambda _t: None,
                  usa_ocr: bool = True) -> Indice:
    """Indice aggiornato: riusa quello condiviso o locale se i documenti non sono cambiati, altrimenti lo ricrea."""
    import numpy as np

    firma = _firma(cfg)
    if not firma["file"]:
        raise FileNotFoundError(f"Nessun documento in {cfg.cartella}. Aggiungine con «+ Documento» o «+ Nota».")
    condiviso = cfg.cartella / NOME_INDICE
    for p in (condiviso, cfg.indice_locale):
        dati = _leggi_indice(p)
        if dati and dati.get("firma") == firma:
            avanzamento(f"Indice caricato ({len(dati['pezzi'])} pezzi di testo).")
            return Indice(dati["pezzi"], np.array(dati["vettori"], dtype="float32"))

    # ricrea, riusando i vettori dei file non cambiati
    vecchio = _leggi_indice(condiviso) or _leggi_indice(cfg.indice_locale) or {}
    gia = {}
    if vecchio.get("firma", {}).get("modello") == cfg.modello_embedding:
        for pezzo, vettore in zip(vecchio.get("pezzi", []), vecchio.get("vettori", [])):
            if vecchio["firma"]["file"].get(pezzo["fonte"]) == firma["file"].get(pezzo["fonte"]):
                gia.setdefault(pezzo["fonte"], []).append((pezzo, vettore))

    pezzi, vettori, nuovi = [], [], []
    totale = len(firma["file"])
    for n, rel in enumerate(firma["file"], start=1):
        if rel in gia:
            for pezzo, vettore in gia[rel]:
                pezzi.append(pezzo)
                vettori.append(vettore)
            continue
        avanzamento(f"Leggo {n}/{totale}: {rel}")
        try:
            testo = leggi_file(cfg.cartella / rel, usa_ocr)
        except Exception as e:  # file illeggibile: si salta, l'avviso resta nella barra di stato
            avanzamento(f"Non leggibile: {rel} ({e})")
            continue
        for t in dividi_in_pezzi(testo):
            nuovi.append({"fonte": rel, "testo": t})

    if nuovi:
        avanzamento(f"Preparo la ricerca su {len(nuovi)} pezzi di testo nuovi (la prima volta può richiedere minuti)…")
        vettori_nuovi = _calcola_vettori(cfg, [p["testo"] for p in nuovi], "search_document: ")
        pezzi += nuovi
        vettori += vettori_nuovi
    if not pezzi:
        raise ValueError("Nessun testo letto dai documenti (scansioni senza OCR?).")

    dati = {"firma": firma, "pezzi": pezzi, "vettori": vettori}
    _scrivi_indice(condiviso, dati)
    if cfg.indice_locale:
        _scrivi_indice(cfg.indice_locale, dati)
    avanzamento(f"Indice pronto: {len({p['fonte'] for p in pezzi})} documenti.")
    return Indice(pezzi, np.array(vettori, dtype="float32"))


# ------------------------------------------------------------------ domande
def cerca(cfg: Configurazione, indice: Indice, domanda: str, area: str = "Generale") -> list[dict]:
    import numpy as np

    scelti = indice.indici_area(area)
    if not scelti:
        return []
    q = np.array(_calcola_vettori(cfg, [domanda], "search_query: ")[0], dtype="float32")
    m = indice.matrice[scelti]
    punteggi = m @ q / (np.linalg.norm(m, axis=1) * np.linalg.norm(q) + 1e-10)
    migliori = np.argsort(punteggi)[::-1][:PEZZI_DA_USARE]
    return [indice.pezzi[scelti[i]] for i in migliori]


def rispondi(cfg: Configurazione, domanda: str, trovati: list[dict], area: str) -> Iterator[str]:
    contesto = "\n\n".join(f"[{p['fonte']}]\n{p['testo']}" for p in trovati)
    messaggi = [{"role": "system", "content": ISTRUZIONI},
                {"role": "user", "content": f"AREA SCELTA: {area}\n\nDOCUMENTI:\n{contesto}\n\nDOMANDA: {domanda}"}]
    return ollama_http.chat(cfg.host, cfg.modello, messaggi)


def spiega_verifica(cfg: Configurazione, risultato: str) -> Iterator[str]:
    return ollama_http.chat(cfg.host, cfg.modello, [{"role": "system", "content": ISTRUZIONI_SPIEGA},
                                                    {"role": "user", "content": risultato}])
