"""Fattibilità della cessione del quinto (e della delegazione di pagamento) da busta paga o cedolino pensione.

- rata massima: un quinto dello stipendio/pensione netti, meno le cessioni già in corso
  (per i dipendenti si può aggiungere una delegazione, un altro quinto)
- durata: da 24 a 120 mesi, ridotta da:
  * contratto a tempo determinato: non oltre la scadenza del contratto
  * età a fine finanziamento: di solito entro i 70 anni per i dipendenti e i 90 per i pensionati
    (limiti delle assicurazioni, variano da una finanziaria all'altra: sono modificabili)
- non cedibili: assegno sociale, invalidità civile e altre prestazioni assistenziali; contratto già scaduto;
  apprendisti e lavoro intermittente/somministrato di solito non sono accettati
- simulazione: importo finanziabile (capitale) per 60, 84 e 120 mesi a un TAN indicativo

È una stima: decide la finanziaria (età, anzianità di servizio, dimensione dell'azienda, TFR, ...).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_DOWN, Decimal

from .estinzione import valore_attuale
from .report import Esito, Report
from .validators import formatta_euro

GRUPPO = "Fattibilità cessione del quinto"
DURATA_MASSIMA = 120
DURATA_MINIMA = 24
ETA_FINE_DIPENDENTI = 70
ETA_FINE_PENSIONATI = 90
TAN_INDICATIVO = Decimal("6.5")
DURATE = (60, 84, 120)


@dataclass
class Fattibilita:
    possibile: bool
    rata_massima: Decimal | None
    durata_massima: int | None
    motivi: list[str] = field(default_factory=list)       # perché non è possibile o è limitata
    note: list[str] = field(default_factory=list)
    simulazione: list[tuple[int, Decimal, Decimal, Decimal]] = field(default_factory=list)  # mesi, rata, montante, capitale
    delegazione: Decimal | None = None
    durata_incerta: bool = False   # contratto a termine senza data di fine: durata da verificare


def _mesi(da: date, a: date) -> int:
    return (a.year - da.year) * 12 + a.month - da.month


def _riferimento(d: dict) -> date:
    from .busta_paga import _anno_mese_periodo

    am = _anno_mese_periodo(d.get("periodo"))
    return date(*am, 1) if am else date.today()


def valuta(r: Report, tan: Decimal = TAN_INDICATIVO, eta_fine_dipendenti: int = ETA_FINE_DIPENDENTI,
           eta_fine_pensionati: int = ETA_FINE_PENSIONATI) -> Fattibilita | None:
    d = r.dati
    t = r.tipo_documento
    pensione = t.startswith(("Cedolino pensione", "Certificato di pensione"))
    if t != "Busta paga" and not pensione:
        return None
    rata = d.get("cessione_disponibile")
    f = Fattibilita(True, rata, DURATA_MASSIMA)
    oggi = _riferimento(d)

    if rata is None:
        f.possibile = False
        f.motivi.append("rata massima non calcolabile (netto o trattenute non letti)")
    elif rata <= 0:
        f.possibile = False
        f.motivi.append("quinto già interamente impegnato da altre cessioni")
    if d.get("pignoramento"):
        f.note.append(f"pignoramento in corso ({formatta_euro(d['pignoramento'])}): molte finanziarie non procedono")

    nascita = d.get("data_nascita_da_cf")
    eta_fine = eta_fine_pensionati if pensione else eta_fine_dipendenti
    if nascita:
        fine_eta = date(nascita.year + eta_fine, nascita.month, 1)
        mesi = _mesi(oggi, fine_eta)
        if mesi < f.durata_massima:
            f.durata_massima = max(mesi, 0)
            f.note.append(f"durata limitata dall'età: a fine finanziamento al massimo {eta_fine} anni")

    if pensione:
        if d.get("categoria") in ("PS", "AS", "INVCIV", "CIV", "INV") or "assistenzial" in str(d.get("tipo_pensione")):
            f.possibile = False
            f.motivi.append("prestazione assistenziale (assegno sociale / invalidità civile): non cedibile")
        if d.get("tredicesima"):
            f.note.append("cedolino con tredicesima: rata calcolata su un mese ordinario")
    else:
        tipo = d.get("tipo_contratto") or ""
        fine = d.get("data_fine_contratto")
        if tipo.startswith("Tempo determinato"):
            if fine:
                mesi = _mesi(oggi, fine)
                if mesi <= 0:
                    f.possibile = False
                    f.motivi.append(f"contratto a termine già scaduto ({fine:%d/%m/%Y})")
                elif mesi < f.durata_massima:
                    f.durata_massima = mesi
                    f.note.append(f"contratto a termine: durata non oltre la scadenza del {fine:%d/%m/%Y}")
            else:
                f.durata_incerta = True
        elif tipo == "Apprendistato":
            f.note.append("apprendistato: accettato solo da alcune finanziarie")
        elif tipo.startswith(("Lavoro intermittente", "Somministrazione")):
            f.note.append(f"{tipo.lower()}: di solito non accettato")
        if d.get("datore_di_lavoro") == "Pubblico":
            f.note.append("dipendente pubblico: condizioni migliori (convenzioni, TFS a garanzia)")
        delega = d.get("delegazione_disponibile")
        if delega and delega > 0:
            f.delegazione = delega
    if f.durata_massima is not None and f.durata_massima < DURATA_MINIMA:
        f.possibile = False
        f.motivi.append(f"durata possibile solo {f.durata_massima} mesi (minimo {DURATA_MINIMA})")

    if f.possibile and rata and not f.durata_incerta:
        for mesi in DURATE:
            if mesi <= f.durata_massima:
                f.simulazione.append((mesi, rata, rata * mesi, valore_attuale(rata, mesi, tan).quantize(Decimal("1"),
                                                                                                         ROUND_DOWN)))
        if f.durata_massima not in DURATE and f.durata_massima >= DURATA_MINIMA:
            n = f.durata_massima
            f.simulazione.append((n, rata, rata * n, valore_attuale(rata, n, tan).quantize(Decimal("1"), ROUND_DOWN)))
    return f


def aggiungi_controlli(r: Report, tan: Decimal = TAN_INDICATIVO) -> None:
    f = valuta(r, tan)
    if f is None or r.dati.get("mensilita_aggiuntiva"):
        return
    r.dati["fattibilita_quinto"] = "Possibile" if f.possibile else "Non possibile"
    r.dati["durata_massima_mesi"] = f.durata_massima if f.possibile else None
    if not f.possibile:
        r.aggiungi("Cessione del quinto", Esito.ATTENZIONE, "NON possibile: " + "; ".join(f.motivi), GRUPPO)
    elif f.durata_incerta:
        r.dati["durata_massima_mesi"] = None
        r.aggiungi("Cessione del quinto", Esito.ATTENZIONE,
                   f"Rata fino a {formatta_euro(f.rata_massima)}, ma contratto a termine senza data di fine letta: "
                   "la durata non può superare la scadenza del contratto — chiedere il contratto", GRUPPO)
    else:
        r.aggiungi("Cessione del quinto", Esito.OK,
                   f"Possibile: rata fino a {formatta_euro(f.rata_massima)} per al massimo {f.durata_massima} mesi"
                   + (f"; in più delegazione fino a {formatta_euro(f.delegazione)}" if f.delegazione else ""), GRUPPO)
        migliore = max(f.simulazione, key=lambda x: x[0], default=None)
        if migliore:
            mesi, rata, montante, capitale = migliore
            r.aggiungi("Importo finanziabile (stima)", Esito.INFO,
                       f"{mesi} rate da {formatta_euro(rata)} = {formatta_euro(montante)}; capitale circa "
                       f"{formatta_euro(capitale)} al TAN indicativo {str(tan).replace('.', ',')}%", GRUPPO)
    for nota in f.note:
        r.aggiungi("Nota", Esito.INFO, nota, GRUPPO)
