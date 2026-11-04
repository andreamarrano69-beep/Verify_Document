"""Archivio dei documenti: copia dei file aperti nella cartella "documenti" del programma.

- i documenti aperti da qualsiasi cartella (es. la cartella delle scansioni) vengono copiati
  nell'archivio, in una sottocartella per cliente: "RSSMRA80A01H501U - ROSSI MARIO"
- la copia prende un nome comprensibile: "Busta paga - Ottobre 2026 - <nome originale>.pdf"
- lo stesso file non viene copiato due volte (confronto del contenuto)
- l'eliminazione sposta il file nel Cestino (se disponibile send2trash) e riguarda SOLO i file
  dentro l'archivio: gli originali nelle altre cartelle non vengono mai toccati

Cartella dell'archivio: impostazione "archivio"; se vuota
- dal codice sorgente: <cartella del progetto>/documenti
- dal programma .exe: Documenti dell'utente/Verify Document/documenti
"""

from __future__ import annotations

import hashlib
import re
import shutil
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from .report import Report

SENZA_CF = "Senza codice fiscale"
TIPI_BREVI = {
    "Busta paga": "Busta paga",
    "Modello Redditi PF (ex Unico)": "Modello Redditi",
    "Certificazione Unica (CU)": "CU",
    "Cedolino pensione": "Cedolino pensione",
    "Certificato di pensione (ObisM)": "ObisM",
}
_MESI = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto",
         "settembre", "ottobre", "novembre", "dicembre"]


def cartella_archivio(impostazioni: dict | None = None) -> Path:
    from .risorse import cartella_base, e_eseguibile

    scelta = (impostazioni or {}).get("archivio", "")
    if scelta:
        return Path(scelta)
    if e_eseguibile():
        return Path.home() / "Documents" / "Verify Document" / "documenti"
    return cartella_base() / "documenti"


def _pulisci(nome: str) -> str:
    """Nome valido per Windows (niente \\ / : * ? \" < > |), senza spazi doppi."""
    nome = re.sub(r'[\\/:*?"<>|]+', "-", nome)
    return re.sub(r"\s+", " ", nome).strip(" .-")[:120] or "documento"


def codice_fiscale(report: Report | None) -> str | None:
    if report is None:
        return None
    d = report.dati
    for k in ("codice_fiscale", "codice_fiscale_dipendente", "codice_fiscale_contribuente",
              "codice_fiscale_pensionato"):
        if d.get(k):
            return d[k]
    return None


def nominativo(report: Report | None) -> str | None:
    if report is None:
        return None
    d = report.dati
    if d.get("cognome") and d.get("nome"):
        return f"{d['cognome']} {d['nome']}"
    return d.get("nominativo")


def data_documento(report: Report | None) -> date | None:
    """Data di riferimento del documento: mese della busta/cedolino, fine anno per CU e Redditi."""
    if report is None:
        return None
    d = report.dati
    periodo = d.get("periodo")
    if isinstance(periodo, str) and len(periodo.split()) == 2:
        mese, anno = periodo.lower().split()
        if mese in _MESI and anno.isdigit():
            return date(int(anno), _MESI.index(mese) + 1, 1)
    for k in ("periodo_imposta", "anno"):
        if isinstance(d.get(k), int):
            return date(d[k], 12, 31)
    for k in ("data_rilascio", "data_scadenza"):
        if isinstance(d.get(k), date):
            return d[k]
    return None


def descrizione_periodo(report: Report | None) -> str:
    if report is None:
        return ""
    d = report.dati
    if d.get("periodo"):
        return str(d["periodo"])
    if d.get("periodo_imposta"):
        return f"Anno {d['periodo_imposta']}"
    if d.get("anno"):
        return f"Anno {d['anno']}"
    if isinstance(d.get("data_scadenza"), date):
        return f"Scad. {d['data_scadenza']:%d/%m/%Y}"
    return ""


def nome_cartella_cliente(report: Report | None, archivio: Path) -> str:
    cf = codice_fiscale(report)
    if not cf:
        return SENZA_CF
    # se esiste già una cartella per questo CF la riusa (anche se il nome è stato letto diversamente)
    if archivio.is_dir():
        for c in archivio.iterdir():
            if c.is_dir() and c.name.startswith(cf):
                return c.name
    nome = nominativo(report)
    return _pulisci(f"{cf} - {nome}" if nome else cf)


