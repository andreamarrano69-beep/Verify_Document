"""Voci della busta paga con il loro calcolo, ricalcolate una per una.

Molti cedolini riportano per ogni voce gli elementi del calcolo:

    Retribuzione edili        11,89171   56,00000 ORE      665,94      tariffa × quantità
    Contributo IVS              859,00    9,19000 %         78,95      base × aliquota
    F.do Sanitario C/Ditta      ...        0,60000 %      (  4,00)     tra parentesi: quota dell'azienda

Il programma rifà ogni calcolo (un importo ritoccato a mano di solito non torna più) e somma i contributi
IVS del dipendente su tutte le pagine (buste di più cantieri o reparti).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from .validators import parse_importo

_IMPORTO = r"\d{1,3}(?:\.\d{3})*,\d{2}"
RIGA_PERCENTUALE = re.compile(
    rf"(?P<descr>[A-Za-z][^\n]*?)\s+(?P<base>{_IMPORTO})\s+(?P<perc>\d{{1,3}},\d{{1,5}})\s*%\s*"
    rf"(?P<par>\(?)\s*(?P<imp>{_IMPORTO})\s*\)?")
RIGA_QUANTITA = re.compile(
    rf"(?P<descr>[A-Za-z][^\n]*?)\s+(?P<tariffa>\d{{1,4}},\d{{3,5}})\s+(?P<qta>\d{{1,4}},\d{{2,5}})\s*"
    rf"(?P<um>ORE|GG|H)\b\s*(?P<par>\(?)\s*(?P<imp>{_IMPORTO})\s*\)?", re.IGNORECASE)

IVS = re.compile(r"contribut\w*\s*(?:\w+\s+)?i\.?v\.?s\b", re.IGNORECASE)
ALTRI_OBBLIGATORI = re.compile(r"contribut\w*\s+(?:cigs|fis|aggiuntiv\w*|naspi|disoccupaz\w*)", re.IGNORECASE)
AZIENDA = re.compile(r"c\s*/\s*ditta|carico\s+(?:ditta|azienda)", re.IGNORECASE)


@dataclass
class Calcolo:
    descrizione: str
    formula: str
    atteso: Decimal
    indicato: Decimal
    corretto: bool


@dataclass
class EsitoVoci:
    calcoli: list[Calcolo] = field(default_factory=list)
    ivs_base: Decimal = Decimal(0)
    ivs_importo: Decimal = Decimal(0)
    righe_ivs: int = 0
    altri_contributi: Decimal = Decimal(0)

    @property
    def errati(self) -> list[Calcolo]:
        return [c for c in self.calcoli if not c.corretto]


def _descrizione(testo: str) -> str:
    """Toglie dal testo della riga i codici voce e i segni ("tn Iso * Z00000Contributo IVS" -> "Contributo IVS")."""
    t = re.sub(r"^.*?(?:[A-Z]{1,2}[0-9A-Z]\d{3,4}|\d{6})\s*(?=[A-Z])", "", testo.strip())
    t = re.sub(r"^[\W\d_]+", "", t)
    return re.sub(r"\s+", " ", t).strip() or testo.strip()


def _arrotonda(v: Decimal) -> Decimal:
    return v.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def analizza_voci(testo: str) -> EsitoVoci:
    esito = EsitoVoci()
    for riga in testo.splitlines():
        for m in RIGA_PERCENTUALE.finditer(riga):
            base, perc, imp = parse_importo(m["base"]), parse_importo(m["perc"]), parse_importo(m["imp"])
            if None in (base, perc, imp) or perc <= 0:
                continue
            atteso = _arrotonda(base * perc / 100)
            # la base INPS è spesso arrotondata all'euro: si tollera l'errore che questo produce sull'importo
            # (mezzo euro di base sposta l'importo al massimo di aliquota ÷ 200)
            tolleranza = Decimal("0.011") + (perc / 200 if base == base.to_integral_value() else 0)
            descr = _descrizione(m["descr"])
            esito.calcoli.append(Calcolo(descr, f"{m['base']} × {m['perc']}%", atteso, imp,
                                         abs(atteso - imp) <= tolleranza))
            a_carico_azienda = bool(m["par"]) or bool(AZIENDA.search(m["descr"]))
            if not a_carico_azienda and IVS.search(m["descr"]):
                esito.ivs_base += base
                esito.ivs_importo += imp
                esito.righe_ivs += 1
            elif not a_carico_azienda and ALTRI_OBBLIGATORI.search(m["descr"]):
                esito.altri_contributi += imp
        for m in RIGA_QUANTITA.finditer(riga):
            tariffa, qta, imp = parse_importo(m["tariffa"]), parse_importo(m["qta"]), parse_importo(m["imp"])
            if None in (tariffa, qta, imp):
                continue
            atteso = _arrotonda(tariffa * qta)
            esito.calcoli.append(Calcolo(_descrizione(m["descr"]), f"{m['tariffa']} × {m['qta']} {m['um'].upper()}",
                                         atteso, imp, abs(atteso - imp) <= Decimal("0.011")))
    return esito
