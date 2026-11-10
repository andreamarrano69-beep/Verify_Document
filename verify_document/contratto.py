"""Tipo di contratto e qualifica del dipendente (aziende private e pubblica amministrazione).

Dalla busta paga / cedolino NoiPA legge:
- tipo di rapporto: tempo indeterminato, tempo determinato (con data di fine), apprendistato,
  intermittente, somministrazione; per la scuola: di ruolo / supplenza
- orario: tempo pieno o part-time (orizzontale, verticale, misto) con la percentuale
- qualifica (operaio, impiegato, quadro, dirigente, docente, collaboratore scolastico, ...), livello o area,
  mansione e contratto collettivo (CCNL)
- datore di lavoro privato o pubblico (NoiPA, ministeri, scuola, enti)

Serve per i finanziamenti: con un contratto a termine la cessione del quinto non può durare oltre la
scadenza del contratto; apprendistato e part-time riducono la stabilità del reddito.
"""

from __future__ import annotations

import re
from datetime import date

from .report import Esito, Report

GRUPPO = "Contratto di lavoro"
_DATA = r"(\d{1,2})[/.\-\s](\d{1,2})[/.\-\s](\d{4})"

QUALIFICHE = [  # (pattern, qualifica) — le più specifiche prima
    (r"dirigente\s+(?:medico|scolastico|sanitario)", None),  # qualifica scritta per intero
    (r"collaborat\w*\s+scolastic\w*", "Collaboratore scolastico"),
    (r"assistente\s+amministrativ\w*", "Assistente amministrativo"),
    (r"assistente\s+tecnic\w*", "Assistente tecnico"),
    (r"\bdocente\b|\binsegnante\b|professore", "Docente"),
    (r"infermier\w*", "Infermiere"),
    (r"funzionari\w*", "Funzionario"),
    (r"istruttore", "Istruttore"),
    (r"\bdirigent\w*", "Dirigente"),
    (r"\bquadr[oi]\b", "Quadro"),
    (r"impiegat\w*", "Impiegato"),
    (r"intermedi[oa]\b", "Intermedio"),
    (r"\boperai\w*|\boperaio\b", "Operaio"),
    (r"apprendist\w*|\bapprend\b", "Apprendista"),
]

SEGNI_PUBBLICO = re.compile(r"noipa|ministero|\bm\.?i\.?u\.?r\b|istituto\s+(?:comprensivo|scolastico)|"
                            r"amministrazione\s+(?:pubblica|dello\s+stato|comunale|provinciale|regionale)|"
                            r"\bcomune\s+di\b|\bregione\b|azienda\s+sanitaria|\basl\b|\basp\b|ufficio\s+scolastico|"
                            r"ragioneria\s+territoriale|\binpdap\b|\bcpdel\b|\bctps\b|gestione\s+dipendenti\s+pubblici",
                            re.IGNORECASE)


def _data(m: re.Match) -> date | None:
    g, mese, anno = map(int, m.groups()[-3:])
    try:
        return date(anno, mese, g) if 1950 <= anno <= 2100 else None
    except ValueError:
        return None


