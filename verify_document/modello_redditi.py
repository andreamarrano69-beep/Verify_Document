"""Analisi del Modello Redditi Persone Fisiche (ex Modello Unico).

- Individua il regime fiscale dai quadri compilati (LM, RE, RG, RF, RC, ...)
- Estrae reddito e imposte e calcola il reddito mensile
- Per il forfettario: verifica aliquota (5%/15%), coefficiente di redditività e soglia ricavi
- Quadro RN: reddito complessivo = somma dei quadri, imponibile = complessivo − deduzioni,
  imposta lorda = IRPEF a scaglioni, imposta netta = lorda − detrazioni, saldo a debito/credito
- Quadri RE/RG: compensi/ricavi − spese/costi = reddito; cedolare secca 10/21/26%; addizionali

NB: la numerazione dei righi cambia tra un anno e l'altro, quindi la ricerca è fatta
principalmente per descrizione. Verificare sempre le etichette sul modello dell'anno.
"""

from __future__ import annotations

import re
from decimal import Decimal

from .report import Esito, Report, cerca_importo
from .validators import CF_REGEX, decodifica_codice_fiscale, formatta_euro

SOGLIA_FORFETTARIO = Decimal("85000")       # ricavi/compensi anno precedente
SOGLIA_USCITA_IMMEDIATA = Decimal("100000")  # uscita in corso d'anno

QUADRI = {
    "LM": "Quadro LM – regime forfettario / di vantaggio",
    "RE": "Quadro RE – lavoro autonomo (professionisti) regime ordinario",
    "RG": "Quadro RG – impresa in contabilità semplificata",
    "RF": "Quadro RF – impresa in contabilità ordinaria",
    "RD": "Quadro RD – allevamento",
    "RH": "Quadro RH – redditi da partecipazione (soci di società di persone)",
    "RC": "Quadro RC – lavoro dipendente e pensione",
    "RB": "Quadro RB – fabbricati",
    "RA": "Quadro RA – terreni",
    "RL": "Quadro RL – altri redditi",
}

ETICHETTE = {
    # quadro RN – determinazione dell'IRPEF
    "reddito_complessivo": [r"reddito\s+complessivo"],
    "deduzione_abitazione": [r"deduzione\s+(?:per\s+)?(?:l['’]\s*)?abitazione\s+principale"],
    "oneri_deducibili": [r"oneri\s+deducibili"],
    "reddito_imponibile": [r"(?<!\w)reddito\s+imponibile(?!\s+(?:cedolare|addizional))"],
    "imposta_lorda": [r"imposta\s+lorda"],
    "totale_detrazioni": [r"totale\s+detrazioni(?:\s+d['’]\s*imposta)?"],
    "imposta_netta": [r"imposta\s+netta"],
    "ritenute_totali": [r"ritenute\s+totali", r"totale\s+ritenute"],
    "acconti_versati": [r"acconti\s+versati"],
    "imposta_a_debito": [r"imposta\s+a\s+debito"],
    "imposta_a_credito": [r"imposta\s+a\s+credito"],
    # quadri dei redditi
    "reddito_dipendente": [r"redditi?\s+di\s+lavoro\s+dipendente", r"lavoro\s+dipendente\s+e\s+assimilati"],
    "reddito_fabbricati": [r"reddito\s+(?:dei\s+)?fabbricati(?!\s+(?:a\s+)?cedolare)"],
    "reddito_impresa": [r"reddito\s+d['’]\s*impresa", r"reddito\s+di\s+impresa"],
    "reddito_lavoro_autonomo": [r"reddito\s+(?:netto\s+)?(?:di|da)\s+lavoro\s+autonomo"],
    "reddito_partecipazione": [r"reddito\s+(?:di\s+|da\s+)?partecipazione"],
    "altri_redditi": [r"totale\s+altri\s+redditi", r"redditi\s+diversi"],
    # quadro RE – lavoro autonomo
    "compensi_re": [r"totale\s+compensi", r"compensi\s+derivanti\s+dall['’]\s*attivit[aà]", r"\bcompensi\b"],
    "spese_re": [r"totale\s+(?:delle\s+)?spese", r"totale\s+componenti\s+negativi"],
    # quadro RG – impresa in contabilità semplificata
    "ricavi_rg": [r"totale\s+componenti\s+positivi", r"\bricavi\b(?!\s+o\s+compensi)"],
    "costi_rg": [r"totale\s+componenti\s+negativi", r"totale\s+costi"],
    # cedolare secca (quadro RB)
    "imponibile_cedolare": [r"(?:reddito\s+)?imponibile\s+(?:a\s+)?cedolare\s+secca"],
    "imposta_cedolare": [r"(?:totale\s+)?imposta\s+(?:a\s+)?cedolare\s+secca"],
    # quadro RV – addizionali
    "addizionale_regionale": [r"addizionale\s+regionale(?:\s+all['’]\s*irpef)?\s+dovuta"],
    "addizionale_comunale": [r"addizionale\s+comunale(?:\s+all['’]\s*irpef)?\s+dovuta"],
}

