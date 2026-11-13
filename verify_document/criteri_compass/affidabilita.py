"""Affidabilità dei documenti della pratica, da mostrare insieme all'esito dei criteri Compass.

Prima di guardare i criteri bisogna sapere se i documenti sono credibili:
- controlli di ogni documento (quadratura del netto, calcolo delle voci, contributi, imponibili, codice
  fiscale, date) — errori e punti da verificare
- rischio di alterazione dei file PDF (ALTO = non affidabile, MEDIO = da verificare)
- controlli incrociati tra documenti e con l'estratto contributivo INPS (busta ↔ estratto, CU ↔ estratto, ...)

Livelli: AFFIDABILI · DA VERIFICARE · NON COERENTI (nessun documento: NON VALUTATA).
Nel testo solo tipo e periodo dei documenti: niente nomi di file, nomi o codici fiscali (il risultato si può
copiare o far riassumere all'AI).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..report import Esito, Report

AFFIDABILI = "AFFIDABILI"
DA_VERIFICARE = "DA VERIFICARE"
NON_COERENTI = "NON COERENTI"
NON_VALUTATA = "NON VALUTATA"

# gruppi che non riguardano la veridicità del documento (sono valutati dai criteri)
GRUPPI_ESCLUSI = {"Contratto di lavoro", "Fattibilità cessione del quinto", "Anzianità contributiva",
                  "Periodi contributivi", "Pensione"}
# controlli che descrivono la situazione del cliente (prestiti in corso, importi), non la veridicità del documento
INFORMATIVI = {"Cessione del quinto / prestiti", "Pignoramento", "Quinto cedibile", "Importo mensile",
               "Netto mensile", "Tipo di pensione", "Decorrenza della pensione"}
ATTENZIONE_NON_RILEVANTE = {"Data assunzione"}  # «assunzione recente»: è un criterio, non un dubbio sul documento
RILEVANTI = ("Busta paga", "Cedolino pensione", "Certificato di pensione", "Estratto contributivo",
             "Certificazione Unica", "Carta", "Patente", "Passaporto", "Tessera", "Documento")


@dataclass
class Affidabilita:
    livello: str
    righe: list[tuple[str, str]] = field(default_factory=list)  # (ok | pre | ko | nota, testo)

    def testo(self) -> str:
        simboli = {"ok": "✅", "pre": "⚠️", "ko": "❌", "nota": "ℹ️"}
        return "\n".join([f"AFFIDABILITÀ DEI DOCUMENTI: {self.livello}"]
                         + [f"  {simboli[t]} {r}" for t, r in self.righe])


def _nome_documento(r: Report) -> str:
    from ..archivio import descrizione_periodo

    periodo = descrizione_periodo(r)
    return r.tipo_documento.split(" (")[0] + (f" {periodo}" if periodo else "")


def _motivo(c) -> str:
    if c.nome.lower().startswith("codice fiscale"):  # il dettaglio contiene il codice fiscale
        return c.nome + (" non valido" if "NON valido" in c.dettaglio else " da verificare")
    dettaglio = c.dettaglio if len(c.dettaglio) <= 150 else c.dettaglio[:147] + "…"
    return f"{c.nome}: {dettaglio}"


def valuta(reports: list[Report | None], confronto=None) -> Affidabilita:
    docs = [r for r in reports if r is not None and r.tipo_documento.startswith(RILEVANTI)]
    if not docs:
        return Affidabilita(NON_VALUTATA, [("nota", "Nessun documento aperto: l'affidabilità dei documenti non è "
                                                    "stata valutata (esito solo sui dati inseriti a mano)")])
    a = Affidabilita(AFFIDABILI)
    gravita = {AFFIDABILI: 0, DA_VERIFICARE: 1, NON_COERENTI: 2}

    def peggiora(livello):
        if gravita[livello] > gravita[a.livello]:
            a.livello = livello

    for r in docs:
        nome = _nome_documento(r)
        errori = [c for c in r.controlli if c.esito == Esito.ERRORE and c.gruppo not in GRUPPI_ESCLUSI
                  and c.nome not in INFORMATIVI]
        attenzioni = [c for c in r.controlli if c.esito == Esito.ATTENZIONE and c.gruppo not in GRUPPI_ESCLUSI
                      and c.nome not in INFORMATIVI | ATTENZIONE_NON_RILEVANTE]
        rischio = str(r.dati.get("rischio_alterazione") or "")
        if rischio.startswith("ALTO"):
            peggiora(NON_COERENTI)
            a.righe.append(("ko", f"{nome}: rischio di alterazione del file PDF ALTO"))
        elif rischio.startswith("MEDIO"):
            peggiora(DA_VERIFICARE)
            a.righe.append(("pre", f"{nome}: rischio di alterazione del file PDF MEDIO (chiedere l'originale)"))
        if errori:
            peggiora(NON_COERENTI)
            for c in errori[:4]:
                a.righe.append(("ko", f"{nome} — {_motivo(c)}"))
        elif attenzioni:
            peggiora(DA_VERIFICARE)
            a.righe.append(("pre", f"{nome} — " + "; ".join(c.nome for c in attenzioni[:4])
                            + (" …" if len(attenzioni) > 4 else "")))
        elif not rischio.startswith(("ALTO", "MEDIO")):
            a.righe.append(("ok", f"{nome}: controlli superati"))

    # controlli incrociati (tra documenti e con l'INPS)
    if confronto is not None:
        incroci = [c for c in confronto.report.controlli if c.gruppo != "Identità" and c.nome != "Documenti"]
        inps = [c for c in incroci if "estratto" in c.nome or "ricevuta" in c.nome]
        for c in incroci:
            if c.esito == Esito.ERRORE:
                peggiora(NON_COERENTI)
                a.righe.append(("ko", f"Confronto — {_motivo(c)}"))
            elif c.esito == Esito.ATTENZIONE and c in inps:
                peggiora(DA_VERIFICARE)
                a.righe.append(("pre", f"Confronto — {_motivo(c)}"))
        if inps and not any(c.esito in (Esito.ERRORE, Esito.ATTENZIONE) for c in inps):
            a.righe.append(("ok", f"Controlli con l'estratto INPS: {sum(c.esito == Esito.OK for c in inps)} coerenti"))
    if not any(r.tipo_documento == "Estratto contributivo" for r in docs):
        a.righe.append(("nota", "Senza l'estratto contributivo INPS non si può confermare che il rapporto di lavoro "
                                "o la pensione siano registrati all'INPS: consigliato"))
    return a


def esito_finale(aff: Affidabilita, assumibili: list[str], preaccettazione: list[str],
                 da_verificare: list[str] | None = None) -> tuple[str, str]:
    """(tag, testo) dell'esito complessivo: documenti + criteri."""
    da_verificare = da_verificare or []
    criteri = (f"assumibile con {', '.join(assumibili)}" if assumibili else
               f"solo in pre-accettazione con {', '.join(preaccettazione)}" if preaccettazione else
               f"da completare (dati mancanti) per {len(da_verificare)} compagnie" if da_verificare else
               "non assumibile con nessuna compagnia")
    if aff.livello == NON_COERENTI:
        return "ko", (f"❌ DOCUMENTI NON COERENTI — risolvere prima di presentare la pratica. Criteri: {criteri} "
                      "(valido solo se i documenti sono veri)")
    if aff.livello == DA_VERIFICARE:
        return "pre", f"⚠️ DOCUMENTI DA VERIFICARE · Criteri: {criteri}"
    if aff.livello == NON_VALUTATA:
        return "pre", f"ℹ️ Documenti non valutati · Criteri: {criteri}"
    tag = "ok" if assumibili else "pre" if preaccettazione or da_verificare else "ko"
    simbolo = {"ok": "✅", "pre": "⚠️", "ko": "❌"}[tag]
    return tag, f"{simbolo} DOCUMENTI AFFIDABILI · Criteri: {criteri}"
