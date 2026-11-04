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
                t = t.replace(d[chiave], "XXXXXX00X00X000X")
    for nome in sorted(nomi, key=len, reverse=True):
        t = re.sub(rf"\b{re.escape(nome)}\b", "X" * len(nome), t, flags=re.IGNORECASE)
    # matricole, numeri di documento e di pensione (sequenze lunghe di cifre non importi né P.IVA)
    t = re.sub(r"(?<![\d.,])\d{12,}(?![\d.,])", lambda m: "0" * len(m.group(0)), t)
    return t