ETICHETTE_LM = {
    "ricavi_compensi": [r"componenti\s+positivi", r"ricavi\s+o\s+compensi", r"compensi\s+percepiti",
                        r"ricavi\s+conseguiti"],
    "coefficiente_redditivita_%": [r"coefficiente\s+di\s+redditivit[aà]"],
    "reddito_lordo_lm": [r"reddito\s+lordo"],
    "contributi_previdenziali": [r"contributi\s+previdenziali"],
    "reddito_netto_lm": [r"reddito\s+netto"],
    "imposta_sostitutiva": [r"imposta\s+sostitutiva"],
}


def riconosci(testo: str) -> int:
    t = testo.lower()
    punti = 0
    for k in ["redditi persone fisiche", "modello unico", "unico persone fisiche", "periodo d'imposta",
              "quadro rn", "quadro lm", "reddito complessivo", "agenzia delle entrate", "imposta netta"]:
        if k in t:
            punti += 1
    return punti


def _quadri_presenti(testo: str) -> list[str]:
    presenti = []
    for q in QUADRI:
        # "QUADRO LM" oppure codici rigo "LM1", "LM34", ... seguiti da spazio/punto
        if re.search(rf"\bquadro\s+{q}\b", testo, re.IGNORECASE) or re.search(
            rf"(?m)^\s*{q}\d{{1,2}}\b", testo
        ):
            presenti.append(q)
    return presenti


def _determina_regime(testo: str, quadri: list[str]) -> str:
    t = testo.lower()
    if "LM" in quadri or "forfetari" in t or "forfettari" in t:
        if re.search(r"forfe+t+ari|forfet+ario", t):
            return "Forfettario"
        if "vantaggio" in t or "minimi" in t:
            return "Regime di vantaggio (contribuenti minimi)"
        return "Forfettario"
    if "RF" in quadri:
        return "Impresa – contabilità ordinaria"
    if "RG" in quadri:
        return "Impresa – contabilità semplificata"
    if "RE" in quadri:
        return "Lavoro autonomo – regime ordinario (IRPEF)"
    if "RH" in quadri:
        return "Socio di società di persone (redditi da partecipazione)"
    if "RC" in quadri:
        return "Lavoratore dipendente / pensionato (nessuna partita IVA)"
    return "Non determinato"


