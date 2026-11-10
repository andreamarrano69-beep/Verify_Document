"""Scheda del cliente per settore: i dati che servono alla pratica, in una tabella per il report PDF.

- tutti i settori: documenti richiesti presenti e mancanti, reddito mensile, anzianità contributiva,
  esito dei controlli incrociati con l'INPS, fattibilità della cessione del quinto
- Privato / Statale: datore di lavoro, contratto, qualifica, assunzione e anzianità di servizio
- Pensionato: tipo di pensione, ente, decorrenza e da quanto tempo è in pensione
- Autonomo: regime fiscale, anni dichiarati, presentazione telematica
"""

from __future__ import annotations

from datetime import date

from .report import Esito, Report, sintesi
from .settori import SETTORI, riconosci_settore, stato_documenti
from .validators import formatta_euro


def _ultimo(documenti: list[Report], *tipi: str) -> Report | None:
    from .archivio import data_documento

    scelti = [r for r in documenti if r.tipo_documento.startswith(tipi)]
    return max(scelti, key=lambda r: data_documento(r) or date.min, default=None)


def _anzianita_servizio(assunzione: date, riferimento: date) -> str:
    mesi = (riferimento.year - assunzione.year) * 12 + riferimento.month - assunzione.month
    anni, resto = divmod(max(mesi, 0), 12)
    return f"{anni} anni e {resto} mesi" if anni else f"{resto} mesi"


