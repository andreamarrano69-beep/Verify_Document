"""Archivio dei documenti: copia dei file aperti nella cartella "documenti" del programma.

- i documenti aperti da qualsiasi cartella (es. la cartella delle scansioni) vengono copiati
  nell'archivio, in una sottocartella per cliente: "RSSMRA80A01H501U - ROSSI MARIO"
- la copia prende un nome comprensibile: "Busta paga - Ottobre 2026 - <nome originale>.pdf"
- lo stesso file non viene copiato due volte (confronto del contenuto)
- l'eliminazione sposta il file nel Cestino (se disponibile send2trash) e riguarda SOLO i file
  dentro l'archivio: gli originali nelle altre cartelle non vengono mai toccati

Cartella dell'archivio: impostazione "archivio"; se vuota
- con la cartella condivisa dell'ufficio: <cartella condivisa>/archivio (tutti i PC vedono gli stessi clienti)
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
    "Estratto contributivo": "Estratto contributivo",
    "Ricevuta telematica Modello Redditi": "Ricevuta Redditi",
}
_MESI = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto",
         "settembre", "ottobre", "novembre", "dicembre"]


def cartella_archivio(impostazioni: dict | None = None) -> Path:
    from .risorse import cartella_base, e_eseguibile

    scelta = (impostazioni or {}).get("archivio", "")
    if scelta:
        return Path(scelta)
    condivisa = (impostazioni or {}).get("cartella_condivisa", "")
    if condivisa:
        return Path(condivisa) / "archivio"
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
    for k in ("data_estratto", "ultimo_contributo", "data_rilascio", "data_scadenza"):
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
    for k in ("data_estratto", "ultimo_contributo"):
        if isinstance(d.get(k), date):
            return f"{_MESI[d[k].month - 1].capitalize()} {d[k].year}"
    return ""


# Sottocartelle per prodotto, dentro la cartella del cliente
CATEGORIE = {
    "Busta paga": "Buste paga",
    "Certificazione Unica (CU)": "CU",
    "Modello Redditi PF (ex Unico)": "Modello Redditi",
    "Ricevuta telematica Modello Redditi": "Modello Redditi",
    "Cedolino pensione": "Cedolini pensione",
    "Certificato di pensione (ObisM)": "ObisM",
    "Estratto contributivo": "Estratti contributivi",
}
CATEGORIA_IDENTITA = "Documenti identità"
CATEGORIA_ALTRO = "Altri documenti"
FILE_CF = ".codice_fiscale"  # file nascosto nella cartella del cliente: lega la cartella al codice fiscale


def categoria(report: Report | None) -> str:
    if report is None:
        return CATEGORIA_ALTRO
    t = report.tipo_documento
    if t in CATEGORIE:
        return CATEGORIE[t]
    if any(p in t for p in ("identità", "Patente", "Passaporto", "Tessera", "Documento anagrafico")):
        return CATEGORIA_IDENTITA
    return CATEGORIA_ALTRO


def _cf_della_cartella(cartella: Path) -> str | None:
    try:
        return (cartella / FILE_CF).read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


def nome_cartella_cliente(report: Report | None, archivio: Path) -> str:
    """Cartella del cliente: "COGNOME NOME" (o il codice fiscale se il nome non è leggibile).

    Una cartella già legata allo stesso codice fiscale viene sempre riusata (anche se il nome è stato letto in
    modo diverso); un omonimo con codice fiscale diverso riceve il codice fiscale tra parentesi.
    """
    cf = codice_fiscale(report)
    if not cf:
        # codice fiscale non letto (scansioni): si usa il nome, se è un nome vero, e la cartella già esistente
        nome = nominativo(report)
        if not nome_valido(nome):
            return SENZA_CF
        nome = _pulisci(nome.upper())
        if archivio.is_dir():
            for c in sorted(archivio.iterdir()):
                if c.is_dir() and (c.name.upper() == nome or c.name.upper().startswith(nome + " (")):
                    return c.name
        return nome
    if archivio.is_dir():
        for c in archivio.iterdir():
            if c.is_dir() and (_cf_della_cartella(c) == cf or c.name.startswith(cf)):
                return c.name
    nome = _pulisci(nominativo(report) or cf)
    cartella = archivio / nome
    if cartella.exists() and _cf_della_cartella(cartella) not in (None, cf):
        nome = _pulisci(f"{nome} ({cf})")  # omonimo
    return nome


def nome_valido(nome: str | None) -> bool:
    """«ROSSI MARIO» sì; «rata conv», «E NOME», sigle o numeri letti dall'OCR no."""
    if not nome:
        return False
    parole = nome.split()
    if not 2 <= len(parole) <= 5 or not nome.replace(" ", "").replace("'", "").isalpha():
        return False
    if nome != nome.upper():  # nei documenti il nominativo è in maiuscolo
        return False
    return sum(len(p) >= 3 for p in parole) >= 2 and not {"NOME", "COGNOME", "CODICE", "FISCALE"} & set(parole)