def leggi(testo: str) -> dict:
    t = re.sub(r"[ \t]+", " ", testo)
    d: dict = {}

    # --- tipo di rapporto -----------------------------------------------------------------------------------
    if re.search(r"apprendist|\bapprend\b", t, re.IGNORECASE) and \
            re.search(r"contratto\s+di\s+apprendistato|apprendista\b|qualifica\W+apprend", t, re.IGNORECASE):
        d["tipo_contratto"] = "Apprendistato"
    elif re.search(r"intermittent|a\s+chiamata|job\s+on\s+call", t, re.IGNORECASE):
        d["tipo_contratto"] = "Lavoro intermittente (a chiamata)"
    elif re.search(r"somministra", t, re.IGNORECASE):
        d["tipo_contratto"] = "Somministrazione (agenzia per il lavoro)"
    if re.search(r"supplen\w*|incarico\s+annuale|fino\s+al\s+termine\s+delle\s+attivit", t, re.IGNORECASE):
        d["tipo_contratto"] = d.get("tipo_contratto") or "Tempo determinato (supplenza)"
    determinato = re.search(r"(?:tempo|t\.|terpo|tenpo)\s*determ|\bdeterminato\b|\bdeter\b|contratto\s+a\s+termine|"
                            r"\bt\.?\s*d\.?\b(?=\s|$)", t, re.IGNORECASE)
    indeterminato = re.search(r"(?:tempo|t\.)\s*indeterm|\bindeterminato\b|\bindet\b|\bt\.?\s*i\.?\b(?=\s|$)|"
                              r"\bdi\s+ruolo\b|\bruolo\b", t, re.IGNORECASE)
    if "tipo_contratto" not in d:
        if indeterminato and not determinato:
            d["tipo_contratto"] = "Tempo indeterminato"
        elif determinato:
            d["tipo_contratto"] = "Tempo determinato"

    # data di fine del contratto a termine
    m = re.search(r"(?:data\s+(?:di\s+)?(?:termine|fine|scadenza)(?:\s+(?:contratto|rapporto))?|"
                  r"scadenza\s+(?:del\s+)?contratto|fine\s+rapporto|termine\s+(?:del\s+)?contratto|"
                  r"\btermine\b)\s*[:\-]?\s*" + _DATA, t, re.IGNORECASE)
    if m:
        fine = _data(m)
        if fine:
            d["data_fine_contratto"] = fine
            if "tipo_contratto" not in d or d["tipo_contratto"] == "Tempo indeterminato":
                d["tipo_contratto"] = "Tempo determinato"

    # --- orario ----------------------------------------------------------------------------------------------
    m = re.search(r"part[\s\-]*time(?:\s+(oriz\w*|vert\w*|mist\w*))?(?:[^\n%]{0,25}?(\d{1,2}(?:,\d{1,2})?)\s*%)?",
                  t, re.IGNORECASE)
    if m:
        orario = "Part-time"
        tipo_pt = (m.group(1) or "").lower()
        if tipo_pt.startswith("oriz"):
            orario += " orizzontale"
        elif tipo_pt.startswith("vert"):
            orario += " verticale"
        elif tipo_pt.startswith("mist"):
            orario += " misto"
        if m.group(2):
            orario += f" {m.group(2)}%"
        d["orario"] = orario
    elif re.search(r"full[\s\-]*time|tempo\s+pieno", t, re.IGNORECASE):
        d["orario"] = "Tempo pieno"

    # --- qualifica, livello, mansione, CCNL --------------------------------------------------------------------
    for pattern, qualifica in QUALIFICHE:
        m = re.search(pattern, t, re.IGNORECASE)
        if m:
            d["qualifica"] = qualifica or m.group(0).capitalize()
            break
    m = re.search(r"\blivell?o\b\.?\s*[:\-]?\s*([0-9]{1,2}(?:\s*[°ºa^])?(?:\s*s(?:uper)?\b)?|[A-D]\d?|Q\d?|[IVX]{1,4})\b",
                  t, re.IGNORECASE)
    if m:
        d["livello"] = re.sub(r"\s+", " ", m.group(1)).strip()
    m = re.search(r"\b(?:area|fascia\s+retributiva|posizione\s+economica|categoria\s+economica)\s*[:\-]?\s*"
                  r"((?:[A-D]|I{1,3}|[A-Z]{1,2})\s*\d{0,2}|\w+\s+\w+)\b", t, re.IGNORECASE)
    if m and "livello" not in d:
        d["livello"] = m.group(1).strip()
    m = re.search(r"mansion[ei]\s*[:\-]?\s*([A-Za-zÀ-ú][A-Za-zÀ-ú' ]{2,40}?)(?=\s{2,}|\n|$|\s+(?:livello|liv\.|ccnl))",
                  testo, re.IGNORECASE)
    if m:
        d["mansione"] = m.group(1).strip().capitalize()
    m = re.search(r"\bc\.?c\.?n\.?l\.?\s*[:\-]?\s*([A-Za-zÀ-ú][^\n]{2,45}?)(?=\s{2,}|\n|$)", testo, re.IGNORECASE)
    if m:
        d["ccnl"] = m.group(1).strip(" .-")

    d["datore_pubblico"] = bool(SEGNI_PUBBLICO.search(t))
    return d


