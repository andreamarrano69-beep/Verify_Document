"""Importi della busta paga ricavati dai calcoli quando le intestazioni non si leggono.

Nelle scansioni poco nitide l'OCR perde spesso le intestazioni piccole («TOTALE COMPETENZE»,
«NETTO DEL MESE», ...) ma legge bene i numeri. Gli importi si riconoscono allora dai rapporti tra loro:

- totale competenze = somma degli importi delle voci (righe con codice voce) se quel totale è nel documento
- contributi IVS = riga «IVS  base  importo» con aliquota plausibile (8-10,5%)
- imponibile previdenziale − contributi = imponibile fiscale: la terna di importi presenti che torna
- netto = importo vicino ad «ACCREDITO» / «NETTO» compreso tra metà e il totale delle competenze

Si riempiono solo i valori non trovati con le etichette, e ogni valore ricavato viene segnalato.
"""

from __future__ import annotations

import re
from decimal import Decimal

from .validators import parse_importo

_IMPORTO = r"\d{1,3}(?:\.\d{3})*,\d{2}"
_RE_IMPORTO = re.compile(rf"(?<![\d,.])({_IMPORTO})(?![\d,])")
CENT = Decimal("0.01")

MESI = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto", "settembre", "ottobre",
        "novembre", "dicembre"]


def periodo_su_righe_separate(testo: str) -> str | None:
    """«Ottobre» e «2026» in righe diverse dell'intestazione (es. casella MESE con l'anno sotto)."""
    intestazione = "\n".join(testo.splitlines()[:15])
    m = re.search(r"\b(" + "|".join(MESI) + r")\b[^\n]*\n(?:[^\n]*\n){0,2}?[^\n]*?\b(20\d{2})\b",
                  intestazione, re.IGNORECASE)
    if m:
        return f"{m.group(1).capitalize()} {m.group(2)}"
    return None


def _importi(testo: str) -> list[Decimal]:
    return [v for v in (parse_importo(m) for m in _RE_IMPORTO.findall(testo)) if v is not None]


def _presente(valore: Decimal, importi: list[Decimal]) -> bool:
    return any(abs(valore - v) <= CENT for v in importi)


def importi_voci(testo: str) -> list[Decimal]:
    """Importo di ogni riga con codice voce: dopo la tariffa (4-5 decimali) o il primo importo della riga."""
    importi = []
    for riga in testo.splitlines():
        m = re.match(r"^\s*(?:[A-Z]\s+)?\d{1,4}\s+[A-Z][A-Z'.]+(?:\s+(?=[\w'./-]*[A-Z])[A-Z0-9'./-]+(?![\d,]))*", riga)
        if not m:
            continue
        resto = riga[m.end():]
        tariffa = re.search(r"\d{1,4},\d{4,5}", resto)
        if tariffa:
            resto = resto[tariffa.end():]
        imp = _RE_IMPORTO.search(resto)
        if imp:
            importi.append(parse_importo(imp.group(1)))
    return importi


def totale_competenze_da_voci(testo: str) -> Decimal | None:
    voci = importi_voci(testo)
    if len(voci) < 2:
        return None
    totale = sum(voci, Decimal(0))
    return totale if _presente(totale, _importi(testo)) else None


def ivs_semplice(testo: str) -> tuple[Decimal, Decimal] | None:
    """Riga «IVS   990,00   90,98» (base e contributo senza aliquota scritta)."""
    m = re.search(rf"(?im)^\s*(?:contribut\w*\s+)?I\.?V\.?S\.?\s+({_IMPORTO})\s+({_IMPORTO})(?![\d,])", testo)
    if not m:
        return None
    base, contributo = parse_importo(m.group(1)), parse_importo(m.group(2))
    if base and contributo and Decimal("0.08") <= contributo / base <= Decimal("0.105"):
        return base, contributo
    return None


def terna_imponibili(testo: str, base_inps: Decimal | None) -> tuple[Decimal, Decimal, Decimal] | None:
    """(imponibile previdenziale, contributi totali, imponibile fiscale) con a − b = c, tutti nel documento."""
    importi = sorted(set(_importi(testo)))
    candidati_a = [a for a in importi if base_inps is None or abs(a - base_inps) <= 1]
    for a in sorted(candidati_a, reverse=True):
        for b in importi:
            if a and Decimal("0.05") <= b / a <= Decimal("0.12") and _presente(a - b, importi):
                return a, b, a - b
    return None


def netto_vicino_accredito(testo: str, competenze: Decimal | None) -> Decimal | None:
    righe = testo.splitlines()
    for i, riga in enumerate(righe):
        if not re.search(r"accredito|\bnetto\b", riga, re.IGNORECASE):
            continue
        vicini = "\n".join(righe[max(0, i - 2): i + 2])
        candidati = [v for v in _importi(vicini)
                     if v > 0 and (competenze is None or competenze / 2 <= v <= competenze)]
        if candidati:
            return max(candidati)
    return None
