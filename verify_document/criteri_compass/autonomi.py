"""Clienti autonomi: per loro non ci sono criteri Compass di cessione del quinto / delega.

Vale la verifica del Modello Redditi (ex Unico): regime, reddito, presentazione telematica, coerenza con
estratto e ricevuta. La partita IVA si controlla sul sito dell'Agenzia delle Entrate: il programma NON la invia
(resta nella rete dell'ufficio), apre solo la pagina ufficiale e copia la partita IVA negli appunti.
"""

from __future__ import annotations

from ..report import Esito, Report, sintesi
from ..validators import formatta_euro

# Pagina ufficiale «Verifica partita IVA» dell'Agenzia delle Entrate (se cambia indirizzo, aggiornarlo qui)
URL_VERIFICA_PIVA = "https://telematici.agenziaentrate.gov.it/VerificaPIVA/Scegli.do?parameter=verificaPiva"

MESSAGGIO = ("Per i lavoratori autonomi (partita IVA, professionisti, ditte individuali) i criteri Compass di "
             "cessione del quinto e delegazione di pagamento non si applicano: vale la verifica del Modello Redditi "
             "(ex Unico) con la ricevuta di presentazione telematica.")


def riepilogo(reports: list[Report | None]) -> tuple[list[tuple[str, str]], list[str]]:
    """([(tag, testo)], partite IVA) — tag: titolo | ok | pre | ko | nota."""
    righe: list[tuple[str, str]] = []
    partite_iva: list[str] = []
    redditi = sorted((r for r in reports if r is not None and r.tipo_documento.startswith("Modello Redditi")),
                     key=lambda r: r.dati.get("periodo_imposta") or 0, reverse=True)
    if not redditi:
        righe.append(("ko", "Nessun Modello Redditi aperto: caricare l'Unico degli ultimi 2 anni e la ricevuta "
                            "telematica"))
    for r in redditi:
        d = r.dati
        righe.append(("titolo", f"Modello Redditi {d.get('periodo_imposta') or '(anno non letto)'} — "
                                f"esito {r.esito_globale.value}"))
        righe.append(("nota", f"Regime: {d.get('regime_fiscale') or 'non determinato'}"))
        s = sintesi(r)
        if s and s.mensile_netto is not None:
            righe.append(("nota", f"Reddito mensile: netto {formatta_euro(s.mensile_netto)}, lordo "
                                  f"{formatta_euro(s.mensile_lordo)}"))
        if d.get("protocollo_telematico"):
            righe.append(("ok", f"Presentato telematicamente: protocollo {d['protocollo_telematico']}"
                                + (f" del {d['data_presentazione']:%d/%m/%Y}" if d.get("data_presentazione") else "")))
        else:
            righe.append(("pre", "Nessun protocollo telematico nel modello: serve la ricevuta dell'Agenzia delle "
                                 "Entrate"))
        for c in r.controlli:
            if c.esito in (Esito.ERRORE, Esito.ATTENZIONE) and not c.nome.lower().startswith("codice fiscale"):
                righe.append(("ko" if c.esito == Esito.ERRORE else "pre", f"{c.nome}: {c.dettaglio}"))
        if d.get("partita_iva") and d["partita_iva"] not in partite_iva:
            partite_iva.append(d["partita_iva"])
        elif not d.get("partita_iva"):
            righe.append(("nota", "Partita IVA non letta nel modello: verificarla dal certificato di attribuzione"))
    ricevute = [r for r in reports if r is not None and r.tipo_documento.startswith("Ricevuta telematica")]
    for r in ricevute:
        d = r.dati
        righe.append(("ok" if r.esito_globale != Esito.ERRORE else "ko",
                      f"Ricevuta telematica {d.get('periodo_imposta') or ''}: protocollo "
                      f"{d.get('protocollo_telematico') or 'non letto'} — esito {d.get('esito_trasmissione') or '?'}"))
    return righe, partite_iva
