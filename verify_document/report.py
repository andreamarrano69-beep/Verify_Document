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
    "cf": "CF", "lm": "(quadro LM)", "re": "(quadro RE)", "rg": "(quadro RG)", "irpef": "IRPEF", "iva": "IVA", "inps": "INPS",
    "redditivita": "redditività", "eta": "età",
}


def etichetta_campo(chiave: str) -> str:
    parole = chiave.removesuffix("_%").split("_")
    testo = " ".join(_PAROLE.get(p, p) for p in parole)
    testo = testo[0].upper() + testo[1:]
    return testo + (" %" if chiave.endswith("_%") else "")


@dataclass
class Sintesi:
    """Le informazioni principali di un documento di reddito: che tipo di reddito è e quanto rende al mese."""
    etichetta: str            # "Regime fiscale", "Tipo di pensione", ...
    categoria: str | None     # "Forfettario", "Vecchiaia", "Lavoro dipendente", ...
    mensile_lordo: Decimal | None
    mensile_netto: Decimal | None
    nota: str


def sintesi(r: Report) -> Sintesi | None:
    d = r.dati
    t = r.tipo_documento
    if t.startswith("Modello Redditi"):
        nota = "reddito annuo diviso 12 mesi; netto = dopo le imposte"
        if d.get("protocollo_telematico"):
            nota += " · trasmesso" + (f" il {d['data_presentazione']:%d/%m/%Y}" if d.get("data_presentazione") else "") \
                + f" (protocollo {d['protocollo_telematico']})"
        else:
            nota += " · ⚠ nessun protocollo telematico: chiedere la ricevuta di presentazione"
        return Sintesi("Regime fiscale", d.get("regime_fiscale"), d.get("reddito_mensile_lordo"),
                       d.get("reddito_mensile_netto"), nota)
    if t.startswith("Certificazione Unica"):
        return Sintesi("Tipo di reddito", d.get("tipo_reddito"), d.get("reddito_mensile_lordo"),
                       d.get("reddito_mensile_netto"), "media sui mesi del rapporto; netto = dopo ritenute e addizionali")
    if t.startswith(("Cedolino pensione", "Certificato di pensione")):
        nota = "rata mensile, pagata per 13 mensilità"
        if d.get("in_pensione_da"):
            nota += f" · in pensione da {d['in_pensione_da']} (dal {d['decorrenza_pensione']:%d/%m/%Y})"
        return Sintesi("Tipo di pensione", d.get("tipo_pensione"), d.get("reddito_mensile_lordo"),
                       d.get("reddito_mensile_netto"), nota)
    if t == "Busta paga":
        netto, nota = d.get("netto"), f"busta paga di {d.get('periodo') or 'periodo non indicato'}"
        if netto is None and d.get("netto_calcolato") is not None:
            netto, nota = d["netto_calcolato"], nota + " · netto CALCOLATO (non letto nel documento)"
        from .contratto import descrizione

        tipo = "Lavoro dipendente " + ("pubblico" if d.get("datore_di_lavoro") == "Pubblico" else "privato")
        contratto = descrizione(d)
        return Sintesi("Tipo di reddito", f"{tipo} · {contratto}" if contratto else tipo,
                       d.get("totale_competenze"), netto, nota)
    return None


def report_testuale(nome_file: str, r: Report) -> str:
    righe = ["=" * 72, f"{nome_file}  →  {r.tipo_documento}", "=" * 72]
    s = sintesi(r)
    if s:
        from .validators import formatta_euro

        righe += ["SINTESI",
                  f"  {s.etichetta + ':':<24} {s.categoria or 'non determinato'}",
                  f"  {'Importo mensile lordo:':<24} {formatta_euro(s.mensile_lordo)}",
                  f"  {'Importo mensile netto:':<24} {formatta_euro(s.mensile_netto)}",
                  f"  ({s.nota})", ""]
    righe.append("DATI ESTRATTI")
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
    # documenti con le posizioni delle parole (PDF e scansioni): valore nella stessa riga o nella cella sotto
    from .layout import cerca_valore, parole_correnti

    if parole_correnti():
        etichetta_trovata = False
        for etichetta in etichette:
            trovata, valore = cerca_valore(etichetta, regex_importo.pattern)
            etichetta_trovata |= trovata
            if valore is not None and parse_importo(valore) is not None:
                return parse_importo(valore)
        if etichetta_trovata:
            return None  # etichetta presente ma senza valore: meglio nessun valore che uno sbagliato
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
    from .layout import cerca_valore, parole_correnti

    if parole_correnti() and valore != r"(.+)":
        numerico = "\\d" in valore and "A-Z" not in valore
        for etichetta in etichette:
            _, trovato = cerca_valore(etichetta, valore, numerico=numerico, ignora_maiuscole=True)
            if trovato:
                return trovato
    for etichetta in etichette:
        m = re.search(etichetta + r"\s*[:\-]?\s*" + valore, testo, flags=re.IGNORECASE)
        if m:
            return m.group(1).strip()
    return None