def scheda_cliente(documenti: list[tuple[str, Report]], confronto=None,
                   settore: str | None = None) -> tuple[str | None, list[tuple[str, str]]]:
    """(settore, [(voce, valore)]) per la scheda del cliente."""
    reports = [r for _, r in documenti if r is not None]
    riconosciuto = settore is None
    if settore is None:
        settore, _ = riconosci_settore(reports)
    righe: list[tuple[str, str]] = []
    if settore:
        righe.append(("Settore", settore + (" (riconosciuto dai documenti)" if riconosciuto else "")))
        stati = stato_documenti(settore, reports)
        presenti = [s.voce.etichetta + (f" ({s.caricati})" if s.caricati > 1 else "") for s in stati if s.caricati]
        mancanti = [s.voce.etichetta + (f" ({s.voce.minimo - s.caricati} di {s.voce.minimo})"
                                        if s.stato == "parziale" else "")
                    for s in stati if s.voce.richiesto and s.stato != "completo"]
        righe.append(("Documenti presenti", ", ".join(presenti) or "nessuno"))
        righe.append(("Documenti mancanti", ", ".join(mancanti) or "nessuno: documentazione completa"))
    else:
        righe.append(("Settore", "non determinato dai documenti"))

    busta = _ultimo(reports, "Busta paga")
    # il cedolino riporta le trattenute in corso (cessioni): preferito all'ObisM
    pensione = _ultimo(reports, "Cedolino pensione") or _ultimo(reports, "Certificato di pensione")
    redditi = [r for r in reports if r.tipo_documento.startswith("Modello Redditi")]
    if settore in ("Privato", "Statale") and busta:
        d = busta.dati
        righe.append(("Datore di lavoro", (d.get("azienda") or "non letto")
                      + (" (pubblica amministrazione)" if d.get("datore_di_lavoro") == "Pubblico" else "")))
        from .contratto import descrizione

        righe.append(("Contratto", descrizione(d) or "non indicato nella busta paga"))
        if d.get("data_fine_contratto"):
            righe.append(("Fine del contratto", f"{d['data_fine_contratto']:%d/%m/%Y}"))
        if d.get("data_assunzione"):
            from .fattibilita import _riferimento

            righe.append(("Assunzione", f"{d['data_assunzione']:%d/%m/%Y} (anzianità di servizio "
                                        f"{_anzianita_servizio(d['data_assunzione'], _riferimento(d))})"))
    if settore == "Pensionato" and pensione:
        d = pensione.dati
        righe.append(("Tipo di pensione", " · ".join(x for x in (d.get("tipo_pensione"), d.get("ente")) if x)))
        if d.get("decorrenza_pensione"):
            righe.append(("Decorrenza", f"{d['decorrenza_pensione']:%d/%m/%Y} — in pensione da "
                                        f"{d.get('in_pensione_da') or '?'}"
                                        + (f", a {d['eta_al_pensionamento']} anni" if d.get("eta_al_pensionamento")
                                           else "")))
        else:
            righe.append(("Decorrenza", "non indicata nei documenti"))
    if settore == "Autonomo" and redditi:
        ultimo = max(redditi, key=lambda r: r.dati.get("periodo_imposta") or 0).dati
        righe.append(("Regime fiscale", ultimo.get("regime_fiscale") or "non determinato"))
        anni = sorted({r.dati["periodo_imposta"] for r in redditi if r.dati.get("periodo_imposta")})
        righe.append(("Anni dichiarati", ", ".join(map(str, anni)) or "non letti"))
        if ultimo.get("protocollo_telematico"):
            righe.append(("Presentazione telematica", f"protocollo {ultimo['protocollo_telematico']}"
                          + (f" del {ultimo['data_presentazione']:%d/%m/%Y}" if ultimo.get("data_presentazione")
                             else "")))
        else:
            ricevuta = any(r.tipo_documento.startswith("Ricevuta") for r in reports)
            righe.append(("Presentazione telematica", "ricevuta presente" if ricevuta
                          else "NESSUN protocollo: chiedere la ricevuta dell'Agenzia delle Entrate"))

    # reddito mensile: documento principale del settore
    principale = {"Pensionato": pensione, "Autonomo": max(redditi, key=lambda r: r.dati.get("periodo_imposta") or 0,
                                                          default=None)}.get(settore, busta) if settore else None
    principale = principale or busta or pensione
    s = sintesi(principale) if principale else None
    if s and (s.mensile_netto is not None or s.mensile_lordo is not None):
        righe.append(("Reddito mensile", f"netto {formatta_euro(s.mensile_netto)} · lordo {formatta_euro(s.mensile_lordo)}"
                                         f" ({principale.tipo_documento.split(' (')[0]})"))

    estratto = _ultimo(reports, "Estratto contributivo")
    if estratto:
        d = estratto.dati
        righe.append(("Anzianità contributiva", f"{d.get('anzianita_contributiva') or '?'} "
                      f"({d.get('anzianita_settimane') or '?'} settimane)"
                      + (f", ultimo contributo {d['ultimo_contributo']:%m/%Y}" if d.get("ultimo_contributo") else "")))

    if confronto is not None:
        incroci = [c for c in confronto.report.controlli if "↔" in c.nome and ("estratto" in c.nome or
                                                                              "ricevuta" in c.nome)]
        if incroci:
            n = {e: sum(c.esito == e for c in incroci) for e in Esito}
            testo = f"{n[Esito.OK]} coerenti, {n[Esito.ATTENZIONE]} da verificare, {n[Esito.ERRORE]} non coerenti"
            peggiori = [c.nome for c in incroci if c.esito == Esito.ERRORE]
            righe.append(("Controlli con INPS / Agenzia", testo + (f" ({', '.join(peggiori)})" if peggiori else "")))
        elif settore and not estratto:
            righe.append(("Controlli con INPS", "non eseguiti: manca l'estratto contributivo"))

    q = principale if principale is not None and principale.dati.get("fattibilita_quinto") else \
        next((r for r in (busta, pensione) if r is not None and r.dati.get("fattibilita_quinto")), None)
    if q is not None:
        d = q.dati
        if d["fattibilita_quinto"] == "Possibile":
            durata = f"{d['durata_massima_mesi']} mesi" if d.get("durata_massima_mesi") else \
                "fino alla scadenza del contratto"
            righe.append(("Cessione del quinto", f"possibile: rata fino a {formatta_euro(d.get('cessione_disponibile'))}, "
                                                 f"durata massima {durata}"))
        else:
            motivo = next((c.dettaglio for c in q.controlli if c.nome == "Cessione del quinto"), "")
            righe.append(("Cessione del quinto", motivo or "non possibile"))
    return settore, righe


def voci_settore(settore: str) -> list[str]:
    return [v.etichetta for v in SETTORI[settore]["documenti"]]
