"""Testo anonimizzato da inviare per l'assistenza: toglie i dati personali, lascia diciture e importi.

Sostituisce: codici fiscali, nome e cognome del cliente, IBAN, numeri di documento/matricole lunghe,
date di nascita indicate dal codice fiscale. Lascia: diciture, importi, periodi, partite IVA delle aziende.
"""

from __future__ import annotations

import re

from .report import Report


def anonimizza(testo: str, report: Report | None = None) -> str:
    t = testo
    # IBAN e codici fiscali (anche con lettere/cifre lette male dall'OCR)
    t = re.sub(r"\bIT\s?\d{2}\s?[A-Z](?:\s?[0-9A-Z]){22}\b", "IT00X0000000000000000000000", t, flags=re.IGNORECASE)
    t = re.sub(
        r"\b[A-Z0-9|]{6}[0-9A-Z]{2}[A-Z0-9][0-9A-Z]{2}[A-Z0-9][0-9A-Z]{3}[A-Z0-9]\b",
        lambda m: "XXXXXX00X00X000X" if re.search(r"[A-Z]", m.group(0)) and re.search(r"\d", m.group(0))
        else m.group(0), t)
    nomi = set()
    if report is not None:
        d = report.dati
        for chiave in ("nominativo", "cognome", "nome"):
            if d.get(chiave):
                nomi.update(p for p in re.split(r"[\s']+", str(d[chiave])) if len(p) >= 3)
        for chiave in ("codice_fiscale", "codice_fiscale_dipendente", "codice_fiscale_contribuente",
                       "codice_fiscale_pensionato"):
            if d.get(chiave):
                from .validators import decodifica_codice_fiscale, nominativo_da_cf

                if not nomi:  # nome senza etichetta: lo si cerca con il codice fiscale
                    trovato = nominativo_da_cf(testo, d[chiave])
                    if trovato:
                        nomi.update(p for p in trovato.split() if len(p) >= 3)
                nascita = decodifica_codice_fiscale(d[chiave]).data_nascita
                if nascita:  # data di nascita in tutti i formati
                    for sep in "/-.":
                        t = t.replace(nascita.strftime(f"%d{sep}%m{sep}%Y"), f"00{sep}00{sep}0000")
                t = t.replace(d[chiave], "XXXXXX00X00X000X")
    for nome in sorted(nomi, key=len, reverse=True):
        t = re.sub(rf"\b{re.escape(nome)}\b", "X" * len(nome), t, flags=re.IGNORECASE)
    # matricole, numeri di documento e di pensione (sequenze lunghe di cifre non importi né P.IVA)
    t = re.sub(r"(?<![\d.,])\d{12,}(?![\d.,])", lambda m: "0" * len(m.group(0)), t)
    return t


# --- Report ed esportazioni con i dati personali oscurati ------------------------------------------------

CF_OSCURATO = "XXXXXX00X00X000X"
CHIAVI_CF = ("codice_fiscale", "codice_fiscale_dipendente", "codice_fiscale_contribuente", "codice_fiscale_pensionato")
CHIAVI_NUMERI = ("numero_documento", "numero_pensione", "matricola", "iban", "luogo_nascita")


def mappa_sensibili(reports) -> dict[str, str]:
    """Testo sensibile -> sostituzione, raccolto dai dati dei documenti (anche di più documenti insieme)."""
    from .validators import decodifica_codice_fiscale, nominativo_da_cf  # noqa: F401

    mappa: dict[str, str] = {}
    for r in reports:
        if r is None:
            continue
        d = r.dati
        nomi = []
        for chiave in ("nominativo", "cognome", "nome"):
            if d.get(chiave):
                nomi += [p for p in re.split(r"[\s']+", str(d[chiave])) if len(p) >= 2]
        for parola in nomi:
            mappa[parola] = parola[0].upper() + "."
        for chiave in CHIAVI_CF:
            cf = d.get(chiave)
            if cf:
                mappa[str(cf)] = CF_OSCURATO
                nascita = decodifica_codice_fiscale(str(cf)).data_nascita
                if nascita:
                    for formato in ("%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y"):
                        mappa[nascita.strftime(formato)] = "••/••/••••"
        for chiave in ("data_nascita", "data_nascita_da_cf"):
            if hasattr(d.get(chiave), "strftime"):
                for formato in ("%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y"):
                    mappa[d[chiave].strftime(formato)] = "••/••/••••"
        for chiave in CHIAVI_NUMERI:
            if d.get(chiave):
                mappa[str(d[chiave])] = "••••••"
    return mappa


def oscura_testo(testo: str, mappa: dict[str, str]) -> str:
    if not testo:
        return testo
    for originale in sorted(mappa, key=len, reverse=True):
        if re.fullmatch(r"[A-Za-zÀ-ÿ]+", originale):  # nomi: parola intera, maiuscole o minuscole
            testo = re.sub(rf"(?<![A-Za-zÀ-ÿ]){re.escape(originale)}(?![A-Za-zÀ-ÿ])", mappa[originale], testo,
                           flags=re.IGNORECASE)
        else:
            testo = testo.replace(originale, mappa[originale])
    # IBAN e codici fiscali rimasti (anche letti male dall'OCR)
    testo = re.sub(r"\bIT\d{2}[A-Z]\d{10}[0-9A-Z]{12}\b", "IT00X0000000000000000000000", testo)
    return testo


def oscura_report(report: Report, mappa: dict[str, str] | None = None) -> Report:
    """Copia del report con i dati personali oscurati (per stampa, PDF, esportazioni)."""
    import copy
    from datetime import date

    mappa = mappa if mappa is not None else mappa_sensibili([report])
    r = copy.deepcopy(report)
    for chiave, valore in list(r.dati.items()):
        if chiave in CHIAVI_CF and valore:
            r.dati[chiave] = CF_OSCURATO
        elif chiave in ("data_nascita", "data_nascita_da_cf") and valore:
            r.dati[chiave] = "••/••/••••"
        elif chiave in CHIAVI_NUMERI and valore:
            r.dati[chiave] = "••••••"
        elif chiave in ("nominativo", "cognome", "nome") and valore:
            r.dati[chiave] = oscura_testo(str(valore), mappa)
        elif isinstance(valore, str):
            r.dati[chiave] = oscura_testo(valore, mappa)
        elif isinstance(valore, list):
            r.dati[chiave] = [oscura_testo(v, mappa) if isinstance(v, str) else v for v in valore]
        elif isinstance(valore, date) and chiave.startswith("data_nascita"):
            r.dati[chiave] = "••/••/••••"
    for c in r.controlli:
        c.dettaglio = oscura_testo(c.dettaglio, mappa)
        c.gruppo = oscura_testo(c.gruppo, mappa)
        c.nome = oscura_testo(c.nome, mappa)
    return r


def oscura_documenti(documenti: list[tuple[str, Report]], confronto=None):
    """Oscura una serie di documenti (nomi dei file compresi) e l'eventuale confronto, con la stessa mappa."""
    import copy

    mappa = mappa_sensibili([r for _, r in documenti])
    oscurati = [(oscura_testo(nome, mappa), oscura_report(r, mappa)) for nome, r in documenti]
    if confronto is not None:
        confronto = copy.deepcopy(confronto)
        confronto.report = oscura_report(confronto.report, mappa)
        for cf in list(confronto.tabelle):
            righe = confronto.tabelle.pop(cf)
            for riga in righe:
                riga["file"] = oscura_testo(riga.get("file", ""), mappa)
            confronto.tabelle[oscura_testo(cf, mappa)] = righe
    return oscurati, confronto