def descrizione(d: dict) -> str | None:
    """«Tempo determinato · part-time orizzontale · Impiegato liv. 5»"""
    parti = [d.get("tipo_contratto"), (d.get("orario") or "").replace("Part-time", "part-time") or None]
    qualifica = d.get("qualifica")
    if qualifica:
        parti.append(qualifica + (f" liv. {d['livello']}" if d.get("livello") else ""))
    parti = [p for p in parti if p]
    return " · ".join(parti) if parti else None


def controlla(r: Report, testo: str, periodo: tuple[int, int] | None) -> None:
    """Aggiunge i dati del contratto alla busta paga e i controlli utili per un finanziamento."""
    d = r.dati
    info = leggi(testo)
    for k in ("tipo_contratto", "orario", "qualifica", "livello", "mansione", "ccnl", "data_fine_contratto"):
        d[k] = info.get(k)
    d["datore_di_lavoro"] = "Pubblico" if info.get("datore_pubblico") else "Privato"

    tipo = info.get("tipo_contratto")
    if not tipo:
        r.aggiungi("Tipo di contratto", Esito.INFO,
                   "Non indicato nella busta (o non leggibile): chiedere il contratto o la lettera di assunzione",
                   GRUPPO)
    else:
        dettaglio = tipo
        esito = Esito.OK if tipo in ("Tempo indeterminato", "Apprendistato") else Esito.ATTENZIONE
        fine = info.get("data_fine_contratto")
        if tipo.startswith("Tempo determinato"):
            if fine:
                dettaglio += f" fino al {fine:%d/%m/%Y}"
                rif = date(periodo[0], periodo[1], 1) if periodo else date.today()
                mesi = (fine.year - rif.year) * 12 + fine.month - rif.month
                if mesi < 0:
                    esito = Esito.ERRORE
                    dettaglio += " — già scaduto rispetto al periodo della busta paga"
                else:
                    dettaglio += f" (mancano circa {mesi} mesi)"
            dettaglio += (" — per la cessione del quinto la durata del prestito non può superare la scadenza del "
                          "contratto")
        elif tipo == "Apprendistato":
            dettaglio += " — contratto a tempo indeterminato con periodo formativo; verificare la data di fine " \
                         "dell'apprendistato"
        elif tipo.startswith(("Lavoro intermittente", "Somministrazione")):
            dettaglio += " — reddito non garantito ogni mese: valutare più buste paga"
        r.aggiungi("Tipo di contratto", esito, dettaglio, GRUPPO)

    if info.get("orario"):
        r.aggiungi("Orario di lavoro", Esito.INFO,
                   info["orario"] + ("" if info["orario"] == "Tempo pieno"
                                     else " — reddito ridotto rispetto al tempo pieno"), GRUPPO)
    qualifica = " · ".join(x for x in (
        info.get("qualifica"), f"livello {info['livello']}" if info.get("livello") else None,
        f"mansione {info['mansione']}" if info.get("mansione") else None,
        f"CCNL {info['ccnl']}" if info.get("ccnl") else None) if x)
    r.aggiungi("Qualifica", Esito.INFO,
               qualifica or "Qualifica e livello non indicati nella busta (o non leggibili)", GRUPPO)
    r.aggiungi("Datore di lavoro", Esito.INFO,
               "Pubblica amministrazione (dipendente statale/pubblico)" if info.get("datore_pubblico")
               else "Azienda privata", GRUPPO)
