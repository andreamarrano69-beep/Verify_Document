"""Controlli incrociati con l'estratto contributivo INPS e tra Modello Redditi e ricevuta telematica.

L'estratto contributivo è la fonte più difficile da falsificare (arriva dall'INPS): se una busta paga o una CU
dicono che il cliente lavora per un'azienda, i contributi di quei mesi devono esserci.

- Busta paga ↔ estratto: assunzione e mesi delle buste coperti da contributi da lavoro dipendente; datore
- CU ↔ estratto: imponibile previdenziale della CU = retribuzione dell'anno nell'estratto; giorni ↔ settimane;
  sostituto d'imposta ↔ datore di lavoro. CU senza contributi in quell'anno: forte segnale di CU non vera
- Modello Redditi ↔ estratto: reddito da lavoro autonomo/impresa con contributi da autonomo nell'anno
- Modello Redditi ↔ ricevuta: stesso anno, stesso protocollo telematico
- Pensione ↔ estratto: contributi alla decorrenza rispetto ai requisiti; contributi dopo la decorrenza

I mesi più recenti di una data possono mancare nell'estratto (l'INPS li registra con qualche mese di ritardo):
si controllano solo i periodi precedenti alla data di aggiornamento dell'estratto.
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from decimal import Decimal

from .report import Esito, Report
from .validators import formatta_euro

AUTONOMO = re.compile(r"gestione\s+separata|artigian|commerciant|autonom|professionist|coltivator|parasubordinat",
                      re.IGNORECASE)
NON_LAVORO = re.compile(r"disoccupaz|naspi|mobilit|malattia|maternit|figurativ|riscatt|militare|cassa\s+integr",
                        re.IGNORECASE)
_PAROLE_VUOTE = {"SRL", "SPA", "SNC", "SAS", "SRLS", "SOC", "COOP", "SOCIETA", "SOCIETÀ", "DI", "DEL", "DELLA", "E",
                 "IL", "LA", "LE", "GLI", "DEI", "DEGLI", "&", "C", "ARL", "SCARL", "ONLUS"}


def _parole(nome: str | None) -> set[str]:
    return {p for p in re.split(r"[^A-Z0-9À-Ü]+", (nome or "").upper()) if len(p) >= 3 and p not in _PAROLE_VUOTE}


def stesso_nome(a: str | None, b: str | None) -> bool | None:
    """True/False se i nomi di due aziende coincidono (almeno una parola significativa); None se manca un nome."""
    pa, pb = _parole(a), _parole(b)
    if not pa or not pb:
        return None
    return bool(pa & pb)


def _aggiornato_al(e: Report) -> date | None:
    d = e.dati
    return d.get("data_estratto") or d.get("ultimo_contributo")


def _periodi(e: Report) -> list[dict]:
    return e.extra.get("periodi", [])


def _da_lavoro_dipendente(p: dict) -> bool:
    return not AUTONOMO.search(p["tipo"] or "") and not NON_LAVORO.search(p["tipo"] or "")


def _quota_anno(p: dict, anno: int) -> Decimal:
    """Parte del periodo che cade nell'anno (in proporzione ai giorni)."""
    inizio, fine = max(p["dal"], date(anno, 1, 1)), min(p["al"], date(anno, 12, 31))
    if fine < inizio:
        return Decimal(0)
    return Decimal((fine - inizio).days + 1) / Decimal((p["al"] - p["dal"]).days + 1)


def _nell_anno(periodi: list[dict], anno: int, filtro) -> tuple[Decimal, Decimal | None, list[str]]:
    """(settimane, retribuzione o None, datori) dei periodi dell'anno che rispettano il filtro."""
    settimane, retribuzione, datori, con_retr = Decimal(0), Decimal(0), [], False
    for p in periodi:
        q = _quota_anno(p, anno)
        if q and filtro(p):
            settimane += p["settimane"] * q
            if p["retribuzione"] is not None:
                retribuzione += p["retribuzione"] * q
                con_retr = True
            if p["datore"]:
                datori.append(p["datore"])
    return settimane, (retribuzione.quantize(Decimal("0.01")) if con_retr else None), datori


def _coperto(periodi: list[dict], giorno: date, filtro=_da_lavoro_dipendente) -> dict | None:
    return next((p for p in periodi if p["dal"] <= giorno <= p["al"] and filtro(p)), None)