def analizza(testo: str) -> Report:
    r = Report("Modello Redditi PF (ex Unico)")
    d = r.dati

    m = re.search(r"periodo\s+d['’]\s*imposta\s*(\d{4})", testo, re.IGNORECASE) or re.search(
        r"redditi\s+(\d{4})", testo, re.IGNORECASE
    )
    if m:
        anno = int(m.group(1))
        # "REDDITI 2025" si riferisce al periodo d'imposta 2024
        d["periodo_imposta"] = anno if "periodo" in m.group(0).lower() else anno - 1

    codici = list(dict.fromkeys(x.group(0) for x in CF_REGEX.finditer(testo.upper())))
    d["codice_fiscale_contribuente"] = codici[0] if codici else None
    if codici:
        info = decodifica_codice_fiscale(codici[0])
        r.aggiungi("Codice fiscale contribuente", Esito.OK if info.valido else Esito.ERRORE,
                   f"{codici[0]} {'valido' if info.valido else 'NON valido'}")
    else:
        r.aggiungi("Codice fiscale contribuente", Esito.ATTENZIONE, "Codice fiscale non trovato")

    quadri = _quadri_presenti(testo)
    d["quadri_compilati"] = quadri
    regime = _determina_regime(testo, quadri)
    d["regime_fiscale"] = regime
    r.aggiungi("Regime fiscale", Esito.INFO if regime != "Non determinato" else Esito.ATTENZIONE,
               f"{regime} — quadri rilevati: {', '.join(quadri) or 'nessuno'}")

    for chiave, etichette in ETICHETTE.items():
        d[chiave] = cerca_importo(testo, etichette, solo_decimali=False, solo_riga=True)
    if "RE" not in quadri:
        d["compensi_re"] = d["spese_re"] = None
    if "RG" not in quadri and "RF" not in quadri:
        d["ricavi_rg"] = d["costi_rg"] = None

    if regime.startswith("Forfettario") or regime.startswith("Regime di vantaggio"):
        for chiave, etichette in ETICHETTE_LM.items():
            d[chiave] = cerca_importo(testo, etichette, solo_decimali=False, solo_riga=True)
        _controlli_forfettario(r)
        reddito_annuo = d["reddito_netto_lm"] or d["reddito_lordo_lm"]
        imposte = d["imposta_sostitutiva"] or Decimal(0)
        # eventuali altri redditi IRPEF (es. dipendente part-time) nel quadro RN
        if d["reddito_complessivo"]:
            reddito_annuo = (reddito_annuo or 0) + d["reddito_complessivo"]
            imposte += d["imposta_netta"] or 0
    else:
        reddito_annuo = d["reddito_complessivo"]
        imposte = d["imposta_netta"] or Decimal(0)

    _controlli_quadri_attivita(r)
    _controlli_rn(r)
    _controlli_cedolare_addizionali(r)

    # redditi a tassazione separata e addizionali entrano nel reddito disponibile
    if d["imponibile_cedolare"]:
        reddito_annuo = (reddito_annuo or 0) + d["imponibile_cedolare"]
        imposte += d["imposta_cedolare"] or 0
    imposte += (d["addizionale_regionale"] or 0) + (d["addizionale_comunale"] or 0)

    d["reddito_annuo"] = reddito_annuo
    if reddito_annuo is None:
        r.aggiungi("Reddito mensile", Esito.ERRORE, "Reddito non trovato nel documento")
        return r

    netto_annuo = reddito_annuo - imposte
    d["imposte_annue"] = imposte
    d["reddito_netto_imposte_annuo"] = netto_annuo
    d["reddito_mensile_lordo"] = (reddito_annuo / 12).quantize(Decimal("0.01"))
    d["reddito_mensile_netto"] = (netto_annuo / 12).quantize(Decimal("0.01"))
    nota = f" (di cui {formatta_euro(d['imponibile_cedolare'])} affitti a cedolare secca)" \
        if d.get("imponibile_cedolare") else ""
    r.aggiungi("Reddito mensile", Esito.INFO,
               f"Annuo {formatta_euro(reddito_annuo)}{nota} → mensile {formatta_euro(d['reddito_mensile_lordo'])} "
               f"(al netto delle imposte {formatta_euro(d['reddito_mensile_netto'])} su 12 mesi)")
    if reddito_annuo <= 0:
        r.aggiungi("Reddito", Esito.ATTENZIONE, "Reddito nullo o negativo (perdita)")
    return r


TOLLERANZA = Decimal("1")  # i modelli riportano gli importi in euro: ±1 per gli arrotondamenti


def _controlli_quadri_attivita(r: Report) -> None:
    """RE: compensi − spese = reddito; RG: ricavi − costi = reddito d'impresa."""
    d = r.dati
    for nome, positivi, negativi, reddito, etichetta in [
        ("Quadro RE", "compensi_re", "spese_re", "reddito_lavoro_autonomo", "compensi − spese"),
        ("Quadro RG/RF", "ricavi_rg", "costi_rg", "reddito_impresa", "ricavi − costi"),
    ]:
        p, n, red = d.get(positivi), d.get(negativi), d.get(reddito)
        if p is None or n is None or red is None:
            continue
        differenza = p - n
        testo = f"{formatta_euro(p)} − {formatta_euro(n)} = {formatta_euro(differenza)}"
        if abs(differenza - red) <= TOLLERANZA:
            r.aggiungi(nome, Esito.OK, f"{etichetta}: {testo} = reddito dichiarato")
        elif red < differenza:
            r.aggiungi(nome, Esito.ATTENZIONE,
                       f"{etichetta}: {testo}, reddito dichiarato {formatta_euro(red)} "
                       "(inferiore: perdite pregresse o altre deduzioni?)")
        else:
            r.aggiungi(nome, Esito.ERRORE,
                       f"{etichetta}: {testo}, ma il reddito dichiarato è {formatta_euro(red)}: "
                       "superiore a quanto risulta dai conti")


