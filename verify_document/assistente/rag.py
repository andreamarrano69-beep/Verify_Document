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
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator

from . import ollama_http

VERSIONE_INDICE = 2
ESTENSIONI = {".pdf", ".docx", ".txt", ".md", ".png", ".jpg", ".jpeg", ".tif", ".tiff"}
# indice in formato numpy compresso (vettori float16): circa 10 volte più piccolo e veloce del vecchio JSON
NOME_INDICE = ".indice_ai.npz"
NOME_INDICE_VECCHIO = ".indice_ai.json"   # versione 0.13.0: si riusa una volta e poi si cancella
LOTTO_EMBEDDING = 32
SALVA_OGNI_SECONDI = 60
DIMENSIONE_PEZZO = 800
SOVRAPPOSIZIONE = 150
PEZZI_DA_USARE = 4

# gruppi di documenti: ognuno ha il suo indice e si prepara solo quando serve
#   OAM      -> documenti_ai/OAM/...
#   Compass  -> documenti_ai/Compass/...
#   Generale -> tutto il resto (Generale, Note, altre cartelle)
GRUPPI = ("OAM", "Compass", "Generale")
# pulsante -> gruppi in cui cercare
AREE = {"OAM": ("OAM",), "Compass": ("Compass",), "Generale": ("Generale",), "Tutti": GRUPPI}


def gruppo_di(rel: str) -> str:
    primo = rel.split("/")[0].lower()
    return {"oam": "OAM", "compass": "Compass"}.get(primo, "Generale")

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
                          indice_locale=base / "indice_ai.npz")


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

    def documenti(self, area: str = "Tutti") -> int:
        return len({self.pezzi[i]["fonte"] for i in self.indici_area(area)})

    def indici_area(self, area: str) -> list[int]:
        gruppi = AREE.get(area, GRUPPI)
        return [i for i, p in enumerate(self.pezzi) if gruppo_di(p["fonte"]) in gruppi]

    @staticmethod
    def unisci(indici: list["Indice"]) -> "Indice":
        import numpy as np

        indici = [i for i in indici if i.pezzi]
        if not indici:
            return Indice([], np.zeros((0, 1), dtype="float32"))
        return Indice([p for i in indici for p in i.pezzi], np.concatenate([i.matrice for i in indici]))


def _firma(cfg: Configurazione, gruppo: str | None = None) -> dict:
    file = elenco_file(cfg.cartella)
    if gruppo:
        file = {rel: t for rel, t in file.items() if gruppo_di(rel) == gruppo}
    return {"versione": VERSIONE_INDICE, "modello": cfg.modello_embedding, "file": file}


def _leggi_indice(p: Path | None) -> dict | None:
    """{"firma", "pezzi", "vettori"} dal file .npz (o dal vecchio .json); None se manca o è rovinato."""
    import numpy as np

    try:
        if not p or not p.is_file():
            return None
        with open(p, "rb") as f:
            zip_npz = f.read(2) == b"PK"
        if not zip_npz:   # vecchio formato JSON
            return json.loads(p.read_text(encoding="utf-8"))
        with np.load(p, allow_pickle=False) as z:
            meta = json.loads(str(z["meta"]))
            meta["vettori"] = z["vettori"].astype("float32")
        return meta
    except Exception:
        return None


def _scrivi_indice(p: Path, dati: dict) -> None:
    import numpy as np

    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(p.name + ".tmp")
        meta = json.dumps({"firma": dati["firma"], "pezzi": dati["pezzi"]}, ensure_ascii=False)
        vettori = np.asarray(dati["vettori"], dtype="float16")
        with open(tmp, "wb") as f:   # con un file aperto numpy non aggiunge l'estensione .npz al nome
            np.savez_compressed(f, meta=np.array(meta), vettori=vettori)
        os.replace(tmp, p)  # scrittura «tutta o niente»: un altro PC non legge mai un file a metà
    except OSError:
        pass


def _file_indice(cfg: Configurazione, gruppo: str) -> list[Path]:
    nome = gruppo.lower()
    out = [cfg.cartella / f".indice_ai_{nome}.npz"]
    if cfg.indice_locale:
        out.append(cfg.indice_locale.with_name(f"{cfg.indice_locale.stem}_{nome}.npz"))
    return out


def _file_vecchi(cfg: Configurazione) -> list[Path]:
    """Indici delle versioni precedenti (uno solo per tutti i documenti): servono solo a non ricalcolare."""
    out = [cfg.cartella / NOME_INDICE, cfg.cartella / NOME_INDICE_VECCHIO]
    if cfg.indice_locale:
        out += [cfg.indice_locale, cfg.indice_locale.with_suffix(".json")]
    return list(dict.fromkeys(out))


