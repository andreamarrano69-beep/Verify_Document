"""Analisi di una busta paga (cedolino / LUL).

Estrae: dati azienda (P.IVA), dati dipendente (codice fiscale, data assunzione),
periodo, totali e verifica la coerenza degli importi.

NB: i cedolini dei diversi software paghe (Zucchetti, TeamSystem, INAZ, ADP, ...)
hanno impaginazioni diverse. Le etichette cercate sono nelle liste qui sotto:
se un vostro modello usa diciture diverse basta aggiungerle.
"""

from __future__ import annotations

import re
from decimal import Decimal

from .report import Esito, Report, cerca_importo, cerca_testo
from .validators import (
    CF_REGEX,
    PIVA_REGEX,
    decodifica_codice_fiscale,
    formatta_euro,
    parse_data,
    valida_partita_iva,
)

# esclude le diciture dei progressivi annui ("Progressivo imponibile fiscale")
_NO_PROGR = r"(?<!progressivo\s)(?<!progr\.\s)"

ETICHETTE = {
    "totale_competenze": [
        r"totale\s+competenze", r"tot\.?\s*competenze", r"totale\s+lordo", r"lordo\s+mensile",
    ],
    "totale_trattenute": [r"totale\s+trattenute", r"tot\.?\s*trattenute"],
    "netto": [
        r"netto\s+in\s+busta", r"netto\s+del\s+mese", r"netto\s+a\s+pagare",
        r"netto\s+busta", r"netto\s+da\s+pagare", r"\bnetto\b",
    ],
    # senza \b iniziale: l'OCR a volte incolla etichette vicine ("PRECEDENTERROTONDAMENTO ATTUALE")
    "arrotondamento": [r"a?r?rotondamento\s+attuale", r"arr\.?\s*attuale"],
    "arrotondamento_precedente": [
        r"a?r?rotondamento\s+precedente", r"arr\.?\s*precedente", r"arrot\.?\s*mese\s+prec",
    ],
    "imponibile_previdenziale": [
        r"imponibile\s+previdenziale", r"imponibile\s+inps", r"imp\.?\s*prev\.?",
    ],
    "contributi_dipendente": [
        r"contributi\s+(?:inps\s+)?(?:a\s+carico\s+)?dipendente", r"contributo\s+ivs",
        r"contributi\s+inps", r"ritenute\s+previdenziali", r"totale\s+contributi",
    ],
    "imponibile_fiscale": [_NO_PROGR + r"imponibile\s+fiscale(?!\s+progr)",
                           _NO_PROGR + r"imponibile\s+irpef(?!\s+progr)", r"imp\.?\s*fisc\.?(?!\s*progr)"],
    "irpef_lorda": [r"irpef\s+lorda"],
    "addizionale_regionale": [r"addizionale\s+regionale(?!\s+progr)"],
    "addizionale_comunale": [r"addizionale\s+comunale(?!\s+progr)"],
    "irpef_netta": [r"irpef\s+netta(?!\s+progr)", _NO_PROGR + r"ritenute\s+irpef(?!\s+progr)"],
    # progressivi annui (da gennaio al mese corrente): usati nel confronto tra buste paga
    "progressivo_imponibile_fiscale": [
        r"progr(?:essivo|\.)?\s+imponibile\s+fiscale", r"imponibile\s+fiscale\s+progr(?:essivo|\.)?",
        r"imp\.?\s*fisc\.?\s*progr\.?",
    ],
    "progressivo_irpef": [
        r"progr(?:essivo|\.)?\s+(?:irpef|ritenute\s+irpef)", r"irpef\s+(?:netta\s+)?progr(?:essiva|\.)?",
    ],
}

ETICHETTE_ASSUNZIONE = [r"data\s+(?:di\s+)?assunzione", r"data\s+assunz\.?", r"assunto\s+il", r"assunzione"]
ETICHETTE_PIVA = [r"partita\s+i\.?v\.?a\.?", r"p\.?\s*i\.?v\.?a\.?", r"c\.?f\.?\s*/\s*p\.?\s*iva"]