# --- Busta paga ↔ estratto ---------------------------------------------------------------------------------

def buste_vs_estratto(r: Report, buste: list, estratti: list, gruppo: str) -> None:
    e = max(estratti, key=lambda x: _aggiornato_al(x.report) or date.min).report
    aggiornato = _aggiornato_al(e)
    periodi = _periodi(e)
    if not periodi or aggiornato is None:
        return
    # assunzione
    for b in buste:
        assunzione = b.report.dati.get("data_assunzione")
        if not assunzione:
            continue
        if assunzione > aggiornato:
            r.aggiungi("Assunzione ↔ estratto", Esito.INFO,
                       f"Assunzione del {assunzione:%d/%m/%Y} successiva all'aggiornamento dell'estratto "
                       f"({aggiornato:%d/%m/%Y}): chiedere un estratto più recente", gruppo=gruppo)
        elif _coperto(periodi, assunzione) or _coperto(periodi, assunzione + timedelta(days=31)):
            r.aggiungi("Assunzione ↔ estratto", Esito.OK,
                       f"Contributi da lavoro dipendente dal {assunzione:%d/%m/%Y} presenti nell'estratto", gruppo=gruppo)
        else:
            r.aggiungi("Assunzione ↔ estratto", Esito.ERRORE,
                       f"La busta indica l'assunzione il {assunzione:%d/%m/%Y}, ma nell'estratto INPS non ci sono "
                       "contributi da lavoro dipendente in quel periodo", gruppo=gruppo)
        break
    # mesi delle buste
    scoperti, recenti, controllati = [], [], 0
    datori_mesi = []
    for b in buste:
        am = b.anno_mese
        if not am:
            continue
        meta_mese = date(am[0], am[1], 15)
        if meta_mese > aggiornato:
            recenti.append(b.report.dati["periodo"])
            continue
        controllati += 1
        p = _coperto(periodi, meta_mese)
        if p is None:
            scoperti.append(b.report.dati["periodo"])
        elif p["datore"]:
            datori_mesi.append((b.report.dati.get("azienda"), p["datore"], b.report.dati["periodo"]))
    if scoperti:
        r.aggiungi("Buste paga ↔ estratto", Esito.ERRORE,
                   f"Nessun contributo da lavoro dipendente nell'estratto per: {', '.join(scoperti)} — busta paga "
                   "non corrispondente a un rapporto di lavoro registrato all'INPS (o estratto incompleto)", gruppo=gruppo)
    elif controllati:
        r.aggiungi("Buste paga ↔ estratto", Esito.OK,
                   "Contributi presenti nell'estratto per " + ("il mese della busta paga" if controllati == 1 else
                                                                 f"tutti i {controllati} mesi delle buste paga"),
                   gruppo=gruppo)
    if recenti:
        r.aggiungi("Mesi recenti", Esito.INFO,
                   f"{', '.join(recenti)}: successivi all'aggiornamento dell'estratto ({aggiornato:%d/%m/%Y}), "
                   "non ancora verificabili (l'INPS registra i contributi con qualche mese di ritardo)", gruppo=gruppo)
    diversi = [(a, d, per) for a, d, per in datori_mesi if stesso_nome(a, d) is False]
    if diversi:
        a, d, per = diversi[0]
        r.aggiungi("Datore di lavoro ↔ estratto", Esito.ATTENZIONE,
                   f"{per}: busta paga di «{a}», nell'estratto «{d}» — verificare (cambio di ragione sociale?)",
                   gruppo=gruppo)
    elif any(stesso_nome(a, d) for a, d, _ in datori_mesi):
        r.aggiungi("Datore di lavoro ↔ estratto", Esito.OK, "Stesso datore di lavoro su busta paga ed estratto",
                   gruppo=gruppo)


# --- CU ↔ estratto -------------------------------------------------------------------------------------------