def _durata(secondi: float) -> str:
    minuti = int(secondi // 60)
    return f"circa {minuti} min" if minuti >= 1 else "meno di un minuto"


def carica_indice(cfg: Configurazione, avanzamento: Callable[[str], None] = lambda _t: None,
                  usa_ocr: bool = True, area: str = "Tutti") -> Indice:
    """Indice dei documenti dell'area scelta: prepara solo i gruppi che servono (OAM, Compass, Generale)."""
    gruppi = AREE.get(area, GRUPPI)
    tutti = elenco_file(cfg.cartella)
    if not tutti:
        raise FileNotFoundError(f"Nessun documento in {cfg.cartella}. Aggiungine con «+ Documento» o «+ Nota».")
    if not any(gruppo_di(rel) in gruppi for rel in tutti):
        raise FileNotFoundError(f"Nessun documento nell'area {area}. Aggiungine con «+ Documento» o «+ Nota».")
    indice = Indice.unisci([_carica_gruppo(cfg, g, avanzamento, usa_ocr) for g in gruppi])
    avanzamento(f"Indice pronto: {len({p['fonte'] for p in indice.pezzi})} documenti ({area}).")
    _pulisci_vecchi(cfg)
    return indice


def _pulisci_vecchi(cfg: Configurazione) -> None:
    """Quando tutti i gruppi hanno il loro indice completo, i vecchi indici unici non servono più."""
    for g in GRUPPI:
        firma = _firma(cfg, g)
        if firma["file"] and not any((_leggi_indice(p) or {}).get("firma") == firma for p in _file_indice(cfg, g)):
            return
    for p in _file_vecchi(cfg):
        try:
            p.unlink(missing_ok=True)
        except OSError:
            pass


def _carica_gruppo(cfg: Configurazione, gruppo: str, avanzamento: Callable[[str], None],
                   usa_ocr: bool) -> Indice:
    """Indice di un gruppo: riusa quello salvato se i documenti non sono cambiati, altrimenti lo ricrea.

    Mentre lo crea salva il lavoro ogni minuto: se il programma viene chiuso, la volta dopo riparte da lì.
    """
    import numpy as np

    firma = _firma(cfg, gruppo)
    if not firma["file"]:
        return Indice.unisci([])
    for p in _file_indice(cfg, gruppo):
        dati = _leggi_indice(p)
        if dati and dati.get("firma") == firma:
            avanzamento(f"{gruppo}: indice caricato ({len(dati['pezzi'])} pezzi di testo).")
            return Indice(dati["pezzi"], np.asarray(dati["vettori"], dtype="float32"))

    # ricrea, riusando i vettori dei file non cambiati (da un salvataggio parziale o dai vecchi indici unici)
    gia: dict[str, list] = {}
    for p in _file_indice(cfg, gruppo) + _file_vecchi(cfg):
        vecchio = _leggi_indice(p) or {}
        if vecchio.get("firma", {}).get("modello") != cfg.modello_embedding:
            continue
        file_vecchi = vecchio["firma"].get("file", {})
        nuovi_qui: dict[str, list] = {}
        for pezzo, vettore in zip(vecchio.get("pezzi", []), vecchio.get("vettori", [])):
            fonte = pezzo["fonte"]
            if fonte in firma["file"] and fonte not in gia and file_vecchi.get(fonte) == firma["file"][fonte]:
                nuovi_qui.setdefault(fonte, []).append((pezzo, vettore))
        gia.update(nuovi_qui)
        del vecchio

    pezzi, vettori, fatti = [], [], {}
    da_fare: list[tuple[str, list[str]]] = []
    totale = len(firma["file"])
    for n, rel in enumerate(firma["file"], start=1):
        if rel in gia:
            for pezzo, vettore in gia[rel]:
                pezzi.append(pezzo)
                vettori.append(vettore)
            fatti[rel] = firma["file"][rel]
            continue
        avanzamento(f"{gruppo}: leggo {n}/{totale}: {rel}")
        try:
            testo = leggi_file(cfg.cartella / rel, usa_ocr)
        except Exception as e:  # file illeggibile: si salta, l'avviso resta nella barra di stato
            avanzamento(f"Non leggibile: {rel} ({e})")
            continue
        da_fare.append((rel, dividi_in_pezzi(testo)))

    def salva(firma_da_salvare: dict) -> None:
        dati = {"firma": firma_da_salvare, "pezzi": pezzi, "vettori": vettori}
        for p in _file_indice(cfg, gruppo):
            _scrivi_indice(p, dati)

    n_nuovi = sum(len(t) for _r, t in da_fare)
    if n_nuovi:
        fatti_ora, inizio, ultimo_salvataggio = 0, time.monotonic(), time.monotonic()
        avanzamento(f"{gruppo}: preparo la ricerca su {n_nuovi} pezzi di testo nuovi…")
        for rel, testi in da_fare:
            for i in range(0, len(testi), LOTTO_EMBEDDING):
                lotto = testi[i:i + LOTTO_EMBEDDING]
                vettori += ollama_http.embed(cfg.host, cfg.modello_embedding, ["search_document: " + t for t in lotto])
                pezzi += [{"fonte": rel, "testo": t} for t in lotto]
                fatti_ora += len(lotto)
                passati = time.monotonic() - inizio
                resto = passati / fatti_ora * (n_nuovi - fatti_ora)
                avanzamento(f"{gruppo}: preparo la ricerca {fatti_ora}/{n_nuovi} pezzi ({fatti_ora * 100 // n_nuovi}%), "
                            f"{_durata(resto)} rimasti. Puoi chiudere: il lavoro fatto resta salvato.")
            fatti[rel] = firma["file"][rel]
            if time.monotonic() - ultimo_salvataggio > SALVA_OGNI_SECONDI:
                # salvataggio parziale: firma con i soli file già pronti, così non vale come indice completo
                salva({**firma, "file": dict(fatti)})
                ultimo_salvataggio = time.monotonic()
    if not pezzi:
        return Indice.unisci([])
    # anche i file illeggibili restano nella firma: così non si riprova a leggerli a ogni apertura
    salva(firma)
    return Indice(pezzi, np.asarray(vettori, dtype="float32"))


# ------------------------------------------------------------------ domande
def cerca(cfg: Configurazione, indice: Indice, domanda: str, area: str = "Tutti") -> list[dict]:
    import numpy as np

    scelti = indice.indici_area(area)
    if not scelti:
        return []
    q = np.array(ollama_http.embed(cfg.host, cfg.modello_embedding, ["search_query: " + domanda])[0], dtype="float32")
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
