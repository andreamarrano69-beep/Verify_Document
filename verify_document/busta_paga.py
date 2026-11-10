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

from .layout import cf_corretto_ocr
from .report import Esito, Report, cerca_importo, cerca_testo
from .validators import (
    trova_codici_fiscali,
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
        r"netto\s+busta", r"netto\s+da\s+pagare", r"netto\s+da\s+corrispondere", r"netto\s+corrisposto",
        r"netto\s+pagato", r"netto\s+erogato", r"netto\s+spettante", r"netto\s+(?:della\s+)?retribuzione",
        r"netto\s+mese", r"netto\s+(?:a\s+)?liquidare", r"totale\s+netto", r"importo\s+netto",
        r"\bnetto\b(?!\s+(?:progr|anno|annuo|imponibile|precedente))",
    ],
    # senza \b iniziale: l'OCR a volte incolla etichette vicine ("PRECEDENTERROTONDAMENTO ATTUALE")
    "arrotondamento": [r"a?r?rotondamento\s+attuale", r"arr\.?\s*attuale",
                       r"\barrotondamento\b(?!\s+(?:precedente|prec|mese))"],
    "arrotondamento_precedente": [
        r"a?r?rotondamento\s+precedente", r"arr\.?\s*precedente", r"arrot\.?\s*mese\s+prec",
        r"a?r?rotondamento\s+preced\w*",  # parola troncata dall'OCR ("PRECEDEN")
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
        r"\bimp\.\s*irpef\b",  # riquadro PROGRESSIVI (es. Zucchetti): "Imp. IRPEF"
    ],
    "progressivo_irpef": [
        r"progr(?:essivo|\.)?\s+(?:irpef|ritenute\s+irpef)", r"irpef\s+(?:netta\s+)?progr(?:essiva|\.)?",
        r"irpef\s+pagata",
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


# Parole tipiche della busta paga, con un peso: anche se l'OCR perde le intestazioni principali
# (es. scansioni poco nitide) restano voci come matricola INPS, contingenza, ratei, TFR, IVS.
TERMINI_BUSTA = [
    (r"busta\s+paga|cedolino\s+(?:paga|stipendio)|libro\s+unico|prospetto\s+paga", 3),
    (r"cedolino(?!\s+(?:della\s+|di\s+)?pension)", 1),
    (r"netto\s+(?:in\s+busta|del\s+mese|a\s+pagare|da\s+corrispondere|pagato)", 3),
    (r"totale\s+(?:competenze|trattenute)", 2),
    (r"imponibile\s+(?:previdenziale|fiscale|irpef|inps)", 2),
    (r"matricola\s+inps|posizione\s+inps|pat\s+inail", 2),
    (r"\binail\b", 1),
    (r"retribuzione", 1),
    (r"contingenza|paga\s+base|minimo\s+cont|superminimo|scatti", 2),
    (r"\bratei\b|\bferie\b|permessi|\brol\b|festivit", 1),
    (r"\btfr\b|t\.f\.r\.", 1),
    (r"\bivs\b|i\.v\.s\.", 1),
    (r"\blivello\b|qualifica|impiegat|\boperai", 1),
    (r"detrazion", 1),
    (r"data\s+(?:di\s+)?assunzione|\bassunt[oa]\b", 1),
]


def riconosci(testo: str) -> int:
    return sum(peso for pattern, peso in TERMINI_BUSTA if re.search(pattern, testo, re.IGNORECASE))


_FORMA_SOCIETARIA = r"(?:S\.?R\.?L\.?S?|S\.?P\.?A\.?|S\.?N\.?C\.?|S\.?A\.?S\.?|SOC\.?\s*COOP\w*|S\.?C\.?A\.?R\.?L\.?)"


def _trova_azienda(testo: str) -> str | None:
    """Ragione sociale del datore di lavoro (per il confronto con CU ed estratto contributivo)."""
    m = re.search(r"(?:azienda|ditta|datore\s+di\s+lavoro|ragione\s+sociale|amministrazione)\s*[:\-]\s*"
                  r"([A-Z0-9][A-Za-z0-9&'.\- ]{2,60}?)(?=\s{2,}|\n|,|$|\s+(?:via|viale|piazza|corso|p\.?\s?iva|"
                  r"partita|c\.?f))", testo, re.IGNORECASE)
    if m:
        return m.group(1).strip(" .-")
    intestazione = "\n".join(testo.splitlines()[:8])
    m = re.search(rf"\b([A-Z][A-Z0-9&'. ]{{1,50}}?\s{_FORMA_SOCIETARIA}(?:\s+DI\s+[A-Z][A-Z' ]{{2,40}}?)?)(?=\s{{2,}}|\n|$)",
                  intestazione, re.IGNORECASE)
    return re.sub(r"\s+", " ", m.group(1)).strip() if m else None


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
    from . import deduzioni

    periodo = _trova_periodo(testo) or deduzioni.periodo_su_righe_separate(testo)
    d["periodo"] = periodo
    # cedolino di 13ª/14ª: cercato solo nell'intestazione (i "ratei 13ª" compaiono in ogni busta)
    intestazione = "\n".join(testo.strip().splitlines()[:6])
    d["mensilita_aggiuntiva"] = bool(re.search(
        r"(?<!ratei\s)(?<!rateo\s)\b(tredicesima|quattordicesima|1[34]\s*[ªa°^]\s*mensilit|mensilit[aà]\s+aggiuntiva)",
        intestazione, re.IGNORECASE)) or None

    d["azienda"] = _trova_azienda(testo)
    piva = _trova_piva(testo)
    d["partita_iva_azienda"] = piva
    if not piva:
        r.aggiungi("P.IVA azienda", Esito.ERRORE, "Partita IVA dell'azienda non trovata")
    elif valida_partita_iva(piva):
        r.aggiungi("P.IVA azienda", Esito.OK, f"{piva} formalmente valida")
    else:
        r.aggiungi("P.IVA azienda", Esito.ERRORE, f"{piva} NON valida (cifra di controllo errata)")

    m = re.search(r"(?i:dipendente|lavoratore|cognome\s+e\s+nome)\s*[:\-]\s*([A-Z][A-Z'À-Ü]+(?: [A-Z'À-Ü]+){1,3})(?=\s{2,}|\s*\n|\s+(?i:codice|c\.f))", testo)
    d["nominativo"] = m.group(1).strip() if m else None
    if not d["nominativo"]:  # etichetta sopra e nome sotto (impaginazione a colonne)
        d["nominativo"] = cerca_testo(testo, [r"cognome\s+e\s+nome", r"nominativo"],
                                      r"([A-Z][A-Z'À-Ü]+(?: [A-Z'À-Ü]+){1,3})")

    codici = trova_codici_fiscali(testo)
    cf, nota_cf = cf_corretto_ocr(codici[0] if codici else None, d["nominativo"])
    d["codice_fiscale_dipendente"] = cf
    if not d["nominativo"] and cf:  # nome senza etichetta accanto: lo si riconosce dal codice fiscale
        from .validators import nominativo_da_cf

        d["nominativo"] = nominativo_da_cf(testo, cf)
    if nota_cf:
        r.aggiungi("Codice fiscale corretto (OCR)", Esito.ATTENZIONE, nota_cf)
    if not cf:
        from .layout import testo_da_ocr

        if testo_da_ocr():  # scansione: il codice c'è ma l'OCR non l'ha letto per intero
            r.aggiungi("Codice fiscale dipendente", Esito.ATTENZIONE,
                       "Codice fiscale non leggibile nella scansione: verificarlo sul documento")
        else:
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


    # --- Contratto: tipo di rapporto, orario, qualifica, livello ----------------
    from .contratto import controlla as controlla_contratto

    controlla_contratto(r, testo, _anno_mese_periodo(periodo))

    # --- Importi ------------------------------------------------------------
    for chiave, etichette in ETICHETTE.items():
        d[chiave] = cerca_importo(testo, etichette)

    # "Imp. IRPEF" in alcune buste è l'imponibile del mese, non il progressivo: se coincidono (e non è gennaio)
    am = _anno_mese_periodo(periodo)
    if d["progressivo_imponibile_fiscale"] is not None and d["progressivo_imponibile_fiscale"] == d["imponibile_fiscale"] \
            and am and am[1] != 1:
        d["progressivo_imponibile_fiscale"] = None

    # --- Voci con il calcolo (tariffa × ore, base × aliquota): ricalcolo e contributi IVS di tutte le pagine
    from .voci import analizza_voci

    voci = analizza_voci(testo)
    if voci.righe_ivs:
        # la riga "Contributo IVS base aliquota% importo" è la fonte più affidabile (e va sommata se ce ne sono
        # più d'una, ad esempio una per cantiere): l'etichetta da sola porterebbe a prendere la base
        d["contributi_dipendente"] = voci.ivs_importo
        if d["imponibile_previdenziale"] is None or abs(d["imponibile_previdenziale"] - voci.ivs_base) > 1:
            d["imponibile_previdenziale"] = voci.ivs_base
        d["contributi_obbligatori_totali"] = voci.ivs_importo + voci.altri_contributi
    if voci.calcoli:
        d["voci_ricalcolate"] = len(voci.calcoli)
        if voci.errati:
            elenco = "; ".join(f"{c.descrizione}: {c.formula} = {formatta_euro(c.atteso)}, indicato "
                               f"{formatta_euro(c.indicato)}" for c in voci.errati[:5])
            r.aggiungi("Calcolo delle voci", Esito.ERRORE,
                       f"{len(voci.errati)} voci su {len(voci.calcoli)} non tornano: {elenco}")
        else:
            r.aggiungi("Calcolo delle voci", Esito.OK,
                       f"{len(voci.calcoli)} voci ricalcolate (tariffa × quantità, base × aliquota): tutte corrette"
                       + (f"; contributi IVS da {voci.righe_ivs} righe = {formatta_euro(voci.ivs_importo)}"
                          if voci.righe_ivs > 1 else ""))

    # --- Intestazioni non lette (scansioni poco nitide): importi riconosciuti dai rapporti tra i numeri
    ricavati = []
    if d["totale_competenze"] is None:
        d["totale_competenze"] = deduzioni.totale_competenze_da_voci(testo)
        if d["totale_competenze"] is not None:
            ricavati.append(f"totale competenze {formatta_euro(d['totale_competenze'])} = somma delle voci")
    if d["contributi_dipendente"] is None:
        ivs = deduzioni.ivs_semplice(testo)
        if ivs:
            d["contributi_dipendente"] = ivs[1]
            d["imponibile_previdenziale"] = d["imponibile_previdenziale"] or ivs[0]
            ricavati.append(f"contributi IVS {formatta_euro(ivs[1])} su {formatta_euro(ivs[0])}")
    if d["imponibile_fiscale"] is None:
        terna = deduzioni.terna_imponibili(testo, d["imponibile_previdenziale"])
        if terna and (d["contributi_dipendente"] is None or terna[1] >= d["contributi_dipendente"]):
            d["imponibile_previdenziale"], d["imponibile_fiscale"] = terna[0], terna[2]
            d["contributi_obbligatori_totali"] = d.get("contributi_obbligatori_totali") or terna[1]
            ricavati.append(f"imponibile previdenziale {formatta_euro(terna[0])} − contributi {formatta_euro(terna[1])}"
                            f" = imponibile fiscale {formatta_euro(terna[2])}")
    if d["netto"] is None:
        d["netto"] = deduzioni.netto_vicino_accredito(testo, d["totale_competenze"])
        if d["netto"] is not None:
            ricavati.append(f"netto {formatta_euro(d['netto'])} letto vicino ad «ACCREDITO»/«NETTO»")
    if ricavati:
        r.aggiungi("Importi ricavati dai calcoli", Esito.ATTENZIONE,
                   "Intestazioni non leggibili (scansione poco nitida): " + "; ".join(ricavati)
                   + ". Verificare sul documento; per una lettura migliore scansionare a 300 dpi, foglio dritto, "
                   "oppure usare il PDF originale")

    comp, tratt, netto = d["totale_competenze"], d["totale_trattenute"], d["netto"]
    if comp is not None and netto is not None and tratt is None:
        # trattenute non lette: si mostra quanto è stato trattenuto in tutto e di cosa si tratta
        trattenute = comp - netto
        contributi = d.get("contributi_obbligatori_totali") or d.get("contributi_dipendente")
        dettaglio = f"{formatta_euro(comp)} − netto {formatta_euro(netto)} = trattenute {formatta_euro(trattenute)}"
        if contributi is not None:
            dettaglio += (f" (contributi {formatta_euro(contributi)} + IRPEF, addizionali e altre trattenute "
                          f"{formatta_euro(trattenute - contributi)})")
        esito = Esito.INFO if Decimal(0) <= trattenute <= comp / 2 else Esito.ATTENZIONE
        r.aggiungi("Quadratura netto", esito, dettaglio + " — totale trattenute non trovato: verificare")
    elif netto is None and comp is not None and tratt is not None:
        # netto non letto (dicitura non riconosciuta o scansione): lo si calcola, segnalandolo
        arr = (d["arrotondamento"] or 0) - (d["arrotondamento_precedente"] or 0)
        d["netto_calcolato"] = comp - tratt + arr
        r.aggiungi("Quadratura netto", Esito.ATTENZIONE,
                   f"Netto non trovato nel documento: calcolato {formatta_euro(comp)} − {formatta_euro(tratt)}"
                   + (f" ± arrotondamenti {formatta_euro(arr)}" if arr else "")
                   + f" = {formatta_euro(d['netto_calcolato'])}. Verificare sul documento (dicitura del netto non riconosciuta)")
    elif None in (comp, tratt, netto):
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
    if imp_prev and contr and not (Decimal("3") <= contr / imp_prev * 100 <= Decimal("15")):
        # un'aliquota impossibile vuol dire che è stato letto un altro numero (es. contributi azienda + dipendente):
        # non lo si usa negli altri calcoli, per non propagare l'errore
        aliquota = (contr / imp_prev * 100).quantize(Decimal("0.01"))
        r.aggiungi("Contributi INPS", Esito.ATTENZIONE,
                   f"Letto {formatta_euro(contr)} su imponibile {formatta_euro(imp_prev)} = {str(aliquota).replace('.', ',')}%: "
                   "aliquota impossibile per il dipendente (di solito ~9-10%), probabilmente è stato letto un altro "
                   "importo (es. totale contributi con la quota dell'azienda). Valore non usato negli altri calcoli")
        d["contributi_letti_scartati"] = contr
        d["contributi_dipendente"] = contr = None
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
    contr_mese, irpef_mese = d.get("contributi_obbligatori_totali") or d["contributi_dipendente"], d["irpef_netta"]
    if comp and contr_mese is not None and irpef_mese is not None:
        base = comp - contr_mese - irpef_mese - (d["addizionale_regionale"] or 0) - (d["addizionale_comunale"] or 0)
        descr = "lordo − contributi − IRPEF − addizionali"
    elif netto or d.get("netto_calcolato"):
        base = (netto or d["netto_calcolato"]) + sum((d[k] or 0) for k in ("cessione_quinto", "delegazione_pagamento",
                                                                           "pignoramento"))
        descr = "netto in busta + rate già trattenute (stima)" if netto else "netto calcolato + rate già trattenute (stima)"
    else:
        base, descr = None, ""
    if not d.get("mensilita_aggiuntiva"):
        controlla_impegni(r, base, descr)
        from .fattibilita import aggiungi_controlli

        aggiungi_controlli(r)

    if netto:
        r.aggiungi("Netto mensile", Esito.INFO, f"Netto percepito: {formatta_euro(netto)}")
    return r
