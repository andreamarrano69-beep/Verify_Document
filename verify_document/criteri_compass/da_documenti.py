"""Dati della pratica ricavati dai documenti già analizzati del cliente.

Dalla busta paga più recente: sesso e data di nascita (dal codice fiscale), data di assunzione, contratto,
part-time, netto per il calcolo del quinto e trattenute in corso (cessione, delega, pignoramento).
Dal cedolino della pensione / ObisM: data di nascita, pensione netta, quota ancora cedibile, cessione in corso.
Dall'estratto contributivo: anzianità contributiva.

Restituisce un dizionario {campo della finestra: valore come testo}: l'operatore può correggere ogni campo.
"""

from __future__ import annotations

import re
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from ..report import Report

# settore del programma -> settore dei criteri Compass
SETTORE_COMPASS = {
    "Privato": "Dipendente privato",
    "Statale": "Statale / pubblico",
    "Pensionato": "Pensionato",
}


def _testo_data(d) -> str:
    if isinstance(d, date):
        return d.strftime("%d/%m/%Y")
    if isinstance(d, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", d):
        a, m, g = d.split("-")
        return f"{g}/{m}/{a}"
    return ""


def _importo(v) -> str:
    if v in (None, "", 0):
        return ""
    try:
        return f"{Decimal(str(v)):.2f}".replace(".", ",")
    except Exception:
        return ""


def _data_riferimento(r: Report) -> date:
    """Per scegliere il documento più recente (periodo della busta / anno)."""
    from ..archivio import data_documento

    return data_documento(r) or date.min


def _contratto(tipo: str | None) -> str:
    t = (tipo or "").lower()
    if "apprendist" in t:
        return "Apprendistato"
    if "somministr" in t or "interinal" in t:
        return "Somministrazione-interinale"
    if "determinato" in t and "indeterminato" not in t:
        return "Determinato"
    return "Indeterminato"


def _part_time(orario: str | None) -> tuple[str, str]:
    o = (orario or "").lower()
    if "part" not in o:
        return "No", ""
    perc = re.search(r"(\d{1,3})\s*%", o)
    for nome in ("orizzontale", "verticale", "misto"):
        if nome in o:
            return nome.capitalize(), perc.group(1) if perc else ""
    return "Orizzontale", perc.group(1) if perc else ""


def da_reports(reports: list[Report], settore_programma: str | None = None) -> tuple[dict, list[str]]:
    """(campi, note): campi da precompilare e spiegazione di dove viene ogni dato."""
    campi: dict[str, str] = {}
    note: list[str] = []
    validi = [r for r in reports if r is not None]

    buste = sorted((r for r in validi if r.tipo_documento == "Busta paga"), key=_data_riferimento)
    # il cedolino (che riporta le cessioni in corso) vale più del certificato ObisM
    pensioni = sorted((r for r in validi if r.tipo_documento.startswith(("Cedolino pensione", "Certificato di pensione"))),
                      key=lambda r: (r.tipo_documento.startswith("Cedolino"), _data_riferimento(r)))
    estratti = sorted((r for r in validi if r.tipo_documento == "Estratto contributivo"), key=_data_riferimento)

    if settore_programma in SETTORE_COMPASS:
        campi["_settore"] = SETTORE_COMPASS[settore_programma]
    elif pensioni and not buste:
        campi["_settore"] = "Pensionato"
    elif buste:
        campi["_settore"] = ("Statale / pubblico" if buste[-1].dati.get("datore_di_lavoro") == "Pubblico"
                             else "Dipendente privato")

    if buste:
        d = buste[-1].dati
        periodo = d.get("periodo") or "busta paga"
        if d.get("sesso") in ("M", "F"):
            campi["sesso"] = d["sesso"]
        campi["nascita"] = _testo_data(d.get("data_nascita_da_cf"))
        campi["assunzione"] = _testo_data(d.get("data_assunzione"))
        campi["contratto"] = _contratto(d.get("tipo_contratto"))
        campi["part_time"], campi["part_time_perc"] = _part_time(d.get("orario"))
        # netto per il quinto: retribuzione al netto di contributi e imposte, prima di cessioni e deleghe
        campi["netto"] = _importo(d.get("base_netta_quinto") or d.get("netto"))
        campi["rata_pign"] = _importo(d.get("pignoramento"))
        # cessione in corso: per una nuova CQS è la cessione da rinnovare/estinguere; per una delega è la CQS in corso
        campi["_cqs_in_corso"] = _importo(d.get("cessione_quinto"))
        campi["rata_delega"] = _importo(d.get("delegazione_pagamento"))
        note.append(f"Busta paga {periodo}: nascita, assunzione, contratto, netto per il quinto "
                    f"({_importo(d.get('base_netta_quinto') or d.get('netto')) or 'non letto'} €) e trattenute in corso.")
        if d.get("cessione_quinto"):
            note.append(f"In busta c'è già una cessione del quinto ({_importo(d.get('cessione_quinto'))} €): per una "
                        "nuova CQS va estinta/rinnovata; per una delega è la CQS in corso.")

    if pensioni:
        d = pensioni[-1].dati
        campi["nascita"] = campi.get("nascita") or _testo_data(d.get("data_nascita_da_cf"))
        campi["pensione"] = _importo(d.get("base_netta_quinto") or d.get("importo_netto"))
        campi["quota_cedibile"] = _importo(d.get("cessione_disponibile") or d.get("quinto_cedibile"))
        if d.get("cessione_quinto"):
            note.append(f"Sul cedolino c'è già una cessione ({_importo(d.get('cessione_quinto'))} €): la quota "
                        "cedibile indicata è quella ancora libera.")
        note.append(f"{pensioni[-1].tipo_documento} {d.get('periodo') or ''}: data di nascita, pensione netta e "
                    "quota ancora cedibile "
                    f"(stima dal cedolino: va confermata con la Comunicazione di quota cedibile dell'Ente).")

    if estratti:
        d = estratti[-1].dati
        settimane = d.get("anzianita_settimane")
        if settimane:
            # stessa conversione dell'estratto contributivo (arrotondata al mese)
            mesi = int((Decimal(str(settimane)) * 12 / 52).quantize(Decimal("1"), ROUND_HALF_UP))
            campi["anz_anni"], campi["anz_mesi"] = str(mesi // 12), str(mesi % 12)
            note.append(f"Estratto contributivo: anzianità {d.get('anzianita_contributiva') or ''} "
                        f"({settimane} settimane).")

    return {k: v for k, v in campi.items() if v not in (None, "")}, note