def _controlli_rn(r: Report) -> None:
    """Catena di calcolo del quadro RN: complessivo → imponibile → imposta lorda → netta → debito/credito."""
    from .cu import SCAGLIONI_IRPEF, irpef_lorda

    d = r.dati
    complessivo = d["reddito_complessivo"]
    if complessivo is None:
        return

    # 1. reddito complessivo = somma dei redditi dei quadri
    componenti = {k: d[k] for k in ("reddito_dipendente", "reddito_lavoro_autonomo", "reddito_impresa",
                                    "reddito_fabbricati", "reddito_partecipazione", "altri_redditi")
                  if d.get(k) is not None}
    if componenti:
        somma = sum(componenti.values(), Decimal(0))
        elenco = " + ".join(f"{k.removeprefix('reddito_').replace('_', ' ')} {formatta_euro(v)}"
                            for k, v in componenti.items())
        if abs(somma - complessivo) <= TOLLERANZA:
            r.aggiungi("Reddito complessivo", Esito.OK, f"{elenco} = {formatta_euro(complessivo)}")
        else:
            r.aggiungi("Reddito complessivo", Esito.ATTENZIONE,
                       f"{elenco} = {formatta_euro(somma)}, dichiarato {formatta_euro(complessivo)} "
                       "(quadri non letti, perdite o redditi esenti?)")

    # 2. reddito imponibile = complessivo − abitazione principale − oneri deducibili
    deduzioni = (d["deduzione_abitazione"] or 0) + (d["oneri_deducibili"] or 0)
    atteso_imp = max(complessivo - deduzioni, Decimal(0))
    imponibile = d["reddito_imponibile"]
    if imponibile is not None:
        if abs(imponibile - atteso_imp) <= TOLLERANZA:
            r.aggiungi("Reddito imponibile", Esito.OK,
                       f"{formatta_euro(complessivo)} − deduzioni {formatta_euro(deduzioni)} = "
                       f"{formatta_euro(imponibile)}")
        else:
            r.aggiungi("Reddito imponibile", Esito.ERRORE,
                       f"{formatta_euro(complessivo)} − deduzioni {formatta_euro(deduzioni)} = "
                       f"{formatta_euro(atteso_imp)}, ma è indicato {formatta_euro(imponibile)}")
    else:
        imponibile = atteso_imp

    # 3. imposta lorda = IRPEF a scaglioni sul reddito imponibile
    lorda = d["imposta_lorda"]
    anno = d.get("periodo_imposta")
    teorica = irpef_lorda(imponibile, anno) if imponibile else Decimal(0)
    d["imposta_lorda_calcolata"] = teorica
    if lorda is not None:
        if teorica is None:
            r.aggiungi("Imposta lorda", Esito.INFO,
                       f"Scaglioni IRPEF {anno or '?'} non configurati: verifica non eseguita")
        elif abs(lorda - teorica) <= TOLLERANZA:
            r.aggiungi("Imposta lorda", Esito.OK,
                       f"IRPEF su {formatta_euro(imponibile)} con gli scaglioni {anno} = {formatta_euro(teorica)}")
        else:
            scaglioni = ", ".join(f"{a}%" + (f" fino a {lim:,}".replace(",", ".") if lim else " oltre")
                                  for lim, a in SCAGLIONI_IRPEF[anno])
            r.aggiungi("Imposta lorda", Esito.ERRORE,
                       f"Indicata {formatta_euro(lorda)}, ma l'IRPEF su {formatta_euro(imponibile)} è "
                       f"{formatta_euro(teorica)} (scaglioni {anno}: {scaglioni})")

    # 4. imposta netta = imposta lorda − detrazioni (mai negativa)
    netta, detrazioni = d["imposta_netta"], d["totale_detrazioni"]
    base = lorda if lorda is not None else teorica
    if netta is not None and base is not None:
        if detrazioni is not None:
            attesa = max(base - detrazioni, Decimal(0))
            if abs(netta - attesa) <= TOLLERANZA:
                r.aggiungi("Imposta netta", Esito.OK,
                           f"{formatta_euro(base)} − detrazioni {formatta_euro(detrazioni)} = {formatta_euro(netta)}")
            else:
                r.aggiungi("Imposta netta", Esito.ERRORE,
                           f"{formatta_euro(base)} − detrazioni {formatta_euro(detrazioni)} = "
                           f"{formatta_euro(attesa)}, ma è indicata {formatta_euro(netta)}")
        elif netta > base + TOLLERANZA:
            r.aggiungi("Imposta netta", Esito.ERRORE, "Imposta netta maggiore dell'imposta lorda")
        else:
            r.aggiungi("Imposta netta", Esito.OK,
                       f"{formatta_euro(netta)} ≤ imposta lorda {formatta_euro(base)} "
                       f"(detrazioni {formatta_euro(base - netta)})")

    # 5. saldo = imposta netta − ritenute − acconti
    debito, credito = d["imposta_a_debito"], d["imposta_a_credito"]
    if netta is not None and (debito is not None or credito is not None) \
            and (d["ritenute_totali"] is not None or d["acconti_versati"] is not None):
        saldo = netta - (d["ritenute_totali"] or 0) - (d["acconti_versati"] or 0)
        dichiarato = (debito or 0) - (credito or 0)
        descr = (f"{formatta_euro(netta)} − ritenute {formatta_euro(d['ritenute_totali'] or 0)} − acconti "
                 f"{formatta_euro(d['acconti_versati'] or 0)} = {formatta_euro(saldo)}")
        if abs(saldo - dichiarato) <= TOLLERANZA:
            r.aggiungi("Imposta a debito/credito", Esito.OK,
                       f"{descr} ({'a debito' if dichiarato >= 0 else 'a credito'})")
        else:
            r.aggiungi("Imposta a debito/credito", Esito.ATTENZIONE,
                       f"{descr}, dichiarato {formatta_euro(dichiarato)} "
                       "(crediti d'imposta o eccedenze dell'anno precedente non considerati?)")


