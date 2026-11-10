"""Analisi dei documenti dei pensionati: cedolino della pensione (INPS o altri enti)
e certificato di pensione (Modello ObisM).

Estrae: pensionato (CF), ente, categoria e numero della pensione, mese/anno, importo lordo,
trattenute (IRPEF, addizionali, cessione del quinto, pignoramenti, ...), importo netto.

Controlli:
- codice fiscale valido ed età del pensionato
- netto = lordo − trattenute
- ritenuta IRPEF del mese non superiore all'IRPEF lorda massima (calcolata su 13 mensilità)
- cessione del quinto / prestiti / pignoramenti già presenti (rilevante per i finanziamenti)
- importo mensile netto e lordo annuo (13 mensilità)
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

from .busta_paga import _trova_periodo
from .layout import cf_corretto_ocr
from .report import Esito, Report, cerca_importo, cerca_testo
from .validators import trova_codici_fiscali, CF_REGEX, decodifica_codice_fiscale, formatta_euro

MENSILITA = 13  # le pensioni sono pagate in 13 rate (la tredicesima a dicembre)
GRUPPO_PENSIONE = "Pensione"

# Categorie di pensione INPS più comuni (sigla iniziale della categoria)
CATEGORIE = [
    (r"VO|VOART|VOCOM|VOBIS", "Vecchiaia o anticipata (ex anzianità)", "previdenziale"),
    (r"IO|IOART|IOCOM", "Invalidità (assegno ordinario di invalidità)", "previdenziale"),
    (r"INAB", "Inabilità", "previdenziale"),
    (r"SO|SOART|SOCOM", "Superstiti (reversibilità / indiretta)", "previdenziale"),
    (r"PS|AS", "Pensione / assegno sociale", "assistenziale"),
    (r"INVCIV|CIV|INV", "Invalidità civile", "assistenziale"),
]

ETICHETTE = {
    "importo_lordo": [r"importo\s+(?:mensile\s+)?lordo", r"totale\s+lordo", r"lordo\s+mensile",
                      r"pensione\s+lorda", r"\blordo\b"],
    "ritenute_irpef": [r"ritenut[ae]\s+irpef", r"(?m)^\s*irpef\b(?!\s+(?:lorda|netta))"],
    "addizionale_regionale": [r"addizionale\s+regionale"],
    "addizionale_comunale": [r"addizionale\s+comunale"],
    "altre_trattenute": [r"trattenute\s+sindacali", r"quota\s+sindacale", r"conguaglio\s+(?:a\s+)?debito"],
    "totale_trattenute": [r"totale\s+trattenute", r"totale\s+ritenute"],
    "importo_netto": [r"importo\s+(?:mensile\s+)?netto", r"netto\s+(?:da\s+)?(?:pagare|accreditare|in\s+pagamento)",
                      r"totale\s+netto", r"pensione\s+netta", r"\bnetto\b"],
}


def riconosci(testo: str) -> int:
    t = testo.lower()
    punti = 0
    for k, peso in [("cedolino della pensione", 4), ("cedolino pensione", 4), ("obis", 4),
                    ("certificato di pensione", 3), ("categoria pensione", 2), ("pensionato", 1),
                    ("numero pensione", 2), ("rata di pensione", 2), ("importo lordo", 1)]:
        if k in t:
            punti += peso
    return punti


def _categoria(testo: str) -> tuple[str | None, str | None, str | None]:
    m = re.search(r"categoria(?:\s+(?:di\s+)?pensione)?\s*[:\-]?\s*([A-Z]{2,7})\b", testo, re.IGNORECASE)
    if not m:
        return None, None, None
    sigla = m.group(1).upper()
    for pattern, descrizione, natura in CATEGORIE:
        if re.fullmatch(pattern, sigla):
            return sigla, descrizione, natura
    return sigla, None, None


def analizza(testo: str) -> Report:
    obis = bool(re.search(r"obis\s*-?\s*m|certificato\s+di\s+pensione", testo, re.IGNORECASE))
    r = Report("Certificato di pensione (ObisM)" if obis else "Cedolino pensione")
    d = r.dati

    d["periodo"] = None if obis else _trova_periodo(testo)
    m = re.search(r"anno\s*[:\-]?\s*(\d{4})", testo, re.IGNORECASE)
    if d["periodo"]:
        d["anno"] = int(d["periodo"].split()[1])
    elif m:
        d["anno"] = int(m.group(1))
    else:
        m = re.search(r"\b(20\d{2})\b", testo)
        d["anno"] = int(m.group(1)) if m else None

    ente = re.search(r"\b(INPS|INPDAP|ENPAM|INARCASSA|CASSA\s+FORENSE|ENASARCO|CIPAG|ENPAIA)\b", testo, re.IGNORECASE)
    d["ente"] = ente.group(1).upper() if ente else None
    sigla, descrizione, natura = _categoria(testo)
    d["categoria"] = sigla
    d["tipo_pensione"] = descrizione or (f"Categoria {sigla}" if sigla else "Pensione")
    d["numero_pensione"] = cerca_testo(
        testo, [r"(?:numero|n\.)\s*(?:della\s+)?(?:pensione|certificato)", r"certificato\s+n\.?"], r"([0-9]{5,12})")

    m = re.search(r"(?i:pensionato|titolare|beneficiario)\s*[:\-]\s*([A-Z][A-Z'À-Ü]+(?: [A-Z'À-Ü]+){1,3})(?=\s{2,}|\s*\n|\s+(?i:codice|c\.f))", testo)
    d["nominativo"] = m.group(1).strip() if m else None

    # --- Pensionato --------------------------------------------------------------------
    codici = trova_codici_fiscali(testo)
    cf, nota_cf = cf_corretto_ocr(codici[0] if codici else None, d.get("nominativo"))
    d["codice_fiscale_pensionato"] = cf
    if nota_cf:
        r.aggiungi("Codice fiscale corretto (OCR)", Esito.ATTENZIONE, nota_cf)
    if not cf:
        r.aggiungi("Codice fiscale pensionato", Esito.ERRORE, "Codice fiscale non trovato")
    else:
        info = decodifica_codice_fiscale(cf)
        if not info.valido:
            r.aggiungi("Codice fiscale pensionato", Esito.ERRORE, f"{cf} NON valido (carattere di controllo errato)")
        else:
            d["data_nascita_da_cf"] = info.data_nascita
            riferimento = d["anno"] or info.data_nascita.year
            eta = riferimento - info.data_nascita.year
            d["eta"] = eta
            dettaglio = f"{cf} valido — età circa {eta} anni"
            esito = Esito.OK
            if sigla and sigla.startswith("VO") and eta < 57:
                esito = Esito.ATTENZIONE
                dettaglio += " (età bassa per una pensione di vecchiaia/anzianità: verificare)"
            if sigla in ("PS", "AS") and eta < 65:
                esito = Esito.ATTENZIONE
                dettaglio += " (età inferiore a quella richiesta per l'assegno sociale)"
            r.aggiungi("Codice fiscale pensionato", esito, dettaglio)

    if descrizione:
        nota = " — prestazione assistenziale: non è reddito da contributi versati" if natura == "assistenziale" else ""
        r.aggiungi("Tipo di pensione", Esito.INFO if natura == "previdenziale" else Esito.ATTENZIONE,
                   f"{sigla}: {descrizione}{nota}", GRUPPO_PENSIONE)
    else:
        r.aggiungi("Tipo di pensione", Esito.INFO,
                   f"Categoria {sigla} non tra quelle note: verificarla sul certificato ObisM" if sigla
                   else "Categoria della pensione non indicata nel documento", GRUPPO_PENSIONE)

    _controlla_decorrenza(r, testo, sigla)

    # --- Importi -----------------------------------------------------------------------
    for chiave, etichette in ETICHETTE.items():
        d[chiave] = cerca_importo(testo, etichette, solo_riga=True)
    from .impegni import controlla_impegni, leggi_impegni

    d.update(leggi_impegni(testo))
    # rata con tredicesima: solo nei cedolini, se c'è una voce "tredicesima" con importo
    d["tredicesima"] = None if obis else (bool(re.search(
        r"(?im)^\s*(?:importo\s+)?(?:tredicesima|13\s*[ªa°^]\s*(?:mensilit[aà]|rata))\b[^\n]*\d+,\d{2}", testo)) or None)

    lordo, netto = d["importo_lordo"], d["importo_netto"]
    voci = ["ritenute_irpef", "addizionale_regionale", "addizionale_comunale", "cessione_quinto",
            "delegazione_pagamento", "pignoramento", "altre_trattenute"]
    trattenute = d["totale_trattenute"]
    if trattenute is None and any(d[v] is not None for v in voci):
        trattenute = sum((d[v] or 0 for v in voci), Decimal(0))
        d["totale_trattenute_calcolato"] = trattenute

    if lordo is None or netto is None:
        mancanti = [n for n, v in (("importo lordo", lordo), ("importo netto", netto)) if v is None]
        r.aggiungi("Quadratura netto", Esito.ATTENZIONE, "Non trovati: " + ", ".join(mancanti))
    elif netto > lordo:
        r.aggiungi("Quadratura netto", Esito.ERRORE,
                   f"Netto {formatta_euro(netto)} superiore al lordo {formatta_euro(lordo)}")
    elif trattenute is not None:
        atteso = lordo - trattenute
        diff = abs(atteso - netto)
        testo_calc = f"{formatta_euro(lordo)} − trattenute {formatta_euro(trattenute)} = {formatta_euro(atteso)}"
        if diff <= Decimal("0.01"):
            r.aggiungi("Quadratura netto", Esito.OK, testo_calc)
        elif diff <= Decimal("1"):
            r.aggiungi("Quadratura netto", Esito.ATTENZIONE, f"{testo_calc}, indicato {formatta_euro(netto)} (arrotondamento?)")
        else:
            r.aggiungi("Quadratura netto", Esito.ERRORE,
                       f"{testo_calc}, ma il netto indicato è {formatta_euro(netto)} (differenza {formatta_euro(diff)})")

    # IRPEF del mese: al massimo l'IRPEF lorda annua (13 mensilità) divisa per 12 rate
    if lordo and d["ritenute_irpef"] is not None and d["anno"]:
        from .cu import irpef_lorda

        annua = irpef_lorda(lordo * MENSILITA, d["anno"])
        if annua is not None:
            massimo = (annua / 12).quantize(Decimal("0.01"))
            if d["tredicesima"]:
                massimo *= 2  # nel mese della tredicesima la ritenuta raddoppia circa
            if d["ritenute_irpef"] > massimo + 1:
                r.aggiungi("Ritenuta IRPEF", Esito.ERRORE,
                           f"{formatta_euro(d['ritenute_irpef'])}: oltre il massimo possibile "
                           f"{formatta_euro(massimo)} per una pensione lorda di {formatta_euro(lordo)}")
            else:
                r.aggiungi("Ritenuta IRPEF", Esito.OK,
                           f"{formatta_euro(d['ritenute_irpef'])} entro il massimo {formatta_euro(massimo)} "
                           f"(IRPEF lorda su {MENSILITA} mensilità, senza detrazioni)")

    # Cessione del quinto, deleghe, pignoramenti e quinto cedibile
    if lordo and not d["tredicesima"]:
        base = lordo - sum((d[k] or 0) for k in ("ritenute_irpef", "addizionale_regionale", "addizionale_comunale"))
        controlla_impegni(r, base, "lordo − IRPEF − addizionali", pensione=True)
    else:
        controlla_impegni(r, None, "", pensione=True)

    # --- Importo mensile ----------------------------------------------------------------
    if lordo and d["tredicesima"]:
        r.aggiungi("Importo mensile", Esito.ATTENZIONE,
                   f"Cedolino con tredicesima (lordo del mese {formatta_euro(lordo)}): per l'importo mensile "
                   "ordinario usare il cedolino di un altro mese")
    elif lordo:
        d["reddito_annuo"] = lordo * MENSILITA
        d["reddito_mensile_lordo"] = lordo
        d["reddito_mensile_netto"] = netto
        r.aggiungi("Importo mensile", Esito.INFO,
                   f"Pensione lorda {formatta_euro(lordo)} al mese"
                   + (f", netta {formatta_euro(netto)}" if netto is not None else "")
                   + f" × {MENSILITA} mensilità = {formatta_euro(d['reddito_annuo'])} lordi l'anno")
    if not d["tredicesima"]:
        from .fattibilita import aggiungi_controlli

        aggiungi_controlli(r)
    return r


_NATURA = {"previdenziale": "pensione da contributi versati", "assistenziale": "prestazione assistenziale"}


def leggi_decorrenza(testo: str) -> date | None:
    """Data da cui decorre la pensione («Decorrenza: 01/05/2018», «in pagamento dal 05/2018»)."""
    m = re.search(r"(?:data\s+(?:di\s+)?)?decorrenza(?:\s+(?:della\s+)?pensione)?|in\s+pagamento\s+dal|"
                  r"pensionat[oa]\s+dal|liquidat[ao]\s+(?:con\s+decorrenza\s+)?dal", testo, re.IGNORECASE)
    if not m:
        return None
    coda = testo[m.end(): m.end() + 40]
    d = re.search(r"(?:(\d{1,2})[/.\-])?(\d{1,2})[/.\-](\d{4})", coda)
    if not d:
        return None
    try:
        return date(int(d.group(3)), int(d.group(2)), int(d.group(1) or 1))
    except ValueError:
        return None


def _controlla_decorrenza(r: Report, testo: str, sigla: str | None) -> None:
    """Da quando è in pensione: anni e mesi alla data del documento; età al pensionamento dal codice fiscale."""
    d = r.dati
    decorrenza = leggi_decorrenza(testo)
    d["decorrenza_pensione"] = decorrenza
    if decorrenza is None:
        r.aggiungi("Decorrenza della pensione", Esito.INFO,
                   "Data di decorrenza non indicata nel documento: si trova nel certificato ObisM o nella lettera di "
                   "liquidazione INPS", GRUPPO_PENSIONE)
        return
    from .busta_paga import _anno_mese_periodo

    am = _anno_mese_periodo(d.get("periodo")) or ((d["anno"], 12) if d.get("anno") else None)
    oggi = date.today()
    riferimento = date(*am, 1) if am else oggi
    riferimento = min(riferimento, oggi) if riferimento.year > oggi.year else riferimento
    mesi = (riferimento.year - decorrenza.year) * 12 + riferimento.month - decorrenza.month
    if mesi < 0:
        r.aggiungi("Decorrenza della pensione", Esito.ERRORE,
                   f"Dal {decorrenza:%d/%m/%Y}: successiva alla data del documento", GRUPPO_PENSIONE)
        return
    anni, resto = divmod(mesi, 12)
    durata = " e ".join(x for x in (f"{anni} ann{'o' if anni == 1 else 'i'}" if anni else "",
                                    f"{resto} mes{'e' if resto == 1 else 'i'}" if resto or not anni else "") if x)
    d["in_pensione_da"] = durata
    dettaglio = f"In pensione dal {decorrenza:%d/%m/%Y}: da {durata}"
    esito = Esito.INFO
    nascita = d.get("data_nascita_da_cf")
    if nascita:
        eta = decorrenza.year - nascita.year - ((decorrenza.month, decorrenza.day) < (nascita.month, nascita.day))
        d["eta_al_pensionamento"] = eta
        dettaglio += f" (pensionato/a a {eta} anni)"
        if sigla and sigla.startswith("VO") and eta < 55:
            esito = Esito.ATTENZIONE
            dettaglio += " — età molto bassa per una pensione di vecchiaia o anticipata: verificare"
    if mesi < 12:
        dettaglio += " — pensione recente: chiedere anche la lettera di liquidazione"
    r.aggiungi("Decorrenza della pensione", esito, dettaglio, GRUPPO_PENSIONE)

