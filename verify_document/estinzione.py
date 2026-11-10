"""Conteggio sommario di estinzione anticipata (cessione del quinto, delega, prestito personale).

Dati da inserire: rata mensile, decorrenza (prima rata), scadenza (ultima rata), rate residue
(se non indicate: calcolate dalla data del conteggio) e, se noti, il TAN oppure l'importo finanziato.

Calcolo (ammortamento alla francese, rate mensili costanti):
- debito residuo lordo (montante)   = rata × rate residue
- capitale residuo                  = rata × (1 − (1 + i)^−n) / i      i = TAN / 12, n = rate residue
- interessi non dovuti              = montante − capitale residuo
- indennizzo (art. 125-sexies TUB)  = 1% del capitale residuo se mancano più di 12 mesi, altrimenti 0,5%;
  non dovuto se il capitale residuo non supera 10.000 € e senza superare gli interessi non dovuti
- costi da restituire (stima)       = costi iniziali × rate residue / rate totali (riduzione proporzionale)
- totale per estinguere (stima)     = capitale residuo + indennizzo − costi da restituire

Se manca il TAN ma è noto l'importo finanziato (capitale), il TAN viene ricavato dalla rata.
È una stima: l'importo esatto è quello del conteggio estintivo rilasciato dalla finanziaria.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from .validators import formatta_euro

SOGLIA_INDENNIZZO = Decimal("10000")
CENT = Decimal("0.01")


def mesi_tra(inizio: date, fine: date) -> int:
    """Numero di rate mensili da ``inizio`` a ``fine`` comprese (stesso mese = 1 rata)."""
    return (fine.year - inizio.year) * 12 + fine.month - inizio.month + 1


def _aggiungi_mesi(d: date, mesi: int) -> date:
    m = d.month - 1 + mesi
    anno, mese = d.year + m // 12, m % 12 + 1
    import calendar

    return date(anno, mese, min(d.day, calendar.monthrange(anno, mese)[1]))


def valore_attuale(rata: Decimal, n: int, tan: Decimal) -> Decimal:
    """Capitale corrispondente a ``n`` rate costanti al TAN annuo (in %)."""
    if n <= 0:
        return Decimal(0)
    i = tan / 100 / 12
    if i == 0:
        return rata * n
    return rata * (1 - (1 + i) ** -n) / i


def tan_da_capitale(rata: Decimal, n: int, capitale: Decimal) -> Decimal | None:
    """TAN (in %) che con ``n`` rate da ``rata`` restituisce ``capitale`` (ricerca per bisezione)."""
    if capitale <= 0 or n <= 0 or rata * n < capitale:
        return None
    basso, alto = Decimal(0), Decimal(100)
    for _ in range(80):
        medio = (basso + alto) / 2
        if valore_attuale(rata, n, medio) > capitale:
            basso = medio
        else:
            alto = medio
    return ((basso + alto) / 2).quantize(Decimal("0.001"), ROUND_HALF_UP)


@dataclass
class Conteggio:
    rata: Decimal
    rate_totali: int
    rate_pagate: int
    rate_residue: int
    decorrenza: date | None
    scadenza: date | None
    data_conteggio: date
    tan: Decimal | None
    montante_residuo: Decimal
    capitale_residuo: Decimal | None = None
    interessi_non_dovuti: Decimal | None = None
    indennizzo: Decimal | None = None
    costi_restituiti: Decimal | None = None
    totale_estinzione: Decimal | None = None
    avvisi: list[str] = field(default_factory=list)
    note: list[str] = field(default_factory=list)

    def righe(self) -> list[tuple[str, str]]:
        r = [("Rata mensile", formatta_euro(self.rata))]
        if self.decorrenza:
            r.append(("Decorrenza (prima rata)", f"{self.decorrenza:%m/%Y}"))
        if self.scadenza:
            r.append(("Scadenza (ultima rata)", f"{self.scadenza:%m/%Y}"))
        r += [("Rate totali", str(self.rate_totali)), ("Rate pagate", str(self.rate_pagate)),
              ("Rate residue", str(self.rate_residue)),
              ("Debito residuo lordo (rata × rate residue)", formatta_euro(self.montante_residuo))]
        if self.tan is not None:
            r.append(("TAN", f"{self.tan}%".replace(".", ",")))
        if self.capitale_residuo is not None:
            r += [("Capitale residuo", formatta_euro(self.capitale_residuo)),
                  ("Interessi non dovuti (risparmio)", formatta_euro(self.interessi_non_dovuti)),
                  ("Indennizzo estinzione anticipata", formatta_euro(self.indennizzo))]
        if self.costi_restituiti:
            r.append(("Costi da restituire (stima)", "− " + formatta_euro(self.costi_restituiti)))
        if self.totale_estinzione is not None:
            r.append(("TOTALE PER ESTINGUERE (stima)", formatta_euro(self.totale_estinzione)))
        return r

    def testo(self) -> str:
        larghezza = max(len(k) for k, _ in self.righe()) + 2
        out = [f"CONTEGGIO SOMMARIO DI ESTINZIONE al {self.data_conteggio:%d/%m/%Y}", ""]
        out += [f"{k + ':':<{larghezza}} {v}" for k, v in self.righe()]
        if self.avvisi:
            out += ["", "ATTENZIONE"] + [f"  ⚠ {a}" for a in self.avvisi]
        if self.note:
            out += ["", "NOTE"] + [f"  • {n}" for n in self.note]
        return "\n".join(out)


def calcola(rata: Decimal, decorrenza: date | None = None, scadenza: date | None = None,
            rate_totali: int | None = None, rate_residue: int | None = None, tan: Decimal | None = None,
            capitale: Decimal | None = None, costi: Decimal | None = None, data_conteggio: date | None = None,
            quinto: bool = True) -> Conteggio:
    """Calcola il conteggio. Servono la rata e almeno due tra decorrenza, scadenza, rate totali, rate residue."""
    oggi = data_conteggio or date.today()
    rata = Decimal(rata)
    if rata <= 0:
        raise ValueError("La rata deve essere maggiore di zero")
    avvisi: list[str] = []

    # durata complessiva
    if rate_totali is None:
        if decorrenza and scadenza:
            rate_totali = mesi_tra(decorrenza, scadenza)
        elif decorrenza is None and scadenza is None:
            raise ValueError("Indicare la durata: decorrenza e scadenza oppure il numero di rate totali")
    elif decorrenza and scadenza and mesi_tra(decorrenza, scadenza) != rate_totali:
        avvisi.append(f"Da decorrenza a scadenza ci sono {mesi_tra(decorrenza, scadenza)} rate, non {rate_totali}: "
                      "controllare le date")
    if decorrenza and scadenza and scadenza < decorrenza:
        raise ValueError("La scadenza è precedente alla decorrenza")
    if rate_totali is not None and decorrenza and not scadenza:
        scadenza = _aggiungi_mesi(decorrenza, rate_totali - 1)
    if rate_totali is not None and scadenza and not decorrenza:
        decorrenza = _aggiungi_mesi(scadenza, -(rate_totali - 1))

    # rate già scadute alla data del conteggio (la rata del mese in corso si considera pagata)
    scadute = None
    if decorrenza:
        scadute = max(0, min(rate_totali or 0, mesi_tra(decorrenza, oggi)))
    if rate_residue is None:
        if scadute is None or rate_totali is None:
            raise ValueError("Indicare le rate residue oppure la decorrenza")
        rate_residue = rate_totali - scadute
    if rate_totali is None:
        rate_totali = rate_residue + (scadute or 0)
    if rate_residue > rate_totali:
        raise ValueError(f"Le rate residue ({rate_residue}) superano le rate totali ({rate_totali})")
    rate_pagate = rate_totali - rate_residue
    if scadute is not None and rate_pagate != scadute:
        differenza = scadute - rate_pagate
        if differenza > 0:
            avvisi.append(f"Alla data del conteggio sono scadute {scadute} rate ma ne risultano pagate {rate_pagate}: "
                          f"{differenza} rate non pagate o sospese (possibile ritardo o insoluto)")
        else:
            avvisi.append(f"Risultano pagate {rate_pagate} rate ma ne sono scadute solo {scadute}: controllare "
                          "decorrenza e rate residue")

    c = Conteggio(rata, rate_totali, rate_pagate, rate_residue, decorrenza, scadenza, oggi, None,
                  (rata * rate_residue).quantize(CENT), avvisi=avvisi)

    if tan is None and capitale:
        tan = tan_da_capitale(rata, rate_totali, Decimal(capitale))
        if tan is not None:
            c.note.append(f"TAN ricavato da importo finanziato {formatta_euro(Decimal(capitale))} e rata: "
                          f"{str(tan).replace('.', ',')}%")
        else:
            c.avvisi.append("Importo finanziato non coerente con rata e durata (rata × rate inferiore al capitale)")
    c.tan = tan

    if tan is not None:
        capitale_residuo = valore_attuale(rata, rate_residue, Decimal(tan)).quantize(CENT)
        c.capitale_residuo = capitale_residuo
        c.interessi_non_dovuti = (c.montante_residuo - capitale_residuo).quantize(CENT)
        if rate_residue == 0:
            indennizzo = Decimal(0)
        elif capitale_residuo <= SOGLIA_INDENNIZZO:
            indennizzo = Decimal(0)
            c.note.append("Nessun indennizzo: capitale residuo non superiore a 10.000 € (art. 125-sexies TUB)")
        else:
            perc = Decimal("0.01") if rate_residue > 12 else Decimal("0.005")
            indennizzo = (capitale_residuo * perc).quantize(CENT, ROUND_HALF_UP)
            if indennizzo > c.interessi_non_dovuti:
                indennizzo = c.interessi_non_dovuti
            c.note.append(f"Indennizzo {'1%' if perc == Decimal('0.01') else '0,5%'} del capitale residuo "
                          f"({'più' if rate_residue > 12 else 'non più'} di un anno alla scadenza, art. 125-sexies TUB)")
        c.indennizzo = indennizzo
        if costi and rate_totali:
            c.costi_restituiti = (Decimal(costi) * rate_residue / rate_totali).quantize(CENT, ROUND_HALF_UP)
            c.note.append("Costi restituiti in proporzione alle rate residue (stima: dipende dal contratto)")
        c.totale_estinzione = (capitale_residuo + indennizzo - (c.costi_restituiti or 0)).quantize(CENT)
    else:
        c.note.append("Senza TAN o importo finanziato si può calcolare solo il debito residuo lordo: con il TAN "
                      "il programma toglie gli interessi non ancora maturati")

    if quinto and rate_totali:
        quaranta = -(-rate_totali * 4 // 10)  # 40% della durata, arrotondato per eccesso
        if rate_pagate >= quaranta:
            c.note.append(f"Rinnovo possibile: pagate {rate_pagate} rate su {rate_totali}, almeno il 40% della "
                          "durata (art. 39 DPR 180/1950)")
        else:
            c.note.append(f"Rinnovo della cessione: servono almeno {quaranta} rate pagate (40% della durata), "
                          f"ne mancano {quaranta - rate_pagate}")
    c.note.append("Stima indicativa: l'importo esatto è quello del conteggio estintivo della finanziaria")
    return c
