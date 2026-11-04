"""Analisi della Certificazione Unica (CU) – parte lavoro dipendente.

Estrae: sostituto d'imposta (datore di lavoro), dipendente, anno, redditi di lavoro dipendente,
giorni lavorati, ritenute IRPEF, addizionali, dati previdenziali INPS, data inizio rapporto.

Controlli:
- codice fiscale del dipendente e del sostituto d'imposta validi
- giorni lavorati entro i giorni dell'anno
- ritenute IRPEF non superiori all'IRPEF lorda calcolata con gli scaglioni dell'anno
  (le detrazioni possono solo ridurre l'imposta)
- contributi INPS coerenti con l'imponibile previdenziale
- reddito fiscale ≈ imponibile previdenziale − contributi
- reddito mensile medio lordo e netto (ritenute e addizionali)

NB: la ricerca avviene per descrizione; i numeri dei punti (1, 2, 6, 21, ...) sono solo un aiuto.
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

from .busta_paga import ALIQUOTE_INPS
from .report import Esito, Report, cerca_importo, cerca_testo
from .validators import (
    trova_codici_fiscali,
    CF_REGEX,
    PIVA_REGEX,
    decodifica_codice_fiscale,
    formatta_euro,
    parse_data,
    valida_codice_fiscale,
    valida_partita_iva,
)

# Scaglioni IRPEF per anno d'imposta: (limite superiore, aliquota %). Verificare ogni anno.
SCAGLIONI_IRPEF = {
    2022: [(15000, 23), (28000, 25), (50000, 35), (None, 43)],
    2023: [(15000, 23), (28000, 25), (50000, 35), (None, 43)],
    2024: [(28000, 23), (50000, 35), (None, 43)],
    2025: [(28000, 23), (50000, 35), (None, 43)],
    2026: [(28000, 23), (50000, 33), (None, 43)],  # Legge di bilancio 2026: 2° scaglione al 33%
}

ETICHETTE = {
    "reddito_indeterminato": [
        r"redditi\s+di\s+lavoro\s+dipendente\s+e\s+assimilati[^\n]{0,40}indeterminato",
        r"(?:punto\s+)?\b1\b[\s.)-]+redditi\s+di\s+lavoro\s+dipendente",
        r"tempo\s+indeterminato",
    ],
    "reddito_determinato": [
        r"redditi\s+di\s+lavoro\s+dipendente\s+e\s+assimilati[^\n]{0,40}(?<!in)determinato",
        r"(?<!in)\btempo\s+determinato",
    ],
    "reddito_pensione": [r"redditi\s+di\s+pensione"],
    "giorni_lavoro": [r"(?:numero\s+(?:di\s+)?)?giorni\s+(?:di\s+)?lavoro\s+dipendente", r"giorni\s+lavorati"],
    "giorni_pensione": [r"(?:numero\s+(?:di\s+)?)?giorni\s+(?:di\s+)?pensione"],
    # NB: anche "redditi di pensione" (punto 3) è letto da reddito_pensione
    "ritenute_irpef": [r"ritenute\s+irpef", r"ritenute\s+d['’]acconto\s+irpef"],
    "addizionale_regionale": [r"addizionale\s+regionale(?:\s+all['’]\s*irpef)?(?!\s+sospes)"],
    "addizionale_comunale_saldo": [r"saldo\s+addizionale\s+comunale", r"addizionale\s+comunale[^\n]{0,30}saldo"],
    "addizionale_comunale_acconto": [r"acconto\s+addizionale\s+comunale",
                                     r"addizionale\s+comunale[^\n]{0,30}acconto"],
    "imponibile_previdenziale": [r"imponibile\s+previdenziale"],
    "contributi_lavoratore": [r"contributi\s+a\s+carico\s+del\s+lavoratore(?:\s+trattenuti)?",
                              r"contributi\s+(?:inps\s+)?(?:a\s+carico\s+)?(?:del\s+)?dipendente"],
}


def riconosci(testo: str) -> int:
    t = testo.lower()
    punti = 0
    for k, peso in [("certificazione unica", 4), ("certificazione lavoro dipendente", 2),
                    ("sostituto d'imposta", 1), ("sostituto d’imposta", 1), ("percipiente", 1),
                    ("dati fiscali", 1), ("dati previdenziali", 1), ("ritenute irpef", 1)]:
        if k in t:
            punti += peso
    return punti


def irpef_lorda(reddito: Decimal, anno: int | None) -> Decimal | None:
    scaglioni = SCAGLIONI_IRPEF.get(anno or 0)
    if not scaglioni or reddito is None or reddito <= 0:
        return None
    imposta, inferiore = Decimal(0), Decimal(0)
    for limite, aliquota in scaglioni:
        superiore = Decimal(limite) if limite else reddito
        if reddito > inferiore:
            imposta += (min(reddito, superiore) - inferiore) * Decimal(aliquota) / 100
        inferiore = superiore
        if limite is None or reddito <= superiore:
            break
    return imposta.quantize(Decimal("0.01"))


def _trova_sostituto(testo: str) -> str | None:
    """Codice fiscale del datore di lavoro (11 cifre per le società, 16 caratteri per le ditte individuali)."""
    m = re.search(r"sostituto\s+d['’]\s*imposta", testo, re.IGNORECASE)
    zona = testo[m.end(): m.end() + 300] if m else testo
    m11 = re.search(r"(?<!\d)\d{11}(?!\d)", zona)
    if m11:
        return m11.group(0)
    m16 = CF_REGEX.search(zona.upper())
    if m and m16:
        return m16.group(0)
    for x in PIVA_REGEX.finditer(testo):
        if valida_partita_iva(x.group(0)):
            return x.group(0)
    return None


def _trova_dipendente(testo: str, sostituto: str | None) -> str | None:
    m = re.search(r"dati\s+(?:anagrafici\s+)?(?:relativi\s+al\s+)?(?:dipendente|percipiente|lavoratore)",
                  testo, re.IGNORECASE)
    zona = testo[m.end():] if m else testo
    for cf in trova_codici_fiscali(zona) + trova_codici_fiscali(testo):
        if cf != sostituto:
            return cf
    return None


def analizza(testo: str) -> Report:
    r = Report("Certificazione Unica (CU)")
    d = r.dati

    m = re.search(r"periodo\s+d['’]\s*imposta\s*(\d{4})", testo, re.IGNORECASE)
    if m:
        d["periodo_imposta"] = int(m.group(1))
    else:
        m = re.search(r"certificazione\s+unica\s+(\d{4})", testo, re.IGNORECASE)
        if m:  # la "CU 2026" certifica i redditi del 2025
            d["periodo_imposta"] = int(m.group(1)) - 1
    anno = d.get("periodo_imposta")

    # --- Soggetti ---------------------------------------------------------------------
    sostituto = _trova_sostituto(testo)
    d["sostituto_imposta"] = sostituto
    d["partita_iva_azienda"] = sostituto if sostituto and sostituto.isdigit() else None
    if not sostituto:
        r.aggiungi("Sostituto d'imposta", Esito.ATTENZIONE, "Codice fiscale del datore di lavoro non trovato")
    else:
        valido = valida_partita_iva(sostituto) if sostituto.isdigit() else valida_codice_fiscale(sostituto)
        r.aggiungi("Sostituto d'imposta", Esito.OK if valido else Esito.ERRORE,
                   f"{sostituto} {'valido' if valido else 'NON valido (cifra di controllo errata)'}")

    cf = _trova_dipendente(testo, sostituto)
    d["codice_fiscale_dipendente"] = cf
    if not cf:
        r.aggiungi("Codice fiscale dipendente", Esito.ERRORE, "Codice fiscale non trovato")
    else:
        info = decodifica_codice_fiscale(cf)
        r.aggiungi("Codice fiscale dipendente", Esito.OK if info.valido else Esito.ERRORE,
                   f"{cf} {'valido' if info.valido else 'NON valido (carattere di controllo errato)'}")

    m = re.search(r"(?i:cognome)\s*[:\-]?\s*([A-Z][A-Z'À-Ü ]+?)\s+(?i:nome)\s*[:\-]?\s*([A-Z][A-Z'À-Ü]+(?: [A-Z'À-Ü]+)?)\b",
                  testo[testo.upper().find("DIPENDENTE"):] if "DIPENDENTE" in testo.upper() else testo)
    d["nominativo"] = f"{m.group(1).strip()} {m.group(2).strip()}" if m else None

    inizio = cerca_testo(testo, [r"data\s+(?:di\s+)?inizio(?:\s+del)?\s+rapporto", r"data\s+(?:di\s+)?assunzione",
                                 r"data\s+inizio"], r"(\d{1,2}[/.\-]\d{1,2}[/.\-]\d{2,4})")
    d["data_assunzione"] = parse_data(inizio) if inizio else None
    fine = cerca_testo(testo, [r"data\s+(?:di\s+)?(?:cessazione|fine)(?:\s+del)?(?:\s+rapporto)?"],
                       r"(\d{1,2}[/.\-]\d{1,2}[/.\-]\d{2,4})")
    d["data_cessazione"] = parse_data(fine) if fine else None

    # --- Importi ---------------------------------------------------------------------
    for chiave, etichette in ETICHETTE.items():
        intero = chiave.startswith("giorni")
        d[chiave] = cerca_importo(testo, etichette, solo_decimali=not intero, solo_riga=True)
    for k in ("giorni_lavoro", "giorni_pensione"):
        if d[k] is not None:
            d[k] = int(d[k])

    lavoro = [d[k] for k in ("reddito_indeterminato", "reddito_determinato") if d[k]]
    d["reddito_lavoro_dipendente"] = sum(lavoro, Decimal(0)) if lavoro else None
    if lavoro and d["reddito_pensione"]:
        d["tipo_reddito"] = "Lavoro dipendente e pensione"
    elif d["reddito_pensione"]:
        d["tipo_reddito"] = "Pensione"
    elif lavoro:
        d["tipo_reddito"] = "Lavoro dipendente"
    redditi = [d[k] for k in ("reddito_indeterminato", "reddito_determinato", "reddito_pensione") if d[k]]
    reddito = sum(redditi, Decimal(0)) if redditi else None
    d["reddito_totale"] = reddito
    if reddito is None:
        r.aggiungi("Reddito", Esito.ERRORE, "Redditi di lavoro dipendente/pensione non trovati")
        return r

    # --- Giorni ----------------------------------------------------------------------
    giorni_anno = 366 if anno and (anno % 4 == 0 and (anno % 100 != 0 or anno % 400 == 0)) else 365
    giorni = d["giorni_lavoro"] or d["giorni_pensione"]
    nome_giorni = "Giorni lavorati" if d["giorni_lavoro"] else "Giorni di pensione"
    if giorni is None:
        r.aggiungi(nome_giorni, Esito.ATTENZIONE, "Numero di giorni non trovato: uso l'anno intero")
        giorni = giorni_anno
    elif giorni > giorni_anno or giorni <= 0:
        r.aggiungi(nome_giorni, Esito.ERRORE, f"{giorni} giorni: impossibile (max {giorni_anno})")
        giorni = min(max(giorni, 1), giorni_anno)
    else:
        r.aggiungi(nome_giorni, Esito.OK, f"{giorni} giorni su {giorni_anno}")

    if d["reddito_pensione"] and not lavoro:
        r.aggiungi("Tipo di reddito", Esito.INFO, "CU di un pensionato (redditi di pensione)")

    if d["data_assunzione"] and anno:
        if d["data_assunzione"] > date(anno, 12, 31):
            r.aggiungi("Data inizio rapporto", Esito.ERRORE,
                       f"{d['data_assunzione']:%d/%m/%Y}: successiva all'anno certificato {anno}")
        elif d["data_assunzione"].year == anno and d["giorni_lavoro"]:
            massimo = (date(anno, 12, 31) - d["data_assunzione"]).days + 1
            if d["giorni_lavoro"] > massimo + 1:
                r.aggiungi("Data inizio rapporto", Esito.ERRORE,
                           f"Assunto il {d['data_assunzione']:%d/%m/%Y} ma con {d['giorni_lavoro']} giorni "
                           f"(massimo {massimo})")

    # --- IRPEF -----------------------------------------------------------------------
    rit = d["ritenute_irpef"]
    lorda = irpef_lorda(reddito, anno)
    d["irpef_lorda_teorica"] = lorda
    if rit is None:
        r.aggiungi("Ritenute IRPEF", Esito.ATTENZIONE, "Ritenute IRPEF non trovate")
    elif rit > reddito:
        r.aggiungi("Ritenute IRPEF", Esito.ERRORE, "Ritenute superiori al reddito")
    elif lorda is None:
        r.aggiungi("Ritenute IRPEF", Esito.INFO,
                   f"{formatta_euro(rit)} (scaglioni IRPEF {anno or '?'} non configurati: verifica non eseguita)")
    elif rit > lorda + 1:
        r.aggiungi("Ritenute IRPEF", Esito.ERRORE,
                   f"{formatta_euro(rit)} superiori all'IRPEF lorda massima {formatta_euro(lorda)} "
                   f"calcolata con gli scaglioni {anno}: impossibile")
    else:
        aliquota = (rit / reddito * 100).quantize(Decimal("0.1"))
        r.aggiungi("Ritenute IRPEF", Esito.OK,
                   f"{formatta_euro(rit)} (aliquota media {str(aliquota).replace('.', ',')}%), entro l'IRPEF lorda teorica "
                   f"{formatta_euro(lorda)}; differenza = detrazioni {formatta_euro(lorda - rit)}")

    # --- INPS --------------------------------------------------------------------------
    imp, contr = d["imponibile_previdenziale"], d["contributi_lavoratore"]
    if imp and contr:
        aliquota = (contr / imp * 100).quantize(Decimal("0.01"))
        vicina = min(ALIQUOTE_INPS, key=lambda a: abs(a - aliquota))
        if abs(vicina - aliquota) <= Decimal("0.15"):
            r.aggiungi("Contributi INPS", Esito.OK, f"{str(aliquota).replace('.', ',')}% dell'imponibile ({ALIQUOTE_INPS[vicina]})")
        else:
            r.aggiungi("Contributi INPS", Esito.ATTENZIONE,
                       f"Aliquota {aliquota}%: non standard (agevolazioni, fondi, o errore)")
        atteso = imp - contr
        diff = abs(atteso - reddito) / atteso if atteso else Decimal(1)
        if diff <= Decimal("0.05"):
            r.aggiungi("Reddito / imponibile INPS", Esito.OK,
                       f"Reddito {formatta_euro(reddito)} ≈ imponibile previdenziale − contributi "
                       f"{formatta_euro(atteso)}")
        else:
            r.aggiungi("Reddito / imponibile INPS", Esito.ATTENZIONE,
                       f"Reddito {formatta_euro(reddito)}, atteso circa {formatta_euro(atteso)} "
                       f"(scostamento {diff * 100:.0f}%: welfare, fringe benefit, fondi pensione o errore)")

    # --- Reddito mensile ---------------------------------------------------------------
    mesi = Decimal(giorni) / Decimal(giorni_anno) * 12
    imposte = (rit or 0) + sum((d[k] or 0) for k in ("addizionale_regionale", "addizionale_comunale_saldo",
                                                      "addizionale_comunale_acconto"))
    d["imposte_totali"] = imposte
    d["mesi_lavorati"] = str(mesi.quantize(Decimal("0.1"))).replace(".", ",")
    d["reddito_mensile_lordo"] = (reddito / mesi).quantize(Decimal("0.01"))
    d["reddito_mensile_netto"] = ((reddito - imposte) / mesi).quantize(Decimal("0.01"))
    r.aggiungi("Reddito mensile", Esito.INFO,
               f"Annuo {formatta_euro(reddito)} su {d['mesi_lavorati']} mesi → mensile "
               f"{formatta_euro(d['reddito_mensile_lordo'])} (netto ritenute e addizionali "
               f"{formatta_euro(d['reddito_mensile_netto'])}, su 12 mesi)")
    return r
