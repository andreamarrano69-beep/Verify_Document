"""Analisi di documenti anagrafici: carta d'identità (anche CIE), patente,
passaporto, tessera sanitaria.

Controlli: validità del codice fiscale, coerenza CF ↔ cognome/nome/data di nascita/sesso,
scadenza del documento.
"""

from __future__ import annotations

import re
from datetime import date

from .report import Esito, Report, cerca_testo
from .validators import (
    CF_REGEX,
    codice_cognome,
    codice_nome,
    decodifica_codice_fiscale,
    oggi,
    parse_data,
)

TIPI = {
    "Carta d'identità elettronica": [r"carta\s+di\s+identit[aà]\s+elettronica", r"\bCIE\b"],
    "Carta d'identità": [r"carta\s+d['’]?\s*identit[aà]", r"identity\s+card"],
    "Patente di guida": [r"patente\s+di\s+guida", r"driving\s+licen[cs]e"],
    "Passaporto": [r"passaporto", r"passport"],
    "Tessera sanitaria": [r"tessera\s+sanitaria", r"tessera\s+europea"],
}

DATA = r"(\d{1,2}[/.\-]\d{1,2}[/.\-]\d{2,4})"
PAROLA = r"([A-ZÀ-Ü'][A-ZÀ-Ü' ]{1,40}?)\s*(?:\n|$|\s{2,})"


def riconosci(testo: str) -> int:
    punti = 0
    for pattern in sum(TIPI.values(), []):
        if re.search(pattern, testo, re.IGNORECASE):
            punti += 2
    for k in ["cognome", "luogo di nascita", "data di nascita", "scadenza", "cittadinanza"]:
        if k in testo.lower():
            punti += 1
    return punti


def analizza(testo: str, riferimento: date | None = None) -> Report:
    oggi_ = riferimento or oggi()
    tipo = next(
        (n for n, pats in TIPI.items() if any(re.search(p, testo, re.IGNORECASE) for p in pats)),
        "Documento anagrafico",
    )
    r = Report(tipo)
    d = r.dati

    d["cognome"] = cerca_testo(testo, [r"cognome(?:\s*/\s*surname)?"], PAROLA)
    d["nome"] = cerca_testo(testo, [r"(?<!cog)nome(?:\s*/\s*name)?"], PAROLA)
    d["data_nascita"] = parse_data(cerca_testo(testo, [r"data\s+di\s+nascita", r"nato\s+il"], DATA) or "")
    d["luogo_nascita"] = cerca_testo(testo, [r"luogo\s+di\s+nascita", r"nato\s+a"], PAROLA)
    d["sesso"] = cerca_testo(testo, [r"sesso(?:\s*/\s*sex)?"], r"\b([MF])\b")
    d["numero_documento"] = cerca_testo(
        testo, [r"(?:numero|n\.?)\s+(?:del\s+)?documento", r"n\.\s*carta"], r"([A-Z]{2}\s?\d{5,7}[A-Z]{0,2}|[A-Z0-9]{7,10})"
    )
    d["data_scadenza"] = parse_data(cerca_testo(testo, [r"scadenza", r"valid[ao]\s+fino\s+al"], DATA) or "")
    d["data_rilascio"] = parse_data(cerca_testo(testo, [r"(?:data\s+(?:di\s+)?)?(?:rilascio|emissione)"], DATA) or "")

    codici = list(dict.fromkeys(m.group(0) for m in CF_REGEX.finditer(testo.upper())))
    cf = codici[0] if codici else None
    d["codice_fiscale"] = cf

    # --- Codice fiscale -----------------------------------------------------
    if not cf:
        r.aggiungi("Codice fiscale", Esito.ATTENZIONE, "Codice fiscale non presente/leggibile")
    else:
        info = decodifica_codice_fiscale(cf, oggi_)
        if not info.valido:
            r.aggiungi("Codice fiscale", Esito.ERRORE, f"{cf} NON valido (carattere di controllo errato)")
        else:
            r.aggiungi("Codice fiscale", Esito.OK, f"{cf} formalmente valido")
            _coerenza_cf(r, cf, info)

    # --- Scadenza -----------------------------------------------------------
    sc = d["data_scadenza"]
    if not sc:
        r.aggiungi("Scadenza documento", Esito.ATTENZIONE, "Data di scadenza non trovata")
    elif sc < oggi_:
        r.aggiungi("Scadenza documento", Esito.ERRORE, f"Documento SCADUTO il {sc:%d/%m/%Y}")
    elif (sc - oggi_).days <= 60:
        r.aggiungi("Scadenza documento", Esito.ATTENZIONE, f"In scadenza il {sc:%d/%m/%Y}")
    else:
        r.aggiungi("Scadenza documento", Esito.OK, f"Valido fino al {sc:%d/%m/%Y}")

    if d["data_rilascio"] and d["data_nascita"] and d["data_rilascio"] < d["data_nascita"]:
        r.aggiungi("Date", Esito.ERRORE, "Data di rilascio precedente alla data di nascita")
    return r


def _coerenza_cf(r: Report, cf: str, info) -> None:
    d = r.dati
    problemi = []
    if d["cognome"] and codice_cognome(d["cognome"]) != cf[0:3]:
        problemi.append(f"cognome ({codice_cognome(d['cognome'])} ≠ {cf[0:3]})")
    if d["nome"] and codice_nome(d["nome"]) != cf[3:6]:
        problemi.append(f"nome ({codice_nome(d['nome'])} ≠ {cf[3:6]})")
    if d["data_nascita"] and d["data_nascita"] != info.data_nascita:
        problemi.append(f"data di nascita ({d['data_nascita']:%d/%m/%Y} ≠ {info.data_nascita:%d/%m/%Y})")
    if d["sesso"] and d["sesso"].upper() != info.sesso:
        problemi.append(f"sesso ({d['sesso']} ≠ {info.sesso})")
    if problemi:
        r.aggiungi("Coerenza CF / dati anagrafici", Esito.ERRORE, "Non coincidono: " + "; ".join(problemi))
    else:
        verificati = [k for k in ("cognome", "nome", "data_nascita", "sesso") if d[k]]
        r.aggiungi("Coerenza CF / dati anagrafici", Esito.OK,
                   "Coerente con: " + (", ".join(v.replace("_", " ") for v in verificati) or "nessun dato confrontabile"))
