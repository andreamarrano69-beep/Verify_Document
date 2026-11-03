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


GRUPPO_DATI = "Verifica dei dati"

SIMBOLI = {Esito.OK: "✔", Esito.ATTENZIONE: "⚠", Esito.ERRORE: "✘", Esito.INFO: "ℹ"}


@dataclass
class Controllo:
    nome: str
    esito: Esito
    dettaglio: str
    gruppo: str = GRUPPO_DATI


@dataclass
class Report:
    tipo_documento: str
    dati: dict = field(default_factory=dict)
    controlli: list[Controllo] = field(default_factory=list)

    def aggiungi(self, nome: str, esito: Esito, dettaglio: str, gruppo: str = GRUPPO_DATI) -> None:
        self.controlli.append(Controllo(nome, esito, dettaglio, gruppo))

    def gruppi(self) -> dict[str, list[Controllo]]:
        out: dict[str, list[Controllo]] = {}
        for c in self.controlli:
            out.setdefault(c.gruppo, []).append(c)
        return out

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
                {"gruppo": c.gruppo, "nome": c.nome, "esito": c.esito.value, "dettaglio": c.dettaglio}
                for c in self.controlli
            ],
        }


def formatta_valore(chiave: str, v) -> str:
    """Rende leggibile un valore estratto (importi, date, percentuali, liste)."""
    from datetime import date

    from .validators import formatta_euro

    if v is None:
        return "—"
    if chiave.endswith("_%"):
        return f"{v}%".replace(".", ",")
    if isinstance(v, Decimal):
        return formatta_euro(v)
    if isinstance(v, date):
        return v.strftime("%d/%m/%Y")
    if isinstance(v, list):
        return ", ".join(map(str, v)) or "—"
    return str(v)


_PAROLE = {
    "cf": "CF", "lm": "(quadro LM)", "irpef": "IRPEF", "iva": "IVA", "inps": "INPS",
    "redditivita": "redditività", "eta": "età",
}


def etichetta_campo(chiave: str) -> str:
    parole = chiave.removesuffix("_%").split("_")
    testo = " ".join(_PAROLE.get(p, p) for p in parole)
    testo = testo[0].upper() + testo[1:]
    return testo + (" %" if chiave.endswith("_%") else "")


def report_testuale(nome_file: str, r: Report) -> str:
    righe = ["=" * 72, f"{nome_file}  →  {r.tipo_documento}", "=" * 72, "DATI ESTRATTI"]
    for k, v in r.dati.items():
        if v is not None:
            righe.append(f"  {etichetta_campo(k):<34} {formatta_valore(k, v)}")
    for gruppo, controlli in r.gruppi().items():
        righe += ["", gruppo.upper()]
        for c in controlli:
            righe.append(f"  {SIMBOLI[c.esito]} {c.nome:<32} {c.dettaglio}")
    righe += ["", f"ESITO COMPLESSIVO: {SIMBOLI[r.esito_globale]} {r.esito_globale.value}", ""]
    return "\n".join(righe)


def cerca_importo(
    testo: str,
    etichette: list[str],
    solo_decimali: bool = True,
    finestra: int = 160,
    solo_riga: bool = False,
) -> Decimal | None:
    """Cerca la prima etichetta presente e restituisce il primo importo che la segue.

    L'importo può trovarsi sulla stessa riga o subito sotto (layout a colonne).
    Con ``solo_riga`` la riga sotto viene usata solo se contiene soltanto numeri.
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
            if solo_riga and len(righe) > 1 and re.search(r"[A-Za-zÀ-ú]", righe[1]):
                # la riga sotto è un'altra voce (es. "6 Numero giorni..."): non prenderne i numeri
                righe = righe[:1]
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
