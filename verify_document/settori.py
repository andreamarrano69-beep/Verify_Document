"""Settori di lavoro (Privato, Pensionato, Statale, Autonomo) e documenti da chiedere per ciascuno.

Per ogni settore: l'elenco dei documenti (richiesti o facoltativi), il tipo di analisi da usare
all'apertura e quanti ne servono. ``stato_documenti`` dice quali sono già caricati e quali mancano.
"""

from __future__ import annotations

from dataclasses import dataclass

from .report import Report


@dataclass(frozen=True)
class VoceDocumento:
    chiave: str          # identifica il tipo di documento caricato (vedi tipo_caricato)
    etichetta: str       # testo del pulsante
    tipo_analisi: str    # voce dell'elenco «Tipo di documento» da usare all'apertura
    richiesto: bool = True
    minimo: int = 1      # quanti documenti servono (es. 3 buste paga)
    nota: str = ""


IDENTITA = VoceDocumento("identita", "Documento d'identità", "Documento d'identità", nota="carta d'identità, patente, …")
CU = VoceDocumento("cu", "CU", "Certificazione Unica (CU)", nota="ultima Certificazione Unica")
REDDITI_FACOLTATIVO = VoceDocumento("redditi", "Unico / Redditi", "Modello Redditi PF", richiesto=False)
ESTRATTO_FACOLTATIVO = VoceDocumento("estratto", "Estratto contributivo", "Estratto contributivo", richiesto=False,
                                     nota="per l'anzianità contributiva")

SETTORI: dict[str, dict] = {
    "Privato": {
        "icona": "🏢", "descrizione": "Dipendente di azienda privata",
        "documenti": [VoceDocumento("busta", "Buste paga", "Busta paga", minimo=3, nota="ultime 3 mensilità"),
                      CU, IDENTITA, REDDITI_FACOLTATIVO, ESTRATTO_FACOLTATIVO],
    },
    "Pensionato": {
        "icona": "👴", "descrizione": "Pensionato INPS o altre casse",
        "documenti": [VoceDocumento("cedolino_pensione", "Cedolino pensione", "Pensione (cedolino / ObisM)",
                                    nota="ultimo cedolino"),
                      VoceDocumento("obism", "ObisM", "Pensione (cedolino / ObisM)", nota="certificato di pensione"),
                      CU, IDENTITA, REDDITI_FACOLTATIVO],
    },
    "Statale": {
        "icona": "🏛", "descrizione": "Dipendente pubblico (NoiPA, enti, scuola)",
        "documenti": [VoceDocumento("busta", "Cedolini NoiPA", "Busta paga", minimo=3, nota="ultime 3 mensilità"),
                      CU, IDENTITA, REDDITI_FACOLTATIVO, ESTRATTO_FACOLTATIVO],
    },
    "Autonomo": {
        "icona": "💼", "descrizione": "Partita IVA, professionista, ditta individuale",
        "documenti": [VoceDocumento("redditi", "Unico / Redditi", "Modello Redditi PF", minimo=2,
                                    nota="ultimi 2 anni"),
                      IDENTITA, ESTRATTO_FACOLTATIVO,
                      VoceDocumento("cu", "CU", "Certificazione Unica (CU)", richiesto=False,
                                    nota="se ha anche redditi da lavoro")],
    },
}


def tipo_caricato(report: Report | None) -> str | None:
    """Chiave della voce a cui corrisponde un documento analizzato."""
    if report is None:
        return None
    t = report.tipo_documento
    if t == "Busta paga":
        return "busta"
    if t == "Cedolino pensione":
        return "cedolino_pensione"
    if t.startswith("Certificato di pensione"):
        return "obism"
    if t.startswith("Certificazione Unica"):
        return "cu"
    if t.startswith("Modello Redditi"):
        return "redditi"
    if t == "Estratto contributivo":
        return "estratto"
    from .archivio import CATEGORIA_IDENTITA, categoria

    return "identita" if categoria(report) == CATEGORIA_IDENTITA else None


@dataclass
class StatoVoce:
    voce: VoceDocumento
    caricati: int

    @property
    def stato(self) -> str:
        """"completo", "parziale" (meno del minimo), "manca" (richiesto) o "facoltativo" (non caricato)."""
        if self.caricati >= self.voce.minimo:
            return "completo"
        if self.caricati:
            return "parziale"
        return "manca" if self.voce.richiesto else "facoltativo"

    @property
    def testo(self) -> str:
        if self.stato == "completo":
            return f"✔ {self.voce.etichetta} ({self.caricati})" if self.voce.minimo > 1 or self.caricati > 1 \
                else f"✔ {self.voce.etichetta}"
        if self.stato == "parziale":
            return f"◐ {self.voce.etichetta} {self.caricati} di {self.voce.minimo}"
        return f"{'○' if self.stato == 'manca' else '＋'} {self.voce.etichetta}"


def stato_documenti(settore: str, reports: list[Report | None]) -> list[StatoVoce]:
    conteggio: dict[str, int] = {}
    for r in reports:
        k = tipo_caricato(r)
        if k:
            conteggio[k] = conteggio.get(k, 0) + 1
    return [StatoVoce(v, conteggio.get(v.chiave, 0)) for v in SETTORI[settore]["documenti"]]


def riepilogo(stati: list[StatoVoce]) -> str:
    richiesti = [s for s in stati if s.voce.richiesto]
    completi = [s for s in richiesti if s.stato == "completo"]
    mancano = [s.voce.etichetta + (f" ({s.voce.minimo - s.caricati})" if s.stato == "parziale" else "")
               for s in richiesti if s.stato != "completo"]
    testo = f"Documenti richiesti: {len(completi)} di {len(richiesti)}"
    return testo + (" — mancano: " + ", ".join(mancano) if mancano else " — completo ✔")


def documenti_estranei(settore: str, reports: list[Report | None]) -> list[str]:
    """Documenti caricati che non fanno parte dell'elenco del settore (es. cedolino pensione tra i Privati)."""
    previsti = {v.chiave for v in SETTORI[settore]["documenti"]}
    return sorted({r.tipo_documento for r in reports if r is not None and tipo_caricato(r) not in previsti})