ALIQUOTE_CEDOLARE = (Decimal(10), Decimal(21), Decimal(26))
ADDIZIONALE_REGIONALE = (Decimal("1.23"), Decimal("3.33"))  # minimo e massimo (%)
ADDIZIONALE_COMUNALE_MAX = Decimal("0.9")


def _controlli_cedolare_addizionali(r: Report) -> None:
    d = r.dati
    imp, ced = d["imponibile_cedolare"], d["imposta_cedolare"]
    if imp and ced is not None:
        aliquota = (ced / imp * 100).quantize(Decimal("0.1"))
        vicina = min(ALIQUOTE_CEDOLARE, key=lambda a: abs(a - aliquota))
        testo = f"{formatta_euro(ced)} su {formatta_euro(imp)} = {str(aliquota).replace('.', ',')}%"
        if abs(vicina - aliquota) <= Decimal("0.3"):
            r.aggiungi("Cedolare secca", Esito.OK, f"{testo} (aliquota {vicina}%)")
        elif aliquota < 10:
            r.aggiungi("Cedolare secca", Esito.ATTENZIONE,
                       f"{testo}: aliquote diverse sui vari contratti (10%/21%/26%) o errore")
        else:
            r.aggiungi("Cedolare secca", Esito.ERRORE, f"{testo}: non corrisponde a 10%, 21% o 26%")

    base = d["reddito_imponibile"]
    if base is None and d["reddito_complessivo"] is not None:
        base = d["reddito_complessivo"] - (d["deduzione_abitazione"] or 0) - (d["oneri_deducibili"] or 0)
    if not base or base <= 0:
        return
    reg = d["addizionale_regionale"]
    if reg is not None:
        aliquota = (reg / base * 100).quantize(Decimal("0.01"))
        testo = f"{formatta_euro(reg)} = {str(aliquota).replace('.', ',')}% del reddito imponibile"
        minimo, massimo = ADDIZIONALE_REGIONALE
        esito = Esito.OK if minimo - Decimal("0.05") <= aliquota <= massimo + Decimal("0.05") else Esito.ATTENZIONE
        r.aggiungi("Addizionale regionale", esito,
                   testo + ("" if esito == Esito.OK else f" (fuori dall'intervallo {minimo}%–{massimo}%)"))
    com = d["addizionale_comunale"]
    if com is not None:
        aliquota = (com / base * 100).quantize(Decimal("0.01"))
        testo = f"{formatta_euro(com)} = {str(aliquota).replace('.', ',')}% del reddito imponibile"
        esito = Esito.OK if aliquota <= ADDIZIONALE_COMUNALE_MAX + Decimal("0.05") else Esito.ATTENZIONE
        r.aggiungi("Addizionale comunale", esito,
                   testo + ("" if esito == Esito.OK else f" (oltre il massimo {ADDIZIONALE_COMUNALE_MAX}%)"))


