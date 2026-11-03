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
from decimal import Decimal

from .busta_paga import _trova_periodo
from .report import Esito, Report, cerca_importo, cerca_testo
from .validators import CF_REGEX, decodifica_codice_fiscale, formatta_euro

MENSILITA = 13  # le pensioni sono pagate in 13 rate (la tredicesima a dicembre)

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
    "cessione_quinto": [r"cessione\s+(?:del\s+)?(?:quinto|v)", r"quota\s+cedibile"],
    "prestito_delega": [r"delegazione\s+di\s+pagamento", r"prestito\s+(?:inps|pensionistico)", r"\bdelega\b"],
    "pignoramento": [r"pignorament[oi]", r"trattenuta\s+per\s+pignoramento"],
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

    # --- Pensionato --------------------------------------------------------------------
    codici = list(dict.fromkeys(x.group(0) for x in CF_REGEX.finditer(testo.upper())))
    cf = codici[0] if codici else None
    d["codice_fiscale_pensionato"] = cf
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
                   f"{sigla}: {descrizione}{nota}")

    # --- Importi -----------------------------------------------------------------------
    for chiave, etichette in ETICHETTE.items():
        d[chiave] = cerca_importo(testo, etichette, solo_riga=True)
    # rata con tredicesima: solo nei cedolini, se c'è una voce "tredicesima" con importo
    d["tredicesima"] = None if obis else (bool(re.search(
        r"(?im)^\s*(?:importo\s+)?(?:tredicesima|13\s*[ªa°^]\s*(?:mensilit[aà]|rata))\b[^\n]*\d+,\d{2}", testo)) or None)

    lordo, netto = d["importo_lordo"], d["importo_netto"]
    voci = ["ritenute_irpef", "addizionale_regionale", "addizionale_comunale", "cessione_quinto",
            "prestito_delega", "pignoramento", "altre_trattenute"]
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

    # Impegni già presenti
    impegni = [(k, d[k]) for k in ("cessione_quinto", "prestito_delega") if d[k]]
    if impegni:
        elenco = ", ".join(f"{k.replace('_', ' ')} {formatta_euro(v)}" for k, v in impegni)
        r.aggiungi("Cessione del quinto / prestiti", Esito.ATTENZIONE,
                   f"Già presenti trattenute per finanziamenti: {elenco} al mese")
    if d["pignoramento"]:
        r.aggiungi("Pignoramento", Esito.ATTENZIONE,
                   f"Trattenuta per pignoramento: {formatta_euro(d['pignoramento'])} al mese")

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
    return r
