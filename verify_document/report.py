"""Struttura comune del risultato di un'analisi + utilità di ricerca nel testo."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum

from .validators import IMPORTO_ANCHE_INTERO, IMPORTO_DECIMALI, parse_importo


class Esito(str, Enum):
    OK = "OK"
    ATTENZIONE = "ATTENZIONE"
    ERRORE = "ERRORE"
    INFO = "INFO"


SIMBOLI = {Esito.OK: "✔", Esito.ATTENZIONE: "⚠", Esito.ERRORE: "✘", Esito.INFO: "ℹ"}


@dataclass
class Controllo:
    nome: str
    esito: Esito
    dettaglio: str


@dataclass
class Report:
    tipo_documento: str
    dati: dict = field(default_factory=dict)
    controlli: list[Controllo] = field(default_factory=list)

    def aggiungi(self, nome: str, esito: Esito, dettaglio: str) -> None:
        self.controlli.append(Controllo(nome, esito, dettaglio))

    @property
    def esito_globale(self) -> Esito:
        esiti = {c.esito for c in self.controlli}
        if Esito.ERRORE in esiti:
            return Esito.ERRORE
        if Esito.ATTENZIONE in esiti:
            return Esito.ATTENZIONE
        return Esito.OK

    def to_dict(self) -> dict:
        def conv(v):
            if isinstance(v, Decimal):
                return float(v)
            if hasattr(v, "isoformat"):
                return v.isoformat()
            if isinstance(v, dict):
                return {k: conv(x) for k, x in v.items()}
            if isinstance(v, list):
                return [conv(x) for x in v]
            return v

        return {
            "tipo_documento": self.tipo_documento,
            "esito_globale": self.esito_globale.value,
            "dati": conv(self.dati),
            "controlli": [
                {"nome": c.nome, "esito": c.esito.value, "dettaglio": c.dettaglio}
                for c in self.controlli
            ],
        }


def cerca_importo(
    testo: str,
    etichette: list[str],
    solo_decimali: bool = True,
    finestra: int = 160,
) -> Decimal | None:
    """Cerca la prima etichetta presente e restituisce il primo importo che la segue.

    L'importo può trovarsi sulla stessa riga o subito sotto (layout a colonne).
    """
    regex_importo = re.compile(
        r"(?<![\w/.,])(" + (IMPORTO_DECIMALI if solo_decimali else IMPORTO_ANCHE_INTERO) + r")"
        r"(?![\w/])"
    )
    for etichetta in etichette:
        for m in re.finditer(etichetta, testo, flags=re.IGNORECASE):
            coda = testo[m.end(): m.end() + finestra]
            # non sconfinare oltre la riga successiva
            righe = coda.split("\n")
            coda = "\n".join(righe[:2])
            for imp in regex_importo.finditer(coda):
                prima = coda[max(0, imp.start() - 1): imp.start()]
                if prima.isalpha():  # es. "RN1" -> non prendere "1"
                    continue
                v = parse_importo(imp.group(1))
                if v is not None:
                    return v
    return None


def cerca_testo(testo: str, etichette: list[str], valore: str = r"(.+)") -> str | None:
    for etichetta in etichette:
        m = re.search(etichetta + r"\s*[:\-]?\s*" + valore, testo, flags=re.IGNORECASE)
        if m:
            return m.group(1).strip()
    return None