def _controlli_forfettario(r: Report) -> None:
    d = r.dati
    ricavi, coeff = d["ricavi_compensi"], d["coefficiente_redditivita_%"]
    lordo, netto, imp = d["reddito_lordo_lm"], d["reddito_netto_lm"], d["imposta_sostitutiva"]

    if ricavi is not None:
        if ricavi > SOGLIA_USCITA_IMMEDIATA:
            r.aggiungi("Soglia ricavi", Esito.ERRORE,
                       f"Ricavi {formatta_euro(ricavi)} oltre {formatta_euro(SOGLIA_USCITA_IMMEDIATA)}: "
                       "uscita immediata dal forfettario")
        elif ricavi > SOGLIA_FORFETTARIO:
            r.aggiungi("Soglia ricavi", Esito.ATTENZIONE,
                       f"Ricavi {formatta_euro(ricavi)} oltre {formatta_euro(SOGLIA_FORFETTARIO)}: "
                       "uscita dal forfettario dall'anno successivo")
        else:
            r.aggiungi("Soglia ricavi", Esito.OK,
                       f"Ricavi {formatta_euro(ricavi)} entro la soglia di {formatta_euro(SOGLIA_FORFETTARIO)}")

    if ricavi and coeff and lordo is not None:
        atteso = (ricavi * coeff / 100).quantize(Decimal("1"))
        if abs(atteso - lordo) <= 1:
            r.aggiungi("Coefficiente di redditività", Esito.OK,
                       f"{formatta_euro(ricavi)} × {coeff}% = {formatta_euro(lordo)}")
        else:
            r.aggiungi("Coefficiente di redditività", Esito.ERRORE,
                       f"{formatta_euro(ricavi)} × {coeff}% = {formatta_euro(atteso)}, "
                       f"ma il reddito lordo indicato è {formatta_euro(lordo)}")

    contr = d["contributi_previdenziali"]
    if lordo is not None and netto is not None and contr is not None:
        if abs(lordo - contr - netto) <= 1:
            r.aggiungi("Reddito netto LM", Esito.OK, "Reddito lordo − contributi = reddito netto")
        else:
            r.aggiungi("Reddito netto LM", Esito.ATTENZIONE,
                       f"Lordo − contributi = {formatta_euro(lordo - contr)}, indicato {formatta_euro(netto)} "
                       "(possibili perdite pregresse)")

    if netto and imp is not None and netto > 0:
        aliquota = (imp / netto * 100).quantize(Decimal("0.1"))
        d["aliquota_sostitutiva_%"] = aliquota
        if abs(aliquota - 5) <= Decimal("0.2"):
            r.aggiungi("Aliquota imposta sostitutiva", Esito.OK, "5% (agevolata start-up, primi 5 anni)")
        elif abs(aliquota - 15) <= Decimal("0.2"):
            r.aggiungi("Aliquota imposta sostitutiva", Esito.OK, "15% (ordinaria forfettario)")
        else:
            r.aggiungi("Aliquota imposta sostitutiva", Esito.ATTENZIONE,
                       f"Aliquota calcolata {aliquota}%: né 5% né 15%, verificare")