def nome_archiviato(originale: Path, report: Report | None) -> str:
    parti = []
    if report is not None:
        parti.append(TIPI_BREVI.get(report.tipo_documento, report.tipo_documento))
        periodo = descrizione_periodo(report)
        if periodo:
            parti.append(periodo)
    prefisso = " - ".join(parti)
    stem = originale.stem
    if prefisso and stem.startswith(prefisso):  # già archiviato con questo nome
        prefisso = ""
    return _pulisci(f"{prefisso} - {stem}" if prefisso else stem) + originale.suffix.lower()


def _impronta(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for blocco in iter(lambda: f.read(1 << 20), b""):
            h.update(blocco)
    return h.hexdigest()


def e_in_archivio(percorso: Path, archivio: Path) -> bool:
    try:
        percorso.resolve().relative_to(archivio.resolve())
        return True
    except ValueError:
        return False


def archivia(percorso: Path, report: Report | None, archivio: Path) -> tuple[Path, bool]:
    """Copia il file nell'archivio. Restituisce (percorso della copia, True se è stata creata ora)."""
    percorso = Path(percorso)
    if e_in_archivio(percorso, archivio):
        return percorso, False
    cartella = archivio / nome_cartella_cliente(report, archivio)
    cartella.mkdir(parents=True, exist_ok=True)
    impronta = _impronta(percorso)
    for esistente in cartella.iterdir():  # stesso contenuto già archiviato
        if esistente.is_file() and esistente.stat().st_size == percorso.stat().st_size \
                and _impronta(esistente) == impronta:
            return esistente, False
    nome = nome_archiviato(percorso, report)
    destinazione = cartella / nome
    n = 2
    while destinazione.exists():
        destinazione = cartella / f"{Path(nome).stem} ({n}){Path(nome).suffix}"
        n += 1
    shutil.copy2(percorso, destinazione)
    return destinazione, True


@dataclass
class VoceArchivio:
    percorso: Path
    cliente: str
    dimensione: int
    archiviato_il: datetime
    periodo: date | None = None   # periodo del documento, ricavato dal nome dato in archivio
    testo_periodo: str = ""


def periodo_da_nome(nome: str) -> tuple[date | None, str]:
    """'Busta paga - Ottobre 2026 - x.pdf' -> (2026-10-01, 'Ottobre 2026'); 'CU - Anno 2025 - …' -> fine 2025."""
    m = re.search(r"\b(" + "|".join(_MESI) + r") (\d{4})\b", nome, re.IGNORECASE)
    if m:
        return date(int(m.group(2)), _MESI.index(m.group(1).lower()) + 1, 1), f"{m.group(1).capitalize()} {m.group(2)}"
    m = re.search(r"\bAnno (\d{4})\b", nome)
    if m:
        return date(int(m.group(1)), 12, 31), f"Anno {m.group(1)}"
    return None, ""


def elenco(archivio: Path) -> list[VoceArchivio]:
    voci = []
    if not archivio.is_dir():
        return voci
    for f in archivio.rglob("*"):
        if f.is_file() and not f.name.startswith("."):
            cliente = f.parent.name if f.parent != archivio else ""
            st = f.stat()
            periodo, testo = periodo_da_nome(f.name)
            voci.append(VoceArchivio(f, cliente, st.st_size, datetime.fromtimestamp(st.st_mtime), periodo, testo))
    return voci


def elimina(percorso: Path, archivio: Path) -> str:
    """Elimina un file o una cartella cliente dell'archivio. Restituisce dove è finito."""
    percorso = Path(percorso)
    if not e_in_archivio(percorso, archivio) or percorso.resolve() == archivio.resolve():
        raise ValueError("Si possono eliminare solo documenti dentro l'archivio del programma")
    try:
        from send2trash import send2trash

        send2trash(str(percorso))
        return "Cestino"
    except ImportError:
        if percorso.is_dir():
            shutil.rmtree(percorso)
        else:
            percorso.unlink()
        return "eliminato definitivamente"
    finally:
        cartella = percorso.parent  # cartella cliente rimasta vuota: si toglie
        if cartella != archivio and cartella.is_dir() and not any(cartella.iterdir()):
            cartella.rmdir()
