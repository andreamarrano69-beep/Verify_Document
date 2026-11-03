"""Finanziamenti e trattenute già presenti su stipendio o pensione: cessione del quinto,
delegazione di pagamento (prestito con delega), pignoramento. Calcola il quinto cedibile.

Limiti (DPR 180/1950):
- cessione del quinto: rata massima = 1/5 dello stipendio/pensione netti
- cessione + delegazione di pagamento: insieme al massimo 2/5 (un quinto ciascuna)
- cessione + pignoramento: insieme al massimo metà del netto

Il "netto" di riferimento è la retribuzione al netto delle sole ritenute fiscali e previdenziali
(lordo − contributi − IRPEF − addizionali), non il netto in busta, che è già ridotto dalle rate.
Per le pensioni la quota cedibile deve inoltre lasciare al pensionato almeno il trattamento minimo.
"""

from __future__ import annotations

from decimal import Decimal

from .report import Esito, Report, cerca_importo
from .validators import formatta_euro

ETICHETTE_IMPEGNI = {
    "cessione_quinto": [r"cessione\s+(?:del\s+)?(?:quinto|v\b|1\s*/\s*5)", r"\bc\.?\s*q\.?\s*s\.?\b"],
    "delegazione_pagamento": [r"delegazione\s+(?:di\s+)?pagamento", r"\bdelega\b", r"piccolo\s+prestito",
                              r"prestito\s+(?:inps|pensionistico|dipendenti|personale)"],
    "pignoramento": [r"pignorament[oi](?:\s+presso\s+terzi)?", r"trattenuta\s+per\s+pignoramento"],
}

NOMI = {
    "cessione_quinto": "cessione del quinto",
    "delegazione_pagamento": "delegazione di pagamento",
    "pignoramento": "pignoramento",
}


def leggi_impegni(testo: str) -> dict:
    return {k: cerca_importo(testo, et, solo_riga=True) for k, et in ETICHETTE_IMPEGNI.items()}


def controlla_impegni(r: Report, base_netta: Decimal | None, descrizione_base: str, pensione: bool = False) -> None:
    """Segnala le trattenute in corso, verifica i limiti di legge e calcola il quinto ancora disponibile."""
    d = r.dati
    ces = d.get("cessione_quinto") or Decimal(0)
    dele = d.get("delegazione_pagamento") or Decimal(0)
    pig = d.get("pignoramento") or Decimal(0)

    in_corso = [(NOMI[k], d[k]) for k in ("cessione_quinto", "delegazione_pagamento") if d.get(k)]
    if in_corso:
        r.aggiungi("Cessione del quinto / prestiti", Esito.ATTENZIONE,
                   "Già presenti trattenute per finanziamenti: "
                   + ", ".join(f"{n} {formatta_euro(v)}" for n, v in in_corso) + " al mese")
    if pig:
        r.aggiungi("Pignoramento", Esito.ATTENZIONE, f"Trattenuta per pignoramento: {formatta_euro(pig)} al mese")

    if not base_netta or base_netta <= 0:
        return
    quinto = (base_netta / 5).quantize(Decimal("0.01"))
    d["base_netta_quinto"] = base_netta
    d["quinto_cedibile"] = quinto
    d["cessione_disponibile"] = max(quinto - ces, Decimal(0))
    d["delegazione_disponibile"] = max(quinto - dele, Decimal(0))

    errori = []
    if ces > quinto + 1:
        errori.append(f"rata di cessione {formatta_euro(ces)} oltre il quinto {formatta_euro(quinto)}")
    if ces + dele > quinto * 2 + 1:
        errori.append(f"cessione + delegazione {formatta_euro(ces + dele)} oltre i 2/5 {formatta_euro(quinto * 2)}")
    if pig and ces + pig > base_netta / 2 + 1:
        errori.append(f"cessione + pignoramento {formatta_euro(ces + pig)} oltre la metà del netto")

    calcolo = f"1/5 di {formatta_euro(base_netta)} ({descrizione_base})"
    nota_pensione = " — per le pensioni deve restare almeno il trattamento minimo INPS" if pensione else ""
    if errori:
        r.aggiungi("Quinto cedibile", Esito.ERRORE,
                   f"Quinto {formatta_euro(quinto)} = {calcolo}; " + "; ".join(errori)
                   + ": non consentito dalla legge (DPR 180/1950), documento da verificare")
    elif ces or dele:
        r.aggiungi("Quinto cedibile", Esito.INFO,
                   f"Quinto {formatta_euro(quinto)} = {calcolo}. Ancora disponibile: cessione "
                   f"{formatta_euro(d['cessione_disponibile'])}, delegazione {formatta_euro(d['delegazione_disponibile'])}"
                   + nota_pensione)
    else:
        r.aggiungi("Quinto cedibile", Esito.OK,
                   f"Nessuna cessione in corso: rata massima cedibile {formatta_euro(quinto)} = {calcolo}"
                   + nota_pensione)
