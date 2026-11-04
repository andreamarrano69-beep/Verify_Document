"""Analisi del file PDF alla ricerca di segni di alterazione.

Nessun controllo è una prova assoluta: ogni indizio aggiunge punti a un
"indice di rischio" (basso / medio / alto). Con rischio alto conviene chiedere
il documento originale (es. scaricato dal portale del datore di lavoro / Agenzia Entrate).

Indizi esaminati:
1. programma che ha creato/modificato il PDF (metadati Info + XMP)
2. data di modifica diversa dalla creazione; creazione precedente al periodo del documento
3. salvataggi successivi alla creazione (aggiornamenti incrementali, cronologia XMP)
4. importi scritti con un carattere (font) usato quasi solo lì
5. testo sovrapposto ad altro testo nella stessa posizione
6. annotazioni (caselle di testo, timbri, riquadri) aggiunte sopra la pagina
7. campi modulo compilabili; metadati assenti; pagine solo immagine (scansioni)
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from .report import Esito, Report

GRUPPO = "Autenticità file PDF"

# --- Programmi produttori --------------------------------------------------------
SOFTWARE_GESTIONALI = [
    "zucchetti", "teamsystem", "inaz", "adp", "ranocchi", "osra", "datev", "sistemi",
    "paghe", "gis ", "buffetti", "wolters", "entratel", "agenzia delle entrate", "sogei",
    "inps", "jasperreports", "crystal reports", "itext", "pdflib", "apache fop", "birt",
    "list & label", "reportlab", "telerik", "devexpress", "aspose", "stimulsoft", "pdfsharp",
    "tcpdf", "fpdf", "dompdf", "wkhtmltopdf", "qt ", "skia", "chromium",
]
EDITOR_ONLINE = [
    "ilovepdf", "smallpdf", "sejda", "pdfescape", "pdffiller", "pdf candy", "pdfcandy",
    "soda pdf", "sodapdf", "dochub", "pdf2go", "pdfsimpli", "lightpdf", "pdfzorro", "canva",
    "online2pdf", "hipdf", "formswift", "pdfgear",
]
EDITOR_PDF = [
    "pdf-xchange editor", "foxit phantompdf", "foxit pdf editor", "nitro", "pdfelement",
    "wondershare", "master pdf", "pdf expert", "infix", "pdfpen", "acrobat pro",
    "adobe acrobat", "photoshop", "illustrator", "inkscape", "gimp", "pixelmator", "affinity",
    "corel", "libreoffice draw", "openoffice draw", "preview", "pdf studio", "able2extract",
]
ELABORATORI_TESTO = ["microsoft® word", "microsoft word", "word", "libreoffice", "openoffice",
                     "writer", "excel", "pages", "google docs", "wps"]
STAMPANTI_PDF = ["print to pdf", "distiller", "ghostscript", "pdfcreator", "bullzip", "cutepdf", "dopdf",
                 "quartz pdfcontext", "microsoft: print", "pdf24", "primopdf", "novapdf"]
APP_SCANSIONE = ["camscanner", "adobe scan", "genius scan", "microsoft lens", "office lens",
                 "scanner pro", "tiny scanner", "notebloc", "naps2", "epson scan", "hp scan",
                 "canon", "xerox", "ricoh", "kyocera", "brother", "konica"]

PUNTI_SOGLIA_MEDIO = 1
PUNTI_SOGLIA_ALTO = 3


@dataclass
class Indizio:
    nome: str
    esito: Esito
    dettaglio: str
    punti: int = 0


# --- Utilità ---------------------------------------------------------------------

def _decodifica(v) -> str:
    if v is None:
        return ""
    if hasattr(v, "resolve"):
        v = v.resolve()
    if hasattr(v, "name") and not isinstance(v, (str, bytes)):  # nome PDF (/FreeText)
        v = v.name
        if isinstance(v, bytes):
            v = v.decode("latin-1")
    if isinstance(v, bytes):
        if v.startswith(b"\xfe\xff"):
            return v[2:].decode("utf-16-be", errors="replace")
        return v.decode("latin-1", errors="replace")
    return str(v)


def parse_data_pdf(s: str) -> datetime | None:
    """Converte 'D:20261031153000+01'00'' in datetime (UTC se il fuso è indicato)."""
    m = re.match(r"(?:D:)?(\d{4})(\d{2})?(\d{2})?(\d{2})?(\d{2})?(\d{2})?([Zz+\-])?(\d{2})?'?(\d{2})?",
                 (s or "").strip())
    if not m:
        return None
    a, me, g, h, mi, se, tz, tzh, tzm = m.groups()
    try:
        dt = datetime(int(a), int(me or 1), int(g or 1), int(h or 0), int(mi or 0), int(se or 0))
    except ValueError:
        return None
    if tz in ("+", "-") and tzh:
        delta = timedelta(hours=int(tzh), minutes=int(tzm or 0))
        dt = (dt - delta) if tz == "+" else (dt + delta)
        dt = dt.replace(tzinfo=timezone.utc)
    elif tz in ("Z", "z"):
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _confronta(d1: datetime, d2: datetime) -> float:
    """Secondi tra d2 e d1, ignorando il fuso se uno dei due ne è privo."""
    if (d1.tzinfo is None) != (d2.tzinfo is None):
        d1, d2 = d1.replace(tzinfo=None), d2.replace(tzinfo=None)
    return (d2 - d1).total_seconds()


def _classifica(software: str) -> tuple[str, Esito, int] | None:
    s = software.lower()
    for lista, categoria, esito, punti in [
        (EDITOR_ONLINE, "editor PDF online", Esito.ERRORE, 3),
        (EDITOR_PDF, "programma di modifica PDF/immagini", Esito.ATTENZIONE, 2),
        (APP_SCANSIONE, "scanner / app di scansione", Esito.INFO, 0),
        (STAMPANTI_PDF, "stampante virtuale PDF (documento ristampato)", Esito.ATTENZIONE, 1),
        (SOFTWARE_GESTIONALI, "software gestionale / generatore di report", Esito.OK, 0),
        (ELABORATORI_TESTO, "elaboratore di testi / foglio di calcolo", Esito.ATTENZIONE, 2),
    ]:
        if any(re.search(r"(?<![a-z])" + re.escape(k.strip()) + r"(?![a-z])", s) for k in lista):
            return categoria, esito, punti
    return None


def _xmp(raw: bytes) -> dict:
    """Estrae dai metadati XMP (testo XML non compresso) strumento e cronologia."""
    out = {"strumenti": [], "azioni": []}
    for m in re.finditer(rb"xmp:CreatorTool>([^<]{1,200})<|xmp:CreatorTool=\"([^\"]{1,200})\"", raw):
        out["strumenti"].append((m.group(1) or m.group(2)).decode("utf-8", "replace").strip())
    for m in re.finditer(rb"stEvt:softwareAgent(?:>|=\")([^<\"]{1,200})", raw):
        out["strumenti"].append(m.group(1).decode("utf-8", "replace").strip())
    for m in re.finditer(rb"stEvt:action(?:>|=\")([^<\"]{1,40})", raw):
        out["azioni"].append(m.group(1).decode("utf-8", "replace").strip())
    m = re.search(rb"xmp:ModifyDate(?:>|=\")([^<\"]{1,40})", raw)
    if m:
        out["data_modifica"] = m.group(1).decode()
    return out


def _data_riferimento(report: Report | None) -> date | None:
    """Prima data in cui il documento può legittimamente esistere."""
    if not report:
        return None
    d = report.dati
    if d.get("periodo"):  # busta paga: "Ottobre 2026"
        from .busta_paga import MESI

        nome, anno = d["periodo"].lower().split()
        return date(int(anno), MESI.index(nome) + 1, 1)
    if d.get("periodo_imposta"):  # Modello Redditi: presentato dopo la fine dell'anno
        return date(d["periodo_imposta"] + 1, 1, 1)
    if d.get("data_rilascio"):
        return d["data_rilascio"]
    return None


# --- Analisi -----------------------------------------------------------------------

def analizza_pdf(percorso: str | Path, report: Report | None = None) -> list[Indizio]:
    import pdfplumber

    p = Path(percorso)
    raw = p.read_bytes()
    indizi: list[Indizio] = []

    with pdfplumber.open(p) as pdf:
        info = {k: _decodifica(v) for k, v in (pdf.metadata or {}).items()}
        catalogo = pdf.doc.catalog or {}
        pagine_testo = pagine_immagine = 0
        parole_numeriche = []
        tutte_parole = Counter()
        sovrapposizioni = []
        annotazioni = Counter()

        for n, pagina in enumerate(pdf.pages, start=1):
            if len(pagina.chars) < 20:
                if pagina.images:
                    pagine_immagine += 1
                continue
            pagine_testo += 1
            parole = pagina.extract_words(extra_attrs=["fontname", "size"], keep_blank_chars=False)
            for w in parole:
                font = w["fontname"]
                tutte_parole[font] += 1
                if re.fullmatch(r"-?[\d.]+,\d{2}-?|\d{1,3}(?:\.\d{3})+", w["text"]):
                    parole_numeriche.append((n, w["text"], font, round(w["size"], 1)))
            sovrapposizioni += _testo_sovrapposto(pagina, n)
            for a in pagina.annots or []:
                tipo = _decodifica((a.get("data") or {}).get("Subtype")).lstrip("/")
                if tipo and tipo not in ("Link", "Widget", "Popup"):
                    annotazioni[tipo] += 1

    # 1. Programma produttore ---------------------------------------------------------
    xmp = _xmp(raw)
    software = [s for s in [info.get("Producer"), info.get("Creator"), *xmp["strumenti"]] if s]
    software = list(dict.fromkeys(software))
    if not software:
        indizi.append(Indizio("Programma di creazione", Esito.ATTENZIONE,
                              "Metadati assenti: spesso rimossi da strumenti di modifica o conversione", 1))
    else:
        classificati = [(s, _classifica(s)) for s in software]
        peggiore = max(classificati, key=lambda x: x[1][2] if x[1] else 0)
        s, cl = peggiore
        elenco = " · ".join(software)
        if cl is None:
            indizi.append(Indizio("Programma di creazione", Esito.INFO, f"{elenco} (non classificato)"))
        else:
            categoria, esito, punti = cl
            spiegazioni = {
                "editor PDF online": " — il file è stato caricato su un sito (es. iLovePDF) per unirlo, comprimerlo, "
                                     "convertirlo o modificarlo: non prova un'alterazione, ma non è il PDF originale del "
                                     "programma paghe/ente. Chiedere il file originale (es. dal portale del datore di lavoro)",
                "programma di modifica PDF/immagini": " — il file è stato aperto e salvato con un programma che permette "
                                                      "di modificarlo: chiedere se possibile il PDF originale",
                "elaboratore di testi / foglio di calcolo": " — documento prodotto con Word/Excel o simili, non con un "
                                                            "programma paghe",
            }
            indizi.append(Indizio("Programma di creazione", esito,
                                  f"{elenco} → {categoria}{spiegazioni.get(categoria, '')}", punti))

    # 2. Date -------------------------------------------------------------------------
    creazione = parse_data_pdf(info.get("CreationDate", ""))
    modifica = parse_data_pdf(info.get("ModDate", "") or xmp.get("data_modifica", "").replace("-", "")
                              .replace("T", "").replace(":", ""))
    if creazione:
        dettaglio = f"Creato il {creazione:%d/%m/%Y %H:%M}"
        if modifica and _confronta(creazione, modifica) > 120:
            indizi.append(Indizio("Date del file", Esito.ATTENZIONE,
                                  f"{dettaglio}, modificato il {modifica:%d/%m/%Y %H:%M}", 2))
        else:
            indizi.append(Indizio("Date del file", Esito.OK, dettaglio + ", nessuna modifica successiva"))
        rif = _data_riferimento(report)
        if rif and creazione.date() < rif - timedelta(days=5):
            indizi.append(Indizio("Data creazione / periodo", Esito.ERRORE,
                                  f"File creato il {creazione:%d/%m/%Y}, prima del periodo a cui si riferisce "
                                  f"({rif:%d/%m/%Y})", 3))
        elif rif and creazione.date() > rif + timedelta(days=550):
            indizi.append(Indizio("Data creazione / periodo", Esito.INFO,
                                  f"File creato il {creazione:%d/%m/%Y}, molto dopo il periodo: probabile ristampa"))
    else:
        indizi.append(Indizio("Date del file", Esito.ATTENZIONE, "Data di creazione assente", 1))

    # 3. Salvataggi successivi ------------------------------------------------------------
    n_eof = len(re.findall(rb"%%EOF", raw))
    linearizzato = b"/Linearized" in raw[:2048]
    aggiornamenti = n_eof - 1 - (1 if linearizzato else 0)
    azioni_modifica = [a for a in xmp["azioni"] if a.lower() in ("saved", "edited", "modified", "derived")]
    if aggiornamenti > 0 or azioni_modifica:
        parti = []
        if aggiornamenti > 0:
            parti.append(f"{aggiornamenti} salvataggio/i aggiunto/i dopo la creazione")
        if azioni_modifica:
            parti.append(f"cronologia XMP: {', '.join(azioni_modifica)}")
        indizi.append(Indizio("Modifiche successive", Esito.ATTENZIONE, "; ".join(parti), 2))
    else:
        indizi.append(Indizio("Modifiche successive", Esito.OK, "File salvato una sola volta"))

    # 4. Caratteri degli importi -----------------------------------------------------------
    if parole_numeriche:
        font_numeri = Counter(f for _, _, f, _ in parole_numeriche)
        principale = font_numeri.most_common(1)[0][0]
        rari = [(n, t, f) for n, t, f, _ in parole_numeriche
                if f != principale and font_numeri[f] <= max(2, len(parole_numeriche) * 0.1)
                and tutte_parole[f] <= 3]
        gravi = [x for x in rari if not _variante_stile(x[2], tutte_parole)]
        lievi = [x for x in rari if x not in gravi]

        def elenco(xs):
            return ", ".join(f"{t} (pag. {n}, font {f.split('+')[-1]})" for n, t, f in xs[:4])

        if gravi:
            indizi.append(Indizio("Caratteri degli importi", Esito.ERRORE,
                                  f"Importi scritti con un carattere diverso dal resto del documento: "
                                  f"{elenco(gravi)}", 3))
        elif lievi:
            indizi.append(Indizio("Caratteri degli importi", Esito.ATTENZIONE,
                                  f"Importi in grassetto/corsivo isolato (spesso normale per il netto): "
                                  f"{elenco(lievi)}", 1))
        else:
            indizi.append(Indizio("Caratteri degli importi", Esito.OK,
                                  f"{len(parole_numeriche)} importi con caratteri uniformi"))

    # 5. Testo sovrapposto -----------------------------------------------------------------
    if sovrapposizioni:
        indizi.append(Indizio("Testo sovrapposto", Esito.ERRORE,
                              "Testo scritto sopra altro testo: " + "; ".join(sovrapposizioni[:3]), 3))

    # 6. Annotazioni e moduli --------------------------------------------------------------
    if annotazioni:
        elenco = ", ".join(f"{k} ×{v}" for k, v in annotazioni.items())
        indizi.append(Indizio("Elementi aggiunti sopra la pagina", Esito.ERRORE,
                              f"Annotazioni presenti ({elenco}): tipiche degli editor PDF", 3))
    if "AcroForm" in catalogo:
        indizi.append(Indizio("Campi compilabili", Esito.ATTENZIONE,
                              "Il PDF contiene campi modulo modificabili", 1))

    # 7. Scansioni --------------------------------------------------------------------------
    if pagine_immagine and not pagine_testo:
        indizi.append(Indizio("Tipo di PDF", Esito.ATTENZIONE,
                              "Solo immagini (scansione/foto): i controlli sul file sono limitati, "
                              "richiedere se possibile il PDF originale", 1))
    elif pagine_immagine:
        indizi.append(Indizio("Tipo di PDF", Esito.INFO,
                              f"{pagine_immagine} pagina/e senza testo (scansione)"))
    return indizi


_STILI = re.compile(r"[-,]?(bold|italic|oblique|black|heavy|semibold|demi|medium|light|regular|"
                    r"roman|book|bd|it|mt|ps|psmt)+$", re.IGNORECASE)


def _famiglia(font: str) -> tuple[str, str]:
    """('ABCDEF+Arial-BoldMT') -> ('arial', 'ABCDEF')  — famiglia senza stile e prefisso subset."""
    prefisso, _, nome = font.rpartition("+")
    nome = nome.lower()
    precedente = None
    while precedente != nome:
        precedente, nome = nome, _STILI.sub("", nome)
    return nome.strip("-, "), prefisso


def _variante_stile(font: str, tutte_parole: Counter) -> bool:
    """Vero se il font è una variante di stile (grassetto/corsivo) di una famiglia usata altrove.

    Stessa famiglia e stesso stile ma con un prefisso di subset diverso NON conta come variante:
    è il segno tipico di un editor che ha incorporato di nuovo il carattere per scrivere un numero.
    """
    fam, pref = _famiglia(font)
    nome = font.rpartition("+")[2]
    for altro, n in tutte_parole.items():
        if altro == font or n < 5:
            continue
        fam2, pref2 = _famiglia(altro)
        if fam2 != fam:
            continue
        if altro.rpartition("+")[2] == nome and pref2 != pref:
            return False  # stesso identico font, incorporato due volte
        if altro.rpartition("+")[2] != nome:
            return True
    return False


def _testo_sovrapposto(pagina, n: int) -> list[str]:
    """Cifre diverse disegnate nello stesso punto (importo riscritto sopra l'originale, es. «6» coperto da «9»).

    Si ignorano il testo ruotato/verticale e le sovrapposizioni di sole lettere: nei moduli prestampati
    (es. Zucchetti) capita che due intestazioni siano stampate una sopra l'altra, senza che sia un'alterazione.
    """
    celle: dict[tuple, str] = {}
    trovati = []
    for c in pagina.chars:
        if not c["text"].strip() or not c.get("upright", True):
            continue
        chiave = (round(c["x0"]), round(c["top"]))
        precedente = celle.get(chiave)
        if precedente is not None and precedente != c["text"] \
                and (precedente.isdigit() or c["text"].isdigit()):
            trovati.append((chiave, precedente, c["text"]))
        celle[chiave] = c["text"]
    if not trovati:
        return []
    righe: dict[int, list[str]] = {}
    for (_, y), prima, dopo in trovati:
        righe.setdefault(y, []).append(f"«{prima}» coperto da «{dopo}»")
    return [f"pag. {n}, riga a {y} pt: {', '.join(v[:4])}" for y, v in list(righe.items())[:3]]


def aggiungi_al_report(report: Report, percorso: str | Path) -> None:
    """Esegue l'analisi del PDF e aggiunge i risultati e l'indice di rischio al report."""
    try:
        indizi = analizza_pdf(percorso, report)
    except Exception as e:  # file danneggiato o cifrato
        report.aggiungi("Analisi file PDF", Esito.ATTENZIONE, f"Analisi non riuscita: {e}", gruppo=GRUPPO)
        return
    punti = sum(i.punti for i in indizi)
    if punti >= PUNTI_SOGLIA_ALTO:
        livello, esito, consiglio = "ALTO", Esito.ERRORE, "chiedere il documento originale"
    elif punti >= PUNTI_SOGLIA_MEDIO:
        livello, esito, consiglio = "MEDIO", Esito.ATTENZIONE, "verificare gli indizi segnalati"
    else:
        livello, esito, consiglio = "BASSO", Esito.OK, "nessun segno di modifica del file"
    report.dati["rischio_alterazione"] = f"{livello} ({punti} punti)"
    report.aggiungi("Indice di rischio alterazione", esito, f"{livello} ({punti} punti) — {consiglio}",
                    gruppo=GRUPPO)
    for i in indizi:
        report.aggiungi(i.nome, i.esito, i.dettaglio, gruppo=GRUPPO)
