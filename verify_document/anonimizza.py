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
    return oscura_indirizzi_e_frammenti(t)


def _oscura(s: str) -> str:
    """Lettere -> X, cifre -> 0: stessa lunghezza, così le colonne del testo restano allineate."""
    return re.sub(r"\d", "0", re.sub(r"[A-Za-zÀ-ÿ]", "X", s))


def oscura_indirizzi_e_frammenti(t: str) -> str:
    """Dati personali che l'OCR non permette di riconoscere con certezza: si oscurano comunque.

    - indirizzi (VIA/PIAZZA/CORSO ... numero civico), CAP + comune, codice catastale + comune
    - pezzi di codice fiscale letti a metà (6 lettere quasi tutte consonanti, es. «RSSMRA»)
    - date vicino a «nato/nascita/nasc»
    - nome e cognome sotto l'intestazione «COGNOME E NOME» / «NOMINATIVO» / «DIPENDENTE»
    """
    t = re.sub(r"(?im)\b(?:VIA|V\.LE|VIALE|PIAZZA|P\.ZZA|PIAZZALE|CORSO|C\.SO|LARGO|VICOLO|CONTRADA|C\.DA|"
               r"LOCALIT[AÀ]'?|LOC\.|STRADA|TRAVERSA|BORGO)\b[ \t]+[^\n]{0,45}?(?:N\.?[ \t]*)?\d+(?:[ \t]*/[ \t]*\w)?\b",
               lambda m: _oscura(m.group(0)), t)
    t = re.sub(r"(?m)(?<![\d,.])\d{5}[ \t]+[A-ZÀ-Ü][A-ZÀ-Ü' ]{1,30}?(?=[ \t]{2,}|[ \t]*$|[ \t]+\(?[A-Z]{2}\)?\b)",
               lambda m: _oscura(m.group(0)), t)
    t = re.sub(r"\b[A-Z]\d{3}[ \t]+[A-ZÀ-Ü][A-ZÀ-Ü']{2,}(?:[ \t][A-ZÀ-Ü']{2,})?", lambda m: _oscura(m.group(0)), t)
    t = re.sub(r"\b[A-Z]{6}\b", lambda m: "XXXXXX" if sum(c not in "AEIOU" for c in m.group(0)) >= 5 else m.group(0), t)
    t = re.sub(r"(?i)(\bnat[oa]\b|nascit\w*|\bnasc\w*\.?)([^\n\d]{0,25})(\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4})",
               lambda m: m.group(1) + m.group(2) + _oscura(m.group(3)), t)
    righe = t.split("\n")
    for i, riga in enumerate(righe[:-1]):
        for m in re.finditer(r"(?i)cognome\s+e\s+nome|nominativo|\bdipendente\b|\blavoratore\b", riga):
            # il nome è sulla stessa riga dopo l'intestazione o nella riga sotto, nella stessa colonna
            inizio, fine = max(0, m.start() - 8), m.end() + 40
            sotto = righe[i + 1]
            parte = re.sub(r"\b[A-ZÀ-Ü][A-ZÀ-Ü']{1,}\b", lambda x: "X" * len(x.group(0)), sotto[inizio:fine])
            righe[i + 1] = sotto[:inizio] + parte + sotto[fine:]
    return "\n".join(righe)


# --- Report ed esportazioni con i dati personali oscurati ------------------------------------------------

CF_OSCURATO = "XXXXXX00X00X000X"
CHIAVI_CF = ("codice_fiscale", "codice_fiscale_dipendente", "codice_fiscale_contribuente", "codice_fiscale_pensionato")
CHIAVI_NUMERI = ("numero_documento", "numero_pensione", "matricola", "iban", "luogo_nascita", "intermediario",
                 "protocollo_telematico")


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
