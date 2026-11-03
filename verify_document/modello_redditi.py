"""Analisi del Modello Redditi Persone Fisiche (ex Modello Unico).

- Individua il regime fiscale dai quadri compilati (LM, RE, RG, RF, RC, ...)
- Estrae reddito e imposte e calcola il reddito mensile
- Per il forfettario: verifica aliquota (5%/15%), coefficiente di redditività e soglia ricavi

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
    "reddito_complessivo": [r"reddito\s+complessivo"],
    "imposta_lorda": [r"imposta\s+lorda"],
    "imposta_netta": [r"imposta\s+netta"],
    "reddito_dipendente": [r"redditi?\s+di\s+lavoro\s+dipendente", r"lavoro\s+dipendente\s+e\s+assimilati"],
    "reddito_fabbricati": [r"reddito\s+(?:dei\s+)?fabbricati"],
    # impresa / professionista ordinario
    "reddito_impresa": [r"reddito\s+d['’]\s*impresa", r"reddito\s+di\s+impresa"],
    "reddito_lavoro_autonomo": [r"reddito\s+(?:netto\s+)?(?:di|da)\s+lavoro\s+autonomo"],
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
        d[chiave] = cerca_importo(testo, etichette, solo_decimali=False)

    if regime.startswith("Forfettario") or regime.startswith("Regime di vantaggio"):
        for chiave, etichette in ETICHETTE_LM.items():
            d[chiave] = cerca_importo(testo, etichette, solo_decimali=False)
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
        if d["imposta_lorda"] is not None and d["imposta_netta"] is not None:
            if d["imposta_netta"] > d["imposta_lorda"]:
                r.aggiungi("Imposte", Esito.ERRORE, "Imposta netta maggiore dell'imposta lorda")
            else:
                r.aggiungi("Imposte", Esito.OK,
                           f"Imposta lorda {formatta_euro(d['imposta_lorda'])}, "
                           f"netta {formatta_euro(d['imposta_netta'])}")

    d["reddito_annuo"] = reddito_annuo
    if reddito_annuo is None:
        r.aggiungi("Reddito mensile", Esito.ERRORE, "Reddito non trovato nel documento")
        return r

    netto_annuo = reddito_annuo - imposte
    d["imposte_annue"] = imposte
    d["reddito_netto_imposte_annuo"] = netto_annuo
    d["reddito_mensile_lordo"] = (reddito_annuo / 12).quantize(Decimal("0.01"))
    d["reddito_mensile_netto"] = (netto_annuo / 12).quantize(Decimal("0.01"))
    r.aggiungi("Reddito mensile", Esito.INFO,
               f"Annuo {formatta_euro(reddito_annuo)} → mensile {formatta_euro(d['reddito_mensile_lordo'])} "
               f"(al netto delle imposte {formatta_euro(d['reddito_mensile_netto'])} su 12 mesi)")
    if reddito_annuo <= 0:
        r.aggiungi("Reddito", Esito.ATTENZIONE, "Reddito nullo o negativo (perdita)")
    return r


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
