"""Presentazione telematica del Modello Redditi PF (ex Unico) all'Agenzia delle Entrate.

Una dichiarazione stampata dal programma del commercialista può essere una bozza mai inviata: vale
solo se è stata trasmessa. La prova è il **protocollo telematico** (17 cifre + 6 cifre, es.
«25102812345678901 - 000001») riportato sulla dichiarazione inviata o sulla **ricevuta** dell'Agenzia
(«comunicazione di avvenuto ricevimento»).

Si leggono: protocollo, data di presentazione, intermediario (CAF/commercialista) con la data
dell'impegno a trasmettere, esito della ricevuta (accolta / scartata), dichiarazione correttiva o integrativa.

Controlli:
- presenza del protocollo o della ricevuta (senza: possibile bozza)
- ricevuta scartata = dichiarazione non presentata
- data di presentazione nell'anno successivo al periodo d'imposta ed entro la scadenza
  (31 ottobre; 30 novembre fino ai redditi 2022); entro 90 giorni = tardiva ma valida, oltre = omessa
- le prime 6 cifre del protocollo sono la data di ricezione (AAMMGG): devono coincidere con la data indicata
"""

from __future__ import annotations

import re
from datetime import date, timedelta

from .report import Esito, Report

GRUPPO = "Presentazione telematica"
TIPO_RICEVUTA = "Ricevuta telematica Modello Redditi"
_DATA = r"(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{4})"

SEGNI_RICEVUTA = re.compile(r"avvenut[oa]\s+(?:ricevimento|presentazione|trasmissione)|ricevuta\s+(?:di\s+)?"
                            r"(?:presentazione|trasmissione|telematica)|comunicazione\s+di\s+avvenut|"
                            r"documento\s+(?:è\s+stato\s+)?(?:acquisito|ricevuto)|esito\s+(?:dell[ao']\s*)?"
                            r"(?:elaborazione|trasmissione)", re.IGNORECASE)


def _data(m: re.Match | None) -> date | None:
    if not m:
        return None
    try:
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    except ValueError:
        return None


def leggi(testo: str) -> dict:
    t = re.sub(r"[ \t]+", " ", testo)
    d: dict = {}
    m = re.search(r"protocollo(?:\s+telematico)?(?:\s+(?:n\.?|numero|n°))?\s*[:\-]?\s*(\d{17})\s*[-–/]?\s*(\d{6})",
                  t, re.IGNORECASE) or re.search(r"\b(\d{17})\s*[-–]\s*(\d{6})\b", t)
    if m:
        d["protocollo_telematico"] = f"{m.group(1)}-{m.group(2)}"
        try:
            p = m.group(1)
            d["data_protocollo"] = date(2000 + int(p[:2]), int(p[2:4]), int(p[4:6]))
        except ValueError:
            pass
    d["data_presentazione"] = _data(re.search(
        r"(?:data\s+(?:di\s+)?(?:presentazione|trasmissione|ricezione|invio)|presentat[ao]\s+(?:in\s+data|il)|"
        r"trasmess[ao]\s+(?:in\s+data|il)|ricevut[ao]\s+(?:in\s+data|il)|pervenut[ao]\s+(?:in\s+data|il))"
        r"\s*[:\-]?\s*(?:il\s+)?" + _DATA, t, re.IGNORECASE))
    d["data_impegno"] = _data(re.search(r"data\s+(?:dell['’]\s*)?impegno\s*[:\-]?\s*" + _DATA, t, re.IGNORECASE))
    m = re.search(r"(?:codice\s+fiscale\s+(?:dell['’]\s*)?intermediario|intermediario)\D{0,40}?"
                  r"\b([A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z]|\d{11})\b", t, re.IGNORECASE)
    if m:
        d["intermediario"] = m.group(1)
    d["impegno_trasmissione"] = bool(re.search(r"impegno\s+(?:alla|a)\s+(?:presentazione|trasmissione|"
                                               r"presentare)", t, re.IGNORECASE)) or None
    d["ricevuta_presente"] = bool(SEGNI_RICEVUTA.search(t)) or None
    if re.search(r"\bscartat[ao]\b|esito\s*[:\-]?\s*(?:negativo|scarto)|non\s+(?:è\s+stat[ao]\s+)?accolt", t,
                 re.IGNORECASE):
        d["esito_trasmissione"] = "Scartata"
    elif d["ricevuta_presente"] or d.get("protocollo_telematico"):
        d["esito_trasmissione"] = "Accolta"
    if re.search(r"\bintegrativa\b", t, re.IGNORECASE):
        d["tipo_dichiarazione"] = "Integrativa"
    elif re.search(r"\bcorrettiva\b", t, re.IGNORECASE):
        d["tipo_dichiarazione"] = "Correttiva nei termini"
    return {k: v for k, v in d.items() if v is not None}


def scadenza(periodo_imposta: int) -> date:
    """Termine per la presentazione telematica del Modello Redditi PF."""
    return date(periodo_imposta + 1, 11, 30) if periodo_imposta <= 2022 else date(periodo_imposta + 1, 10, 31)


def e_ricevuta(testo: str) -> bool:
    """Solo la ricevuta (senza i quadri della dichiarazione)."""
    if not SEGNI_RICEVUTA.search(testo):
        return False
    quadri = re.findall(r"(?m)^\s*(?:RN|RE|RG|RF|LM|RB|RC|RP|RX)\d{1,2}\b", testo)
    return len(quadri) < 3