MESI = [
    "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio",
    "agosto", "settembre", "ottobre", "novembre", "dicembre",
]

# Aliquote contributive INPS a carico del dipendente più comuni (settore privato)
ALIQUOTE_INPS = {
    Decimal("9.19"): "aliquota ordinaria IVS 9,19%",
    Decimal("9.49"): "9,19% + 1% aggiuntivo oltre la 1ª fascia pensionabile",
    Decimal("5.84"): "apprendisti 5,84%",
    Decimal("10.19"): "9,19% + 1% aggiuntivo (calcolo sull'intero imponibile)",
}

TOLLERANZA_CENT = Decimal("0.01")
TOLLERANZA_ARR = Decimal("1.00")


def riconosci(testo: str) -> int:
    t = testo.lower()
    punti = 0
    for k in ["busta paga", "cedolino", "netto in busta", "totale competenze",
              "totale trattenute", "imponibile previdenziale", "libro unico", "retribuzione"]:
        if k in t:
            punti += 1
    return punti


def _trova_periodo(testo: str) -> str | None:
    m = re.search(r"\b(" + "|".join(MESI) + r")\s+(\d{4})\b", testo, re.IGNORECASE)
    if m:
        return f"{m.group(1).capitalize()} {m.group(2)}"
    m = re.search(r"periodo(?:\s+di\s+paga|\s+retribuzione)?\s*[:\-]?\s*(\d{1,2})[/\-](\d{4})",
                  testo, re.IGNORECASE)
    if m:
        return f"{MESI[int(m.group(1)) - 1].capitalize()} {m.group(2)}"
    return None


def _anno_mese_periodo(periodo: str | None) -> tuple[int, int] | None:
    if not periodo:
        return None
    nome, anno = periodo.lower().split()
    return int(anno), MESI.index(nome) + 1


def _trova_piva(testo: str) -> str | None:
    """P.IVA dell'azienda: prima quella vicina all'etichetta, poi qualsiasi 11 cifre valide."""
    for etichetta in ETICHETTE_PIVA:
        for m in re.finditer(etichetta, testo, re.IGNORECASE):
            coda = testo[m.end(): m.end() + 60]
            c = re.search(r"(?:IT)?\s*(\d{11})(?!\d)", coda)
            if c:
                return c.group(1)
    for m in PIVA_REGEX.finditer(testo):
        if valida_partita_iva(m.group(0)):
            return m.group(0)
    return None