def cu_vs_estratto(r: Report, certificazioni: list, estratti: list, gruppo: str) -> None:
    e = max(estratti, key=lambda x: _aggiornato_al(x.report) or date.min).report
    aggiornato, periodi = _aggiornato_al(e), _periodi(e)
    if not periodi or aggiornato is None:
        return
    for c in certificazioni:
        d = c.report.dati
        anno = d.get("periodo_imposta")
        if not anno or not str(d.get("tipo_reddito") or "").startswith("Lavoro dipendente"):
            continue
        nome = f"CU {anno} ↔ estratto"
        if aggiornato < date(anno, 12, 31):
            r.aggiungi(nome, Esito.INFO, f"Estratto aggiornato al {aggiornato:%d/%m/%Y}: anno {anno} non completo",
                       gruppo=gruppo)
            continue
        settimane, retribuzione, datori = _nell_anno(periodi, anno, _da_lavoro_dipendente)
        if settimane < 1:
            r.aggiungi(nome, Esito.ERRORE,
                       f"La CU certifica lavoro dipendente nel {anno}, ma l'estratto INPS non ha contributi da lavoro "
                       "dipendente in quell'anno: CU da verificare con attenzione", gruppo=gruppo)
            continue
        dettagli, esito = [], Esito.OK
        imp = d.get("imponibile_previdenziale")
        if imp and retribuzione:
            scarto = abs(imp - retribuzione) / imp
            testo = f"imponibile previdenziale CU {formatta_euro(imp)}, retribuzione nell'estratto {formatta_euro(retribuzione)}"
            if scarto <= Decimal("0.02"):
                dettagli.append(testo + " (uguali)")
            elif scarto <= Decimal("0.10"):
                esito = Esito.ATTENZIONE
                dettagli.append(testo + f" (differenza {scarto * 100:.0f}%)")
            else:
                esito = Esito.ERRORE
                dettagli.append(testo + f" — differenza {scarto * 100:.0f}%: importi della CU non coerenti con l'INPS")
        giorni = d.get("giorni_lavoro")
        if giorni:
            attese = Decimal(giorni) * 52 / 365
            if settimane > attese + 4:
                esito = max(esito, Esito.ATTENZIONE, key=_gravita)
                dettagli.append(f"{settimane:.0f} settimane nell'estratto ma solo {giorni} giorni nella CU")
            elif settimane < attese - 4:
                dettagli.append(f"{settimane:.0f} settimane nell'estratto per {giorni} giorni nella CU (part-time o "
                                "retribuzione sotto il minimale INPS?)")
            else:
                dettagli.append(f"{giorni} giorni CU ≈ {settimane:.0f} settimane")
        sostituto = d.get("denominazione_sostituto") or d.get("sostituto_imposta")
        if sostituto and datori and not sostituto.isdigit():
            if any(stesso_nome(sostituto, x) for x in datori):
                dettagli.append("stesso datore di lavoro")
            elif all(stesso_nome(sostituto, x) is False for x in datori):
                esito = max(esito, Esito.ATTENZIONE, key=_gravita)
                dettagli.append(f"sostituto d'imposta «{sostituto}» diverso dal datore nell'estratto «{datori[0]}»")
        r.aggiungi(nome, esito, "; ".join(dettagli) or f"{settimane:.0f} settimane di contributi nel {anno}",
                   gruppo=gruppo)


def _gravita(e: Esito) -> int:
    return {Esito.INFO: 0, Esito.OK: 1, Esito.ATTENZIONE: 2, Esito.ERRORE: 3}[e]


# --- Modello Redditi ↔ estratto e ricevuta ---------------------------------------------------------------------

def redditi_vs_estratto(r: Report, redditi: list, estratti: list, gruppo: str) -> None:
    e = max(estratti, key=lambda x: _aggiornato_al(x.report) or date.min).report
    aggiornato, periodi = _aggiornato_al(e), _periodi(e)
    if not periodi or aggiornato is None:
        return
    for m in redditi:
        d = m.report.dati
        anno, regime = d.get("periodo_imposta"), d.get("regime_fiscale") or ""
        if not anno or not regime.startswith(("Forfettario", "Regime di vantaggio", "Impresa", "Lavoro autonomo")):
            continue
        if aggiornato < date(anno, 12, 31):
            continue
        settimane, _, _ = _nell_anno(periodi, anno, lambda p: bool(AUTONOMO.search(p["tipo"] or "")))
        if settimane >= 1:
            r.aggiungi(f"Redditi {anno} ↔ estratto", Esito.OK,
                       f"Reddito da {regime.split(' (')[0].lower()} e contributi da autonomo nell'estratto "
                       f"({settimane:.0f} settimane)", gruppo=gruppo)
        else:
            r.aggiungi(f"Redditi {anno} ↔ estratto", Esito.ATTENZIONE,
                       f"Il Modello Redditi {anno} dichiara reddito da {regime.split(' (')[0].lower()}, ma l'estratto "
                       "INPS non ha contributi da autonomo (gestione separata, artigiani, commercianti) in quell'anno: "
                       "contributi non versati o iscrizione a una cassa professionale (chiedere l'estratto della cassa)",
                       gruppo=gruppo)


