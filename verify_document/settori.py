"""Settori di lavoro (Privato, Pensionato, Statale, Autonomo) e documenti da chiedere per ciascuno.

Per ogni settore: l'elenco dei documenti (richiesti o facoltativi), il tipo di analisi da usare
all'apertura e quanti ne servono. ``stato_documenti`` dice quali sono già caricati e quali mancano.
"""

from __future__ import annotations

import re
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
ESTRATTO = VoceDocumento("estratto", "Estratto contributivo", "Estratto contributivo",
                         nota="per l'anzianità contributiva")

SETTORI: dict[str, dict] = {
    "Privato": {
        "icona": "🏢", "descrizione": "Dipendente di azienda privata",
        "documenti": [VoceDocumento("busta", "Buste paga", "Busta paga", minimo=3, nota="ultime 3 mensilità"),
                      CU, IDENTITA, ESTRATTO, REDDITI_FACOLTATIVO],
    },
    "Pensionato": {
        "icona": "👴", "descrizione": "Pensionato INPS o altre casse",
        "documenti": [VoceDocumento("cedolino_pensione", "Cedolino pensione", "Pensione (cedolino / ObisM)",
                                    nota="ultimo cedolino"),
                      VoceDocumento("obism", "ObisM", "Pensione (cedolino / ObisM)", nota="certificato di pensione"),
                      CU, IDENTITA, ESTRATTO, REDDITI_FACOLTATIVO],
    },
    "Statale": {
        "icona": "🏛", "descrizione": "Dipendente pubblico (NoiPA, enti, scuola)",
        "documenti": [VoceDocumento("busta", "Cedolini NoiPA", "Busta paga", minimo=3, nota="ultime 3 mensilità"),
                      CU, IDENTITA, ESTRATTO, REDDITI_FACOLTATIVO],
    },
    "Autonomo": {
        "icona": "💼", "descrizione": "Partita IVA, professionista, ditta individuale",
        "documenti": [VoceDocumento("redditi", "Unico / Redditi", "Modello Redditi PF", minimo=2,
                                    nota="ultimi 2 anni"),
                      VoceDocumento("ricevuta", "Ricevuta telematica", "Modello Redditi PF",
                                    nota="protocollo Agenzia Entrate (anche nel modello)"),
                      IDENTITA, ESTRATTO,
                      VoceDocumento("cu", "CU", "Certificazione Unica (CU)", richiesto=False,
                                    nota="se ha anche redditi da lavoro")],
    },
}


def chiavi_caricate(report: Report | None) -> list[str]:
    """Voci dell'elenco a cui corrisponde un documento (un Modello Redditi con protocollo vale anche come ricevuta)."""
    chiave = tipo_caricato(report)
    if chiave is None:
        return []
    if chiave == "redditi" and report.dati.get("protocollo_telematico"):
        return ["redditi", "ricevuta"]
    return [chiave]


def tipo_caricato(report: Report | None) -> str | None:
    """Chiave della voce a cui corrisponde un documento analizzato."""
    if report is None:
        return None
    t = report.tipo_documento
    if t.startswith("Ricevuta telematica"):
        return "ricevuta"
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
        for k in chiavi_caricate(r):
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
    return sorted({r.tipo_documento for r in reports
                   if r is not None and not set(chiavi_caricate(r)) & previsti})


# --- Riconoscimento del settore dai documenti caricati ---------------------------------------------------
_PUBBLICO = re.compile(r"noipa|ministero|ministro|istituto\s+(?:comprensivo|scolastico)|liceo|scuola|universit|"
                       r"\bcomune\s+di\b|\bregione\b|provincia|azienda\s+sanitaria|\basl\b|\basp\b|agenzia\s+delle|"
                       r"inps\b|inail\b|presidenza|prefettura|questura|carabinieri|polizia|esercito|marina|"
                       r"aeronautica|guardia\s+di\s+finanza|vigili\s+del\s+fuoco|tribunale|ragioneria",
                       re.IGNORECASE)