def analizza(testo: str) -> Report:
    r = Report("Busta paga")
    d = r.dati

    # --- Anagrafica ---------------------------------------------------------
    periodo = _trova_periodo(testo)
    d["periodo"] = periodo
    # cedolino di 13ª/14ª: cercato solo nell'intestazione (i "ratei 13ª" compaiono in ogni busta)
    intestazione = "\n".join(testo.strip().splitlines()[:6])
    d["mensilita_aggiuntiva"] = bool(re.search(
        r"(?<!ratei\s)(?<!rateo\s)\b(tredicesima|quattordicesima|1[34]\s*[ªa°^]\s*mensilit|mensilit[aà]\s+aggiuntiva)",
        intestazione, re.IGNORECASE)) or None

    piva = _trova_piva(testo)
    d["partita_iva_azienda"] = piva
    if not piva:
        r.aggiungi("P.IVA azienda", Esito.ERRORE, "Partita IVA dell'azienda non trovata")
    elif valida_partita_iva(piva):
        r.aggiungi("P.IVA azienda", Esito.OK, f"{piva} formalmente valida")
    else:
        r.aggiungi("P.IVA azienda", Esito.ERRORE, f"{piva} NON valida (cifra di controllo errata)")

    codici = list(dict.fromkeys(m.group(0) for m in CF_REGEX.finditer(testo.upper())))
    cf = codici[0] if codici else None
    d["codice_fiscale_dipendente"] = cf
    if not cf:
        r.aggiungi("Codice fiscale dipendente", Esito.ERRORE, "Codice fiscale non trovato")
    else:
        info = decodifica_codice_fiscale(cf)
        if info.valido:
            d["sesso"] = info.sesso
            d["data_nascita_da_cf"] = info.data_nascita
            r.aggiungi("Codice fiscale dipendente", Esito.OK,
                       f"{cf} valido (nato/a il {info.data_nascita:%d/%m/%Y}, sesso {info.sesso})")
        else:
            r.aggiungi("Codice fiscale dipendente", Esito.ERRORE,
                       f"{cf} NON valido (carattere di controllo errato)")

    data_ass_txt = cerca_testo(testo, ETICHETTE_ASSUNZIONE, r"(\d{1,2}[/.\-]\d{1,2}[/.\-]\d{2,4})")
    assunzione = parse_data(data_ass_txt) if data_ass_txt else None
    d["data_assunzione"] = assunzione
    if not assunzione:
        r.aggiungi("Data assunzione", Esito.ATTENZIONE, "Data di assunzione non trovata")
    else:
        dettaglio = f"Assunto/a il {assunzione:%d/%m/%Y}"
        esito = Esito.OK
        am = _anno_mese_periodo(periodo)
        if am:
            mesi = (am[0] - assunzione.year) * 12 + am[1] - assunzione.month
            if mesi < 0:
                esito = Esito.ERRORE
                dettaglio += " — successiva al periodo della busta paga!"
            else:
                anni, resto = divmod(mesi, 12)
                dettaglio += f" — anzianità circa {anni} anni e {resto} mesi"
                if mesi < 6:
                    esito = Esito.ATTENZIONE
                    dettaglio += " (assunzione recente: verificare periodo di prova)"
        if d.get("data_nascita_da_cf"):
            eta = (assunzione - d["data_nascita_da_cf"]).days // 365
            if eta < 16:
                esito = Esito.ERRORE
                dettaglio += f" — età all'assunzione {eta} anni: incoerente con il CF"
        r.aggiungi("Data assunzione", esito, dettaglio)

    m = re.search(r"(?i:dipendente|lavoratore|cognome\s+e\s+nome)\s*[:\-]\s*([A-Z][A-Z'À-Ü]+(?: [A-Z'À-Ü]+){1,3})(?=\s{2,}|\s*\n|\s+(?i:codice|c\.f))", testo)
    d["nominativo"] = m.group(1).strip() if m else None

    # --- Importi ------------------------------------------------------------
    for chiave, etichette in ETICHETTE.items():
        d[chiave] = cerca_importo(testo, etichette)

    comp, tratt, netto = d["totale_competenze"], d["totale_trattenute"], d["netto"]
    if None in (comp, tratt, netto):
        mancanti = [k for k in ("totale_competenze", "totale_trattenute", "netto") if d[k] is None]
        r.aggiungi("Quadratura netto", Esito.ATTENZIONE,
                   "Impossibile verificare, non trovati: " + ", ".join(mancanti))
    else:
        arr = (d["arrotondamento"] or 0) - (d["arrotondamento_precedente"] or 0)
        atteso = comp - tratt + arr
        diff = abs(netto - atteso)
        formula = f"{formatta_euro(comp)} − {formatta_euro(tratt)}"
        if arr:
            formula += f" ± arrotondamenti {formatta_euro(arr)}"
        if diff <= TOLLERANZA_CENT:
            r.aggiungi("Quadratura netto", Esito.OK, f"{formula} = {formatta_euro(netto)}")
        elif diff <= TOLLERANZA_ARR:
            r.aggiungi("Quadratura netto", Esito.ATTENZIONE,
                       f"{formula} = {formatta_euro(atteso)}, in busta {formatta_euro(netto)} "
                       f"(differenza {formatta_euro(diff)}, probabile arrotondamento)")
        else:
            r.aggiungi("Quadratura netto", Esito.ERRORE,
                       f"{formula} = {formatta_euro(atteso)}, ma il netto indicato è "
                       f"{formatta_euro(netto)} (differenza {formatta_euro(diff)})")
        if netto <= 0:
            r.aggiungi("Netto positivo", Esito.ERRORE, "Il netto in busta è nullo o negativo")

    imp_prev, contr = d["imponibile_previdenziale"], d["contributi_dipendente"]
    if imp_prev and contr:
        aliquota = (contr / imp_prev * 100).quantize(Decimal("0.01"))
        d["aliquota_contributiva_%"] = aliquota
        vicina = min(ALIQUOTE_INPS, key=lambda a: abs(a - aliquota))
        if abs(vicina - aliquota) <= Decimal("0.05"):
            r.aggiungi("Contributi INPS", Esito.OK,
                       f"{formatta_euro(contr)} su imponibile {formatta_euro(imp_prev)} "
                       f"= {str(aliquota).replace('.', ',')}% ({ALIQUOTE_INPS[vicina]})")
        else:
            r.aggiungi("Contributi INPS", Esito.ATTENZIONE,
                       f"Aliquota calcolata {aliquota}%: non corrisponde alle aliquote standard "
                       "(possibili agevolazioni, contributi FIS/fondi, o errore)")
        if comp and imp_prev > comp + TOLLERANZA_ARR:
            r.aggiungi("Imponibile previdenziale", Esito.ATTENZIONE,
                       "Imponibile previdenziale superiore al totale competenze")

    imp_fisc = d["imponibile_fiscale"]
    if imp_fisc and imp_prev and contr:
        atteso = imp_prev - contr
        diff = abs(imp_fisc - atteso)
        if diff <= TOLLERANZA_ARR:
            r.aggiungi("Imponibile fiscale", Esito.OK,
                       f"Imponibile previdenziale − contributi = {formatta_euro(imp_fisc)}")
        else:
            r.aggiungi("Imponibile fiscale", Esito.ATTENZIONE,
                       f"Atteso circa {formatta_euro(atteso)}, indicato {formatta_euro(imp_fisc)} "
                       "(possibili voci non soggette a contributi, fringe benefit, ecc.)")

    if d["irpef_netta"] is not None and d["irpef_lorda"] is not None:
        if d["irpef_netta"] > d["irpef_lorda"] + TOLLERANZA_CENT:
            r.aggiungi("IRPEF", Esito.ERRORE, "IRPEF netta maggiore dell'IRPEF lorda")
        else:
            detr = d["irpef_lorda"] - d["irpef_netta"]
            r.aggiungi("IRPEF", Esito.OK, f"Detrazioni applicate nel mese: {formatta_euro(detr)}")

    # --- Cessione del quinto, deleghe, pignoramenti ----------------------------
    from .impegni import controlla_impegni, leggi_impegni

    d.update(leggi_impegni(testo))
    contr_mese, irpef_mese = d["contributi_dipendente"], d["irpef_netta"]
    if comp and contr_mese is not None and irpef_mese is not None:
        base = comp - contr_mese - irpef_mese - (d["addizionale_regionale"] or 0) - (d["addizionale_comunale"] or 0)
        descr = "lordo − contributi − IRPEF − addizionali"
    elif netto:
        base = netto + sum((d[k] or 0) for k in ("cessione_quinto", "delegazione_pagamento", "pignoramento"))
        descr = "netto in busta + rate già trattenute (stima)"
    else:
        base, descr = None, ""
    if not d.get("mensilita_aggiuntiva"):
        controlla_impegni(r, base, descr)

    if netto:
        r.aggiungi("Netto mensile", Esito.INFO, f"Netto percepito: {formatta_euro(netto)}")
    return r