def redditi_vs_ricevute(r: Report, redditi: list, ricevute: list, gruppo: str) -> None:
    for ric in ricevute:
        dr = ric.report.dati
        anno = dr.get("periodo_imposta")
        modello = next((m for m in redditi if m.report.dati.get("periodo_imposta") == anno), None)
        nome = f"Modello Redditi {anno or ''} ↔ ricevuta".replace("  ", " ")
        if modello is None:
            r.aggiungi(nome, Esito.INFO, f"Ricevuta dell'anno {anno or 'non letto'} senza il relativo Modello Redditi",
                       gruppo=gruppo)
            continue
        pm, pr = modello.report.dati.get("protocollo_telematico"), dr.get("protocollo_telematico")
        if dr.get("esito_trasmissione") == "Scartata":
            r.aggiungi(nome, Esito.ERRORE, "La ricevuta è uno SCARTO: la dichiarazione non risulta presentata",
                       gruppo=gruppo)
        elif pm and pr and pm != pr:
            r.aggiungi(nome, Esito.ERRORE,
                       f"Protocollo diverso: modello {pm}, ricevuta {pr} — la ricevuta non è di questa dichiarazione "
                       "(o esiste una dichiarazione successiva)", gruppo=gruppo)
        elif pm and pr:
            r.aggiungi(nome, Esito.OK, f"Stesso protocollo telematico {pr}", gruppo=gruppo)
        else:
            r.aggiungi(nome, Esito.OK, f"Ricevuta di presentazione dell'anno {anno} presente", gruppo=gruppo)


# --- Pensione ↔ estratto ---------------------------------------------------------------------------------------

ANTICIPATA_MINIMA = Decimal(41 * 52)  # sotto i 41 anni circa: solo canali particolari (quota 100/103, usuranti, ...)


def pensioni_vs_estratto(r: Report, pensioni: list, estratti: list, gruppo: str) -> None:
    e = max(estratti, key=lambda x: _aggiornato_al(x.report) or date.min).report
    periodi = _periodi(e)
    p = next((x.report.dati for x in pensioni if x.report.dati.get("decorrenza_pensione")), None)
    if not periodi or p is None:
        return
    decorrenza = p["decorrenza_pensione"]
    prima = [x for x in periodi if x["dal"] < decorrenza]
    settimane = sum((x["settimane"] * min(Decimal(1), Decimal((decorrenza - x["dal"]).days) /
                                         Decimal((x["al"] - x["dal"]).days + 1)) for x in prima), Decimal(0))
    anni = settimane / 52
    eta = p.get("eta_al_pensionamento")
    dettaglio = f"Alla decorrenza ({decorrenza:%d/%m/%Y}) circa {anni:.0f} anni di contributi nell'estratto"
    esito = Esito.OK
    categoria = p.get("categoria") or ""
    if categoria.startswith("VO"):
        if eta is not None and eta < 67 and settimane < ANTICIPATA_MINIMA:
            esito = Esito.ATTENZIONE
            dettaglio += (f" e {eta} anni di età: meno dei requisiti ordinari della pensione anticipata — possibile "
                          "solo con canali particolari (quota 100/103, opzione donna, lavori usuranti, ...): verificare")
        elif eta is not None and eta >= 67 and settimane < 20 * 52:
            esito = Esito.ATTENZIONE
            dettaglio += " — meno dei 20 anni richiesti per la vecchiaia: verificare"
    dopo = [x for x in periodi if x["al"] > decorrenza + timedelta(days=31) and not NON_LAVORO.search(x["tipo"] or "")]
    if dopo:
        dettaglio += f"; contributi anche dopo la pensione ({dopo[-1]['tipo'] or 'lavoro'} fino al " \
                     f"{dopo[-1]['al']:%d/%m/%Y}): lavora ancora, reddito aggiuntivo da verificare"
    r.aggiungi("Pensione ↔ estratto", esito, dettaglio, gruppo=gruppo)