def _indizi(r: Report) -> list[tuple[str, int, str]]:
    """(settore, peso, motivo) suggeriti da un documento."""
    t, d = r.tipo_documento, r.dati
    if t.startswith(("Cedolino pensione", "Certificato di pensione")):
        return [("Pensionato", 3, t.split(" (")[0].lower())]
    if t == "Busta paga":
        if d.get("datore_di_lavoro") == "Pubblico":
            return [("Statale", 3, "cedolino di un ente pubblico")]
        return [("Privato", 3, "busta paga di un'azienda privata")]
    if t.startswith("Certificazione Unica"):
        tipo = d.get("tipo_reddito") or ""
        if tipo == "Pensione":
            return [("Pensionato", 2, "CU di pensione")]
        if tipo.startswith("Lavoro dipendente"):
            if _PUBBLICO.search(str(d.get("sostituto_imposta") or "")):
                return [("Statale", 2, "CU di un ente pubblico")]
            return [("Privato", 2, "CU da lavoro dipendente")]
        return []
    if t.startswith("Modello Redditi"):
        regime = d.get("regime_fiscale") or ""
        if regime.startswith(("Forfettario", "Regime di vantaggio", "Impresa", "Lavoro autonomo", "Socio")):
            return [("Autonomo", 3, f"Modello Redditi con regime {regime.split(' (')[0].lower()}")]
        if regime.startswith("Pensionato"):
            return [("Pensionato", 1, "Modello Redditi con redditi di pensione")]
        if regime.startswith("Lavoratore dipendente"):
            return [("Privato", 1, "Modello Redditi con redditi da lavoro dipendente")]
        return []
    if t.startswith("Ricevuta telematica"):
        return [("Autonomo", 1, "ricevuta del Modello Redditi")]
    if t == "Estratto contributivo":
        # la gestione con più settimane di contributi
        totali = []
        for c in r.controlli:
            m = re.match(r"([\d.]+) settimane", c.dettaglio) \
                if c.nome.startswith("Totale ") and c.nome != "Totale del documento" else None
            if m:
                totali.append((int(m.group(1).replace(".", "")), c.nome.removeprefix("Totale ").lower()))
        if not totali:
            return []
        gestione = max(totali)[1]
        if re.search(r"gestione separata|artigian|commerciant|autonom|professionist|coltivator", gestione):
            return [("Autonomo", 1, "estratto con contributi soprattutto da autonomo")]
        if re.search(r"pubblic|cpdel|ctps|inpdap|stato|scuola", gestione):
            return [("Statale", 1, "estratto con contributi soprattutto da dipendente pubblico")]
        if re.search(r"dipendent", gestione):
            return [("Privato", 1, "estratto con contributi soprattutto da lavoro dipendente")]
        return []
    return []  # documenti d'identità: nessun settore


def riconosci_settore(reports: list[Report | None]) -> tuple[str | None, str]:
    """Settore più probabile dai documenti e il motivo; (None, spiegazione) se non si capisce."""
    punti: dict[str, int] = {}
    motivi: dict[str, list[str]] = {}
    for r in reports:
        if r is None:
            continue
        for settore, peso, motivo in _indizi(r):
            punti[settore] = punti.get(settore, 0) + peso
            motivi.setdefault(settore, [])
            if motivo not in motivi[settore]:
                motivi[settore].append(motivo)
    if not punti:
        return None, "nessun documento indica il settore (es. solo documenti d'identità o documenti non leggibili)"
    ordinati = sorted(punti.items(), key=lambda x: -x[1])
    if len(ordinati) > 1 and ordinati[0][1] == ordinati[1][1]:
        return None, f"documenti di settori diversi ({ordinati[0][0]} e {ordinati[1][0]}): scegli tu il settore"
    settore = ordinati[0][0]
    return settore, ", ".join(motivi[settore])