CHIAVI_CF = ("codice_fiscale", "codice_fiscale_dipendente", "codice_fiscale_contribuente", "codice_fiscale_pensionato")


def imposta_cliente(report: Report, nome: str | None, cf: str | None) -> None:
    """Nome e codice fiscale scritti a mano (lettura non riuscita): sostituiscono quelli letti nel documento."""
    from .report import Esito
    from .validators import decodifica_codice_fiscale

    d = report.dati
    if nome:
        d["nominativo"] = nome.upper().strip()
    if cf:
        cf = cf.upper().replace(" ", "")
        chiave = next((k for k in CHIAVI_CF if k in d), "codice_fiscale")
        d[chiave] = cf
        info = decodifica_codice_fiscale(cf)
        if info.valido and info.data_nascita:
            d.setdefault("data_nascita_da_cf", info.data_nascita)
        report.controlli = [c for c in report.controlli if not c.nome.startswith("Codice fiscale")]
        report.aggiungi("Codice fiscale", Esito.OK if info.valido else Esito.ERRORE,
                        f"{cf} inserito a mano" + ("" if info.valido else " — NON valido (carattere di controllo)"))
    report.aggiungi("Cliente inserito a mano", Esito.INFO,
                    "Nome / codice fiscale scritti dall'operatore perché non letti nel documento: verificarli")


def cartella_cliente_manuale(nome: str | None, cf: str | None, archivio: Path) -> str:
    """Cartella per nome e/o codice fiscale scritti dall'operatore (il nome scritto a mano vale sempre)."""
    if cf:
        segnaposto = Report("")
        segnaposto.dati.update({"nominativo": nome or None, "codice_fiscale": cf})
        return nome_cartella_cliente(segnaposto, archivio)
    nome = _pulisci((nome or "").upper())
    if archivio.is_dir():
        for c in sorted(archivio.iterdir()):
            if c.is_dir() and (c.name.upper() == nome or c.name.upper().startswith(nome + " (")):
                return c.name
    return nome


def file_cliente(archivio: Path, cliente: str) -> list[Path]:
    """Tutti i documenti di un cliente (in tutte le sottocartelle)."""
    cartella = archivio / cliente
    if not cartella.is_dir():
        return []
    return sorted(f for f in cartella.rglob("*") if f.is_file() and not f.name.startswith("."))


def clienti_recenti(archivio: Path, quanti: int = 30) -> list[tuple[str, datetime, int]]:
    """(cliente, ultimo documento archiviato, numero di documenti), dal più recente."""
    righe = []
    for nome, _ in clienti(archivio):
        file = file_cliente(archivio, nome)
        if file:
            righe.append((nome, datetime.fromtimestamp(max(f.stat().st_mtime for f in file)), len(file)))
    return sorted(righe, key=lambda x: x[1], reverse=True)[:quanti]


def cliente_della_cartella(percorso: Path, archivio: Path) -> tuple[str, str | None] | None:
    """Per un file dell'archivio: (nome della cartella del cliente senza il CF tra parentesi, codice fiscale legato)."""
    if not e_in_archivio(percorso, archivio):
        return None
    parti = Path(percorso).resolve().relative_to(archivio.resolve()).parts
    if len(parti) < 2 or parti[0] == SENZA_CF:
        return None
    return parti[0].split(" (")[0], _cf_della_cartella(archivio / parti[0])