def controlla(r: Report, testo: str, periodo_imposta: int | None) -> None:
    d = r.dati
    info = leggi(testo)
    for k in ("protocollo_telematico", "data_presentazione", "intermediario", "data_impegno", "esito_trasmissione",
              "tipo_dichiarazione"):
        d[k] = info.get(k)

    if info.get("esito_trasmissione") == "Scartata":
        r.aggiungi("Esito della trasmissione", Esito.ERRORE,
                   "Ricevuta di SCARTO: la dichiarazione non risulta presentata (va ritrasmessa entro 5 giorni dallo "
                   "scarto)", GRUPPO)
    protocollo = info.get("protocollo_telematico")
    if protocollo:
        r.aggiungi("Protocollo telematico", Esito.OK, f"{protocollo}: dichiarazione trasmessa all'Agenzia delle "
                   "Entrate", GRUPPO)
    elif info.get("ricevuta_presente"):
        r.aggiungi("Protocollo telematico", Esito.ATTENZIONE,
                   "Ricevuta presente ma protocollo non leggibile: verificarlo sul documento", GRUPPO)
    else:
        r.aggiungi("Protocollo telematico", Esito.ATTENZIONE,
                   "Nessun protocollo né ricevuta di presentazione: potrebbe essere una bozza mai inviata. Chiedere "
                   "la ricevuta telematica dell'Agenzia delle Entrate (o la dichiarazione con il protocollo)", GRUPPO)

    presentata = info.get("data_presentazione") or info.get("data_protocollo")
    if info.get("data_presentazione") and info.get("data_protocollo") and \
            abs((info["data_presentazione"] - info["data_protocollo"]).days) > 1:
        r.aggiungi("Data nel protocollo", Esito.ATTENZIONE,
                   f"Il protocollo indica il {info['data_protocollo']:%d/%m/%Y}, il documento il "
                   f"{info['data_presentazione']:%d/%m/%Y}: verificare con il cassetto fiscale", GRUPPO)
    if presentata and periodo_imposta:
        termine = scadenza(periodo_imposta)
        if presentata.year <= periodo_imposta:
            r.aggiungi("Data di presentazione", Esito.ERRORE,
                       f"{presentata:%d/%m/%Y}: precedente alla fine dell'anno d'imposta {periodo_imposta}", GRUPPO)
        elif presentata <= termine:
            r.aggiungi("Data di presentazione", Esito.OK,
                       f"{presentata:%d/%m/%Y}, entro la scadenza del {termine:%d/%m/%Y}", GRUPPO)
        elif presentata <= termine + timedelta(days=90):
            r.aggiungi("Data di presentazione", Esito.ATTENZIONE,
                       f"{presentata:%d/%m/%Y}: TARDIVA (scadenza {termine:%d/%m/%Y}), valida entro 90 giorni con "
                       "sanzione ridotta", GRUPPO)
        else:
            r.aggiungi("Data di presentazione", Esito.ERRORE,
                       f"{presentata:%d/%m/%Y}: oltre 90 giorni dalla scadenza del {termine:%d/%m/%Y}, la "
                       "dichiarazione si considera OMESSA", GRUPPO)
    elif presentata:
        r.aggiungi("Data di presentazione", Esito.INFO, f"{presentata:%d/%m/%Y}", GRUPPO)

    if info.get("intermediario"):
        r.aggiungi("Intermediario", Esito.INFO,
                   f"Trasmessa da intermediario (CAF/commercialista) {info['intermediario']}"
                   + (f", impegno del {info['data_impegno']:%d/%m/%Y}" if info.get("data_impegno") else ""), GRUPPO)
    if info.get("tipo_dichiarazione"):
        r.aggiungi("Tipo di dichiarazione", Esito.ATTENZIONE,
                   f"{info['tipo_dichiarazione']}: sostituisce una dichiarazione già presentata, chiedere anche "
                   "quella originaria", GRUPPO)


def analizza_ricevuta(testo: str) -> Report:
    """Ricevuta dell'Agenzia delle Entrate presentata da sola (senza la dichiarazione)."""
    from .layout import cf_corretto_ocr
    from .validators import decodifica_codice_fiscale, trova_codici_fiscali

    r = Report(TIPO_RICEVUTA)
    d = r.dati
    m = re.search(r"periodo\s+d['’]\s*imposta\s*(\d{4})", testo, re.IGNORECASE)
    m2 = re.search(r"redditi\s*(?:pf\s*)?(\d{4})", testo, re.IGNORECASE)
    d["periodo_imposta"] = int(m.group(1)) if m else (int(m2.group(1)) - 1 if m2 else None)
    codici = trova_codici_fiscali(testo)
    cf, _ = cf_corretto_ocr(codici[0] if codici else None)
    d["codice_fiscale_contribuente"] = cf
    if cf:
        valido = decodifica_codice_fiscale(cf).valido
        r.aggiungi("Codice fiscale contribuente", Esito.OK if valido else Esito.ERRORE,
                   f"{cf} {'valido' if valido else 'NON valido'}")
    else:
        r.aggiungi("Codice fiscale contribuente", Esito.ATTENZIONE, "Codice fiscale non trovato")
    controlla(r, testo, d["periodo_imposta"])
    return r