def clienti(archivio: Path) -> list[tuple[str, str | None]]:
    """Cartelle dei clienti nell'archivio, con il codice fiscale legato (se c'è)."""
    if not archivio.is_dir():
        return []
    return [(c.name, _cf_della_cartella(c)) for c in sorted(archivio.iterdir(), key=lambda x: x.name.lower())
            if c.is_dir()]


def sposta(percorso: Path, archivio: Path, cliente: str, cf: str | None = None) -> Path:
    """Sposta un file dell'archivio nella cartella del cliente indicato (stessa sottocartella del prodotto)."""
    percorso = Path(percorso)
    if not e_in_archivio(percorso, archivio) or not percorso.is_file():
        raise ValueError("Si possono spostare solo documenti dentro l'archivio del programma")
    cliente = _pulisci(cliente)
    destinazione_cliente = archivio / cliente
    cf_cartella = _cf_della_cartella(destinazione_cliente)
    if cf and cf_cartella and cf_cartella != cf:
        raise ValueError(f"La cartella «{cliente}» è di un altro codice fiscale ({cf_cartella})")
    parti = percorso.resolve().relative_to(archivio.resolve()).parts
    categoria_file = parti[1] if len(parti) >= 3 else CATEGORIA_ALTRO
    cartella = destinazione_cliente / categoria_file
    if cartella.resolve() == percorso.parent.resolve():
        return percorso
    cartella.mkdir(parents=True, exist_ok=True)
    if cf and not cf_cartella:
        (destinazione_cliente / FILE_CF).write_text(cf, encoding="utf-8")
    nuovo = cartella / percorso.name
    n = 2
    while nuovo.exists():
        nuovo = cartella / f"{percorso.stem} ({n}){percorso.suffix}"
        n += 1
    vecchia = percorso.parent
    shutil.move(str(percorso), str(nuovo))
    _togli_cartelle_vuote(vecchia, archivio)
    return nuovo


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
    """Copia il file in archivio/<cliente>/<prodotto>/. Restituisce (copia, True se creata ora)."""
    percorso = Path(percorso)
    if e_in_archivio(percorso, archivio):
        return percorso, False
    cliente = archivio / nome_cartella_cliente(report, archivio)
    cliente.mkdir(parents=True, exist_ok=True)
    cf = codice_fiscale(report)
    if cf and not (cliente / FILE_CF).exists():
        (cliente / FILE_CF).write_text(cf, encoding="utf-8")
    impronta = _impronta(percorso)
    for esistente in cliente.rglob("*"):  # stesso contenuto già archiviato (in qualunque sottocartella)
        if esistente.is_file() and not esistente.name.startswith(".") \
                and esistente.stat().st_size == percorso.stat().st_size and _impronta(esistente) == impronta:
            return esistente, False
    cartella = cliente / categoria(report)
    cartella.mkdir(exist_ok=True)
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
    categoria: str = ""           # sottocartella del prodotto (Buste paga, CU, ...)


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
            parti = f.relative_to(archivio).parts
            cliente = parti[0] if len(parti) > 1 else ""
            cat = parti[1] if len(parti) > 2 else ""
            st = f.stat()
            periodo, testo = periodo_da_nome(f.name)
            voci.append(VoceArchivio(f, cliente, st.st_size, datetime.fromtimestamp(st.st_mtime), periodo, testo,
                                     cat))
    return voci


def _togli_cartelle_vuote(cartella: Path, archivio: Path) -> None:
    """Toglie le sottocartelle rimaste vuote e la cartella cliente rimasta con il solo file del codice fiscale."""
    while cartella != archivio and e_in_archivio(cartella, archivio) and cartella.is_dir():
        contenuto = [c for c in cartella.iterdir() if c.name != FILE_CF]
        if contenuto:
            break
        (cartella / FILE_CF).unlink(missing_ok=True)
        cartella.rmdir()
        cartella = cartella.parent


def elimina(percorso: Path, archivio: Path) -> str:
    """Elimina un file, una sottocartella o una cartella cliente dell'archivio. Restituisce dove è finito."""
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
        _togli_cartelle_vuote(percorso.parent, archivio)
