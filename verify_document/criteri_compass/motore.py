"""
VERIFICA PRATICA - Cessione del quinto e Delega - criteri Compass (tutti i settori)
--------------------------------------------------------------------
I calcoli (età, anzianità, montante, percentuali) sono fatti in modo esatto da Python
e confrontati con le regole nei file regole_*.py (uno per prodotto e settore), compagnia per compagnia.
L'AI serve solo, se richiesto, a riassumere il risultato.

ATTENZIONE: è una verifica INDICATIVA basata sui criteri del PDF. L'esito vincolante
resta quello del simulatore / della pre-accettazione Compass.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta


ORDINE = {"OK": 0, "VERIFICA": 1, "PREACC": 2, "KO": 3}
SIMBOLO = {"OK": "✅", "VERIFICA": "❔", "PREACC": "⚠️", "KO": "❌", "INFO": "ℹ️"}
ESITO = {"OK": "ASSUMIBILE", "VERIFICA": "DA VERIFICARE", "PREACC": "PRE-ACCETTAZIONE",
         "KO": "NON ASSUMIBILE"}


# ======================= DATE =======================
def aggiungi_mesi(d, n):
    m = d.month - 1 + n
    anno, mese = d.year + m // 12, m % 12 + 1
    return date(anno, mese, min(d.day, calendar.monthrange(anno, mese)[1]))


def aggiungi_amg(d, amg):
    a, m, g = amg
    return aggiungi_mesi(d, a * 12 + m) + timedelta(days=g)


def differenza_amg(da, a):
    """Anni, mesi, giorni trascorsi da 'da' ad 'a' (a >= da)."""
    anni, mesi, giorni = a.year - da.year, a.month - da.month, a.day - da.day
    if giorni < 0:
        mesi -= 1
        mese_prec = a.month - 1 or 12
        anno_prec = a.year if a.month > 1 else a.year - 1
        giorni += calendar.monthrange(anno_prec, mese_prec)[1]
    if mesi < 0:
        anni -= 1
        mesi += 12
    return (anni, mesi, giorni)


def mesi_tra(da, a):
    anni, mesi, _ = differenza_amg(da, a)
    return anni * 12 + mesi


def primo_giorno_oltre(inizio, limite):
    """Primo giorno in cui il tempo trascorso da 'inizio' supera il limite (a, m, g)."""
    return aggiungi_amg(inizio, limite) + timedelta(days=1)


def fmt_amg(amg):
    a, m, g = amg
    testo = f"{a} {'anno' if a == 1 else 'anni'}"
    if m:
        testo += f" {m} {'mese' if m == 1 else 'mesi'}"
    if g:
        testo += f" {g} {'giorno' if g == 1 else 'giorni'}"
    return testo



def _art(perc, prep="del"):
    """'dell'80%' ma 'del 70%' (e 'sull'80%' / 'sul 70%')."""
    elide = str(int(perc)).startswith("8") or int(perc) in (1, 11)
    return {"del": "dell'" if elide else "del ", "sul": "sull'" if elide else "sul "}[prep] + f"{perc:g}%"


def fmt_data(d):
    return d.strftime("%d/%m/%Y")


def euro(x):
    return f"€ {x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def leggi_data(testo, nome):
    testo = (testo or "").strip()
    for formato in ("%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(testo, formato).date()
        except ValueError:
            pass
    raise ValueError(f"{nome}: data non valida ('{testo}'). Usa il formato gg/mm/aaaa.")


def leggi_numero(testo, nome, obbligatorio=False):
    testo = (testo or "").strip().replace("€", "").replace(" ", "")
    if not testo:
        if obbligatorio:
            raise ValueError(f"{nome}: campo obbligatorio.")
        return 0.0
    if "," in testo:
        testo = testo.replace(".", "").replace(",", ".")
    try:
        return float(testo)
    except ValueError:
        raise ValueError(f"{nome}: numero non valido ('{testo}').")



# ======================= SETTORI E PRODOTTI =======================
from . import archivio_regole

# (prodotto, settore) -> file regole e motore da usare
SETTORI = {
    ("CQS", "Dipendente privato"):        {"regole": "regole_cqs_privati",        "motore": "standard"},
    ("CQS", "Privato NO TFR"):            {"regole": "regole_cqs_privati_no_tfr", "motore": "standard"},
    ("CQS", "Parapubblico"):              {"regole": "regole_cqs_parapubblici",   "motore": "standard"},
    ("CQS", "Statale / pubblico"):        {"regole": "regole_cqs_statali",        "motore": "statali"},
    ("CQS", "Medico convenzionato"):      {"regole": "regole_cqs_medici",         "motore": "standard"},
    ("CQS", "Pensionato"):                {"regole": "regole_cqs_pensionati",     "motore": "pensionati"},
    ("Delega", "Dipendente privato"):     {"regole": "regole_dlg_privati",        "motore": "standard"},
    ("Delega", "Parapubblico"):           {"regole": "regole_dlg_parapubblici",   "motore": "standard"},
    ("Delega", "Statale / pubblico"):     {"regole": "regole_dlg_statali",        "motore": "standard"},
    ("Delega", "Medico convenzionato"):   {"regole": "regole_dlg_medici",         "motore": "standard"},
}

# Compagnie selezionabili per la CQS in corso (serve per le deleghe)
COMPAGNIE_CQS = ["Nessuna CQS in corso", "NET", "CARDIF", "SOGECAP", "AMTRUST", "AXA", "METLIFE",
                 "GREAT_AMERICAN", "HDI", "Altra compagnia"]


# Righe della tabella "Valutazioni assicurazioni": una per compagnia / database
NOMI_DB = {
    "NET": "Net (GARF)",
    "CARDIF": "Cardif (DB Cardif)",
    "SOGECAP": "Sogecap (Ses@me)",
    "AMTRUST": "AmTrust (Quintohub)",
    "AXA": "AXA (Ses@me)",
    "METLIFE": "MetLife",
    "GREAT_AMERICAN": "Great American (All Risks)",
    "HDI": "HDI",
}
ESITI_DB = ["Non verificato", "Assumibile", "Non assumibile"]
CODICI_DB = {   # codici / categorie che compaiono nei criteri
    "NET": ["", "PRIME", "PRIME ESG", "Campagna Compass privati", "Altro"],
    "CARDIF": ["", "A", "B", "YOUNG", "Altro"],
}


def riga_db(codice_compagnia):
    """NET_PLUS, NET_YOUNG -> NET; CARDIF_YOUNG -> CARDIF."""
    return codice_compagnia.replace("_PLUS", "").replace("_YOUNG", "")


def righe_db(prodotto, settore):
    """Compagnie (righe DB) presenti nei criteri di questo prodotto/settore, in ordine."""
    righe = []
    for codice in carica_regole(prodotto, settore).COMPAGNIE:
        r = riga_db(codice)
        if r not in righe:
            righe.append(r)
    return righe


def _val(p, codice_compagnia):
    return p.valutazioni.get(riga_db(codice_compagnia), {})


# Cartella con le regole aggiornate (.json) condivise dall'ufficio: impostata dall'interfaccia
# (impostazione "cartella_condivisa"); None = solo le regole incluse nel programma.
CARTELLA_REGOLE = None


def carica_regole(prodotto, settore):
    """Regole del prodotto/settore: il .json della cartella condivisa se presente, altrimenti quelle incluse."""
    return archivio_regole.carica(SETTORI[(prodotto, settore)]["regole"], CARTELLA_REGOLE)


# ======================= DATI PRATICA =======================
@dataclass
class Pratica:
    sesso: str                      # "M" / "F"
    nascita: date
    assunzione: date
    netto: float                    # stipendio netto mensile (prima di cessioni/deleghe/pignoramenti)
    tfr: float                      # TFR maturato in azienda (0 se non serve / non disponibile)
    rata: float                     # rata RICHIESTA (della CQS o della delega, secondo il prodotto)
    durata: int                     # mesi
    decorrenza: date
    prodotto: str = "CQS"           # "CQS" / "Delega"
    settore: str = "Dipendente privato"
    anzianita_contributiva_mesi: int | None = None   # da estratto conto INPS, alla data di oggi
    dipendenti_azienda: int | None = None
    cooperativa: bool = False
    contratto: str = "Indeterminato"   # Indeterminato / Apprendistato / Somministrazione-interinale / Determinato
    part_time: str = "No"              # No / Orizzontale / Verticale / Misto
    part_time_perc: float = 0
    cig: str = "No"                    # No / Ordinaria / Straordinaria / Per maltempo
    cittadinanza: str = "Italiana"     # Italiana / UE / Extra-UE
    sospensione: bool = False          # aspettativa / sospensione / provvedimenti disciplinari
    scoring: float | None = None       # scoring azienda dal DB compagnia (es. 6 per 6/1)
    categoria_cardif: str = "B"        # parapubblici: categoria ATC nel DB Cardif (A / B)
    # valutazione dell'azienda sul DB di ogni assicurazione:
    # {"NET": {"esito": "Assumibile", "scoring": 6, "codice": "PRIME"}, "CARDIF": {...}, ...}
    valutazioni: dict = field(default_factory=dict)
    # pubblici
    militare: bool = False
    docente_neoassunto: bool = False
    ferroviere: bool = False
    carabiniere_ferma: bool = False    # carabiniere in "ferma quadriennale volontaria"
    # trattenute in corso
    rata_delega: float = 0             # deleghe / prestiti aziendali in corso
    residuo_delega: float = 0          # montante residuo della delega
    rata_pignoramento: float = 0
    residuo_pignoramento: float = 0
    pignoramento_alimenti: bool = False
    altre_trattenute: float = 0        # assicurazioni, alimenti, canone alloggio...
    # CQS in corso (per le deleghe)
    cqs_rata: float = 0
    cqs_residuo: float = 0
    cqs_compagnia: str = "Nessuna CQS in corso"
    cqs_compass: bool = True           # CQS stipulata da Compass
    oggi: date = field(default_factory=date.today)


@dataclass
class Esito:
    compagnia: str
    nome: str
    livello: str = "OK"
    motivi: list = field(default_factory=list)   # (livello, testo)

    def aggiungi(self, livello, testo):
        self.motivi.append((livello, testo))
        if livello in ORDINE and ORDINE[livello] > ORDINE[self.livello]:
            self.livello = livello


# ======================= PUNTO DI INGRESSO =======================
def verifica_pratica(p):
    """Sceglie il motore giusto in base a prodotto e settore."""
    info = SETTORI[(p.prodotto, p.settore)]
    regole = carica_regole(p.prodotto, p.settore)
    if info["motore"] == "statali":
        return verifica_statale(p, regole)
    return verifica(p, regole)


# ======================= CALCOLI COMUNI =======================
def _base(p, g):
    """Calcoli e requisiti generali comuni a tutti i settori dei dipendenti."""
    b = {}
    b["scadenza"] = aggiungi_mesi(p.decorrenza, p.durata) - timedelta(days=1)
    b["montante"] = p.rata * p.durata
    b["eta_oggi"] = differenza_amg(p.nascita, p.oggi)
    b["eta_decorrenza"] = differenza_amg(p.nascita, p.decorrenza)
    b["eta_scadenza"] = differenza_amg(p.nascita, b["scadenza"])
    b["anz_azienda"] = differenza_amg(p.assunzione, p.decorrenza)
    b["tfr_disp"] = p.tfr * (0.8 if p.rata_pignoramento > 0 else 1.0)   # con pignoramento: 4/5 del TFR
    b["inizio_contributi"] = None
    if p.anzianita_contributiva_mesi is not None:
        ic = aggiungi_mesi(p.oggi, -p.anzianita_contributiva_mesi)
        b["inizio_contributi"] = ic
        b["anz_contr_decorrenza"] = differenza_amg(ic, p.decorrenza)
        b["anz_contr_scadenza"] = differenza_amg(ic, b["scadenza"])
    else:
        b["anz_contr_decorrenza"] = b["anz_contr_scadenza"] = None

    b["e_delega"] = p.prodotto == "Delega"
    rata_cqs_in_corso = p.cqs_rata if b["e_delega"] else 0
    b["trattenute"] = p.rata + rata_cqs_in_corso + p.rata_delega + p.rata_pignoramento + p.altre_trattenute
    b["perc"] = b["trattenute"] / p.netto * 100 if p.netto else 0
    b["netto_residuo"] = p.netto - b["trattenute"]
    b["quinto"] = p.netto * g["rata_max_quota"]

    prodotto = "delega" if b["e_delega"] else "CQS"
    calcoli = [
        f"{p.prodotto} · {p.settore}" + (" · militare" if p.militare else "")
        + (" · docente neoassunto" if p.docente_neoassunto else "") + (" · ferroviere" if p.ferroviere else ""),
        f"Decorrenza {fmt_data(p.decorrenza)} → scadenza {fmt_data(b['scadenza'])} ({p.durata} mesi)",
        f"Età oggi: {fmt_amg(b['eta_oggi'])} · alla decorrenza: {fmt_amg(b['eta_decorrenza'])} · "
        f"a scadenza: {fmt_amg(b['eta_scadenza'])}",
        f"Anzianità presso l'azienda alla decorrenza: {fmt_amg(b['anz_azienda'])}",
    ]
    if b["inizio_contributi"]:
        calcoli.append(f"Anzianità contributiva alla decorrenza: {fmt_amg(b['anz_contr_decorrenza'])} · "
                       f"a scadenza: {fmt_amg(b['anz_contr_scadenza'])}")
    else:
        calcoli.append("Anzianità contributiva: non inserita (i limiti di anzianità non vengono verificati)")
    calcoli += [
        f"Montante {prodotto}: {euro(p.rata)} × {p.durata} = {euro(b['montante'])}",
        f"Quinto dello stipendio: {euro(b['quinto'])} (rata richiesta {euro(p.rata)})",
        f"Totale trattenute con la nuova {prodotto}: {euro(b['trattenute'])} = {b['perc']:.1f}% del netto · "
        f"netto residuo {euro(b['netto_residuo'])}",
    ]
    if p.tfr:
        calcoli.append(f"TFR: {euro(p.tfr)}" + (f" → disponibile 4/5 per pignoramento: {euro(b['tfr_disp'])}"
                                                if p.rata_pignoramento > 0 else "")
                       + f" · rapporto Montante/TFR = {b['montante'] / p.tfr:.2f}")
    if b["e_delega"] and p.cqs_rata:
        calcoli.append(f"CQS in corso: rata {euro(p.cqs_rata)}, montante residuo {euro(p.cqs_residuo)}, "
                       f"compagnia: {p.cqs_compagnia}")

    generali = []
    if p.rata > b["quinto"] + 0.005:
        generali.append(("KO", f"Rata {euro(p.rata)} superiore al quinto dello stipendio ({euro(b['quinto'])})."))
    if not g["durata_min"] <= p.durata <= g["durata_max"]:
        generali.append(("KO", f"Durata {p.durata} mesi fuori dai limiti ({g['durata_min']}-{g['durata_max']} mesi)."))
    if p.decorrenza < p.oggi:
        generali.append(("VERIFICA", "La decorrenza è nel passato: controlla la data."))
    if p.contratto == "Apprendistato":
        generali.append(("KO", "Contratto di apprendistato: escluso da tutte le compagnie."))
    if p.contratto == "Determinato":
        generali.append(("VERIFICA", "Contratto a tempo determinato: non previsto nei criteri, verificare con Compass."))
    if p.sospensione:
        generali.append(("KO", "Aspettativa / sospensione / provvedimenti disciplinari: esclusi."))
    if p.cig == "Straordinaria":
        generali.append(("KO", "Cassa integrazione straordinaria: non assumibile."))
    if p.carabiniere_ferma:
        generali.append(("KO", "Carabinieri in \"ferma quadriennale volontaria\": non assumibili."))
    if g.get("nota_settore"):
        generali.append(("INFO", g["nota_settore"]))
    if b["e_delega"]:
        ha_cqs = p.cqs_compagnia != "Nessuna CQS in corso" or p.cqs_rata > 0
        if g.get("cqs_obbligatoria") and not ha_cqs:
            generali.append(("KO", "Delega in assenza di CQS: non ammessa (serve una cessione del quinto in corso)."))
        if g.get("dipendenti_minimi"):
            if p.dipendenti_azienda is None:
                generali.append(("VERIFICA", f"Numero dipendenti non inserito: per la delega servono almeno "
                                             f"{g['dipendenti_minimi']} dipendenti."))
            elif p.dipendenti_azienda < g["dipendenti_minimi"]:
                generali.append(("KO", f"Azienda con {p.dipendenti_azienda} dipendenti: per la delega servono "
                                       f"almeno {g['dipendenti_minimi']}."))
    return b, calcoli, generali


def _anzianita_minima(p, c, e, b):
    mesi = c.get("anzianita_minima_mesi")
    if p.docente_neoassunto and c.get("anzianita_minima_docente_neo") is not None:
        mesi = c["anzianita_minima_docente_neo"]
    if mesi is None:
        return
    giorni = c.get("anzianita_minima_giorni_extra", 0)
    minimo = (mesi // 12, mesi % 12, giorni)
    if b["anz_azienda"] < minimo:
        testo = f"{mesi} mesi" + (f" e {giorni} giorno" if giorni else "")
        e.aggiungi("KO", f"Anzianità in azienda {fmt_amg(b['anz_azienda'])}: minimo {testo}"
                         + (" (docente neoassunto)" if p.docente_neoassunto else " e periodo di prova superato") + ".")


def _comuni_finali(p, c, e, b):
    """Controlli comuni: montante, quota, stipendio minimo, contratto, cittadinanza, documenti, note."""
    montante = b["montante"]
    # ---- montante massimo ----
    massimo = c.get("montante_massimo")
    if b["e_delega"] and c.get("montante_massimo_cqs_altra") is not None and not _cqs_stessa(p, e.compagnia):
        massimo = c["montante_massimo_cqs_altra"]
        e.aggiungi("INFO", f"CQS in corso non assicurata con questa compagnia: montante max {euro(massimo)}.")
    if c.get("sempre_preacc"):
        e.aggiungi("PREACC", c["sempre_preacc"])
    if massimo is not None and montante > massimo + 0.005:
        e.aggiungi("KO", f"Montante {euro(montante)} oltre il massimo di {euro(massimo)}.")
    elif c.get("montante_preacc_oltre") and montante > c["montante_preacc_oltre"]:
        e.aggiungi("PREACC", f"Montante {euro(montante)} oltre {euro(c['montante_preacc_oltre'])}: "
                             f"{c['nota_montante_preacc']}.")
    for soglia, testo in sorted(c.get("montante_preacc", []), reverse=True):
        if montante > soglia:
            e.aggiungi("PREACC", f"Montante {euro(montante)} oltre {euro(soglia)}: {testo}.")
            break
    if (p.rata_delega > 0 or (b["e_delega"] and p.cqs_rata > 0)) and c.get("cumulo"):
        e.aggiungi("INFO", f"Cumulo: {c['cumulo']}.")

    # ---- quota cedibile ridotta (es. quinto dell'80% dello stipendio) ----
    if c.get("quota_cedibile_perc"):
        limite = p.netto * c["quota_cedibile_perc"] / 100 / 5
        if p.rata > limite + 0.005:
            e.aggiungi("KO", f"Rata oltre il quinto {_art(c['quota_cedibile_perc'])} dello stipendio "
                             f"(max {euro(limite)}).")

    # ---- durata massima della compagnia ----
    durata_max = c.get("durata_max")
    regola = c.get("durata_max_se_anzianita_sotto")
    if regola and b["anz_azienda"] < regola[0]:
        durata_max = min(durata_max or 999, regola[1])
    if durata_max and p.durata > durata_max:
        e.aggiungi("KO", f"Durata {p.durata} mesi oltre il massimo di {durata_max} mesi per questa compagnia"
                         + (f" (anzianità sotto {fmt_amg(regola[0])})" if regola and durata_max == regola[1] else "")
                         + ".")

    # ---- stipendio minimo dopo le trattenute ----
    if c.get("stipendio_minimo") and b["netto_residuo"] < c["stipendio_minimo"]:
        e.aggiungi("KO", f"Netto residuo {euro(b['netto_residuo'])} sotto il minimo di {euro(c['stipendio_minimo'])}.")

    # ---- contratto, part-time, cassa integrazione ----
    if p.contratto == "Somministrazione-interinale":
        liv = c.get("interinale", "VERIFICA")
        testo = {"KO": "Somministrazione/interinale: escluso.",
                 "PREACC": "Lavoro interinale: valutabile in pre-accettazione se prevista indennità di "
                           "disponibilità mensile.",
                 "VERIFICA": "Lavoro interinale: verificare (spesso ammesso solo per i dipendenti diretti "
                             "dell'agenzia)."}.get(liv, "")
        e.aggiungi(liv, testo)
    if p.part_time != "No":
        pt = c.get("part_time", {"verticale": "OK", "misto": "VERIFICA", "orizzontale_min_perc": None})
        if p.part_time == "Orizzontale":
            if pt.get("orizzontale_min_perc") and p.part_time_perc < pt["orizzontale_min_perc"]:
                e.aggiungi("KO", f"Part-time orizzontale al {p.part_time_perc:.0f}%: minimo {pt['orizzontale_min_perc']}%.")
        else:
            liv = pt.get(p.part_time.lower(), "VERIFICA")
            if liv == "OK":
                e.aggiungi("INFO", f"Part-time {p.part_time.lower()}: ammesso con evidenza di continuità lavorativa "
                                   "per tutti i mesi dell'anno (anche da CUD).")
            else:
                e.aggiungi(liv, f"Part-time {p.part_time.lower()}: "
                                f"{'non ammesso' if liv == 'KO' else 'non previsto, verificare'}.")
    if p.cig in ("Ordinaria", "Per maltempo") and c.get("cig"):
        chiave = "ordinaria" if p.cig == "Ordinaria" else "maltempo"
        liv = c["cig"].get(chiave, "VERIFICA")
        nota = c.get("cig_ordinaria_nota", "") if chiave == "ordinaria" else ""
        testo = {"OK": "ammessa", "KO": "non assumibile", "PREACC": "valutabile in pre-accettazione",
                 "VERIFICA": "non prevista nei criteri, verificare"}[liv]
        e.aggiungi(liv if liv != "OK" else "INFO",
                   f"Cassa integrazione {p.cig.lower()}: {testo}" + (f" ({nota})." if nota else "."))

    # ---- cittadinanza ----
    if c.get("solo_cittadini_italiani") and p.cittadinanza != "Italiana":
        e.aggiungi("KO", "Ammessi solo cittadini italiani.")
    elif p.cittadinanza != "Italiana":
        e.aggiungi("VERIFICA", f"Cittadino {p.cittadinanza}: {c.get('cittadinanza', 'verificare i requisiti.')}")

    # ---- documenti e note ----
    _documenti(p, c, e, b["eta_decorrenza"], b["eta_scadenza"])
    if c.get("condizioni_azienda"):
        e.aggiungi("INFO", c["condizioni_azienda"])
    for nota in c.get("note", []):
        e.aggiungi("INFO", nota)
    if c.get("nota_extra"):
        e.aggiungi("INFO", c["nota_extra"])


def _valuta_db(p, c, e, b, g):
    """Esito, codice e scoring dell'azienda sul database della compagnia."""
    v = _val(p, e.compagnia)
    esito = v.get("esito", "Non verificato")
    if esito == "Non assumibile":
        if g.get("non_assumibile_preacc_1_1") and p.tfr and b["montante"] <= b["tfr_disp"] + 0.005:
            e.aggiungi("PREACC", "Azienda NON assumibile nel DB della compagnia: valutabile in pre-accettazione "
                                 "con rapporto TFR/Montante 1/1 (montante entro il TFR).")
        elif g.get("non_assumibile_preacc_1_1"):
            e.aggiungi("KO", "Azienda NON assumibile nel DB della compagnia (pre-accettazione solo con montante "
                             f"entro il TFR: {euro(b['tfr_disp'])}).")
        else:
            e.aggiungi("KO", "Azienda NON assumibile nel DB della compagnia.")
    elif esito == "Assumibile":
        dettagli = [x for x in (v.get("codice"), f"scoring {v['scoring']:g}/1" if v.get("scoring") else "") if x]
        e.aggiungi("INFO", "Azienda assumibile nel DB" + (f" ({', '.join(dettagli)})" if dettagli else "") + ".")

    ammessi = c.get("codici_ammessi")
    if ammessi:
        codice = v.get("codice") or ""
        if not codice:
            e.aggiungi("VERIFICA", f"Inserisci il codice/categoria del DB: ammessi solo {', '.join(ammessi)}.")
        elif codice not in ammessi:
            e.aggiungi("KO", f"Codice DB \"{codice}\" non ammesso: servono {', '.join(ammessi)}.")
    if c.get("scoring_minimo"):
        sc = v.get("scoring")
        if sc is None:
            e.aggiungi("VERIFICA", f"Inserisci lo scoring del DB: minimo {c['scoring_minimo']}/1.")
        elif sc < c["scoring_minimo"]:
            e.aggiungi("KO", f"Scoring {sc:g}/1 sotto il minimo di {c['scoring_minimo']}/1.")


def _cqs_stessa(p, codice):
    base = codice.replace("_PLUS", "")
    return p.cqs_compagnia == base


# ======================= MOTORE STANDARD =======================
def verifica(p: Pratica, regole=None):
    """Dipendenti privati, privati no TFR, parapubblici, medici e tutte le deleghe.
    Restituisce (calcoli, problemi_generali, esiti_per_compagnia)."""
    R_ = regole or carica_regole(p.prodotto, p.settore)
    g = R_.REQUISITI_GENERALI
    b, calcoli, generali = _base(p, g)

    esiti = []
    for codice, c in R_.COMPAGNIE.items():
        # Deleghe: alcune compagnie hanno una variante se la CQS è con un'altra compagnia (es. Net Delega Plus)
        if b["e_delega"]:
            stessa = _cqs_stessa(p, codice)
            if codice.endswith("_PLUS"):
                if stessa or p.cqs_compagnia == "Nessuna CQS in corso":
                    continue                       # la variante serve solo se la CQS è con un'altra compagnia
            elif c.get("variante_se_cqs_altra") and not stessa and p.cqs_compagnia != "Nessuna CQS in corso":
                continue                           # si usa la variante al posto di questa
        e = Esito(codice, c["nome"])
        for livello, testo in generali:
            if livello != "INFO":
                e.aggiungi(livello, testo)

        if b["e_delega"]:
            if c.get("solo_se_cqs_stessa") and not c.get("variante_se_cqs_altra") and not _cqs_stessa(p, codice):
                e.aggiungi("KO", "Delega possibile solo se la CQS in corso è assicurata con questa compagnia.")
            if c.get("cqs_stipulata_compass") and not p.cqs_compass:
                e.aggiungi("KO", "Delega possibile solo se la CQS in corso è stipulata da Compass.")

        _anzianita_minima(p, c, e, b)
        _valuta_db(p, c, e, b, g)
        if c.get("anzianita_massima_atc_decorrenza") and b["anz_azienda"] > c["anzianita_massima_atc_decorrenza"]:
            e.aggiungi("KO", f"Anzianità in azienda {fmt_amg(b['anz_azienda'])}: massimo "
                             f"{fmt_amg(c['anzianita_massima_atc_decorrenza'])} alla decorrenza.")
        if c.get("eta_massima_decorrenza") and b["eta_decorrenza"] > c["eta_massima_decorrenza"]:
            e.aggiungi("KO", f"Età alla decorrenza {fmt_amg(b['eta_decorrenza'])}: massimo "
                             f"{fmt_amg(c['eta_massima_decorrenza'])}.")

        # ---- età massima a scadenza (militari / durata 24) ----
        eta_max = c["eta_massima_scadenza"]
        if p.militare and c.get("eta_massima_scadenza_militari"):
            eta_max = c["eta_massima_scadenza_militari"]
        if p.durata == 24 and c.get("eta_massima_scadenza_durata24") and not p.militare:
            eta_max = c["eta_massima_scadenza_durata24"]
        date_limite = [("età", primo_giorno_oltre(p.nascita, eta_max), f"età max a scadenza {fmt_amg(eta_max)}")]

        # ---- anzianità contributiva massima e dato combinato ----
        ic = b["inizio_contributi"]
        if ic:
            anz_max = None
            if p.militare and c.get("anzianita_massima_militari"):
                anz_max = c["anzianita_massima_militari"]
            elif c.get("anzianita_massima"):
                anz_max = c["anzianita_massima"][p.sesso]
            if anz_max:
                date_limite.append(("anzianità", primo_giorno_oltre(ic, anz_max), f"anzianità max {fmt_amg(anz_max)}"))
            if c.get("anzianita_massima_adesione") and b["anz_contr_decorrenza"] > c["anzianita_massima_adesione"]:
                e.aggiungi("KO", f"Anzianità contributiva all'adesione {fmt_amg(b['anz_contr_decorrenza'])}: "
                                 f"massimo {fmt_amg(c['anzianita_massima_adesione'])}.")
            dc = c.get("dato_combinato_militari") if p.militare and c.get("dato_combinato_militari") \
                else c.get("dato_combinato")
            if dc:
                data = max(aggiungi_amg(p.nascita, (dc["eta"], 0, 0)), aggiungi_amg(ic, (dc["anzianita"], 0, 0)))
                date_limite.append(("dato combinato", data,
                                    f"dato combinato età ≥ {dc['eta']} e anzianità ≥ {dc['anzianita']}"))

        superati = [(n, d, t) for n, d, t in date_limite if d <= b["scadenza"]]
        if superati:
            if p.ferroviere and c.get("superamento_ferrovieri"):
                e.aggiungi("VERIFICA", c["superamento_ferrovieri"])
            else:
                _valuta_superamento(p, c, e, superati, b["scadenza"], b["eta_scadenza"], b["tfr_disp"],
                                    b["anz_contr_scadenza"])

        # ---- rapporto TFR / montante ----
        _valuta_tfr(p, c, e, b["montante"], b["tfr_disp"], b["anz_azienda"])

        # ---- coesistenze ----
        if b["e_delega"]:
            _valuta_coesistenze_delega(p, c, e, b["perc"])
        else:
            _valuta_coesistenze(p, c, e, b["perc"])

        _comuni_finali(p, c, e, b)
        esiti.append(e)

    esiti.sort(key=lambda x: ORDINE[x.livello])
    calcoli += [f"ℹ️ {t}" for l, t in generali if l == "INFO"]
    return calcoli, generali, esiti


def _valuta_superamento(p, c, e, superati, scadenza, eta_scadenza, tfr_disp, anz_contr_scadenza):
    descr = "; ".join(t for _, _, t in superati)
    data_limite = min(d for _, d, _ in superati)
    s = c["superamento"]

    if data_limite <= p.decorrenza:
        e.aggiungi("KO", f"Limiti già superati alla decorrenza ({descr}).")
        return
    if not s["ammesso"]:
        e.aggiungi("KO", f"Superati i limiti a scadenza ({descr}): superamento NON ammesso.")
        return

    rate_pagate = mesi_tra(p.decorrenza, data_limite)
    residuo = p.rata * max(0, p.durata - rate_pagate)
    intro = (f"Superati i limiti a scadenza ({descr}). Il limite si raggiunge il {fmt_data(data_limite)}, "
             f"dopo circa {rate_pagate} rate: montante residuo ~{euro(residuo)}.")

    if s.get("eta_assoluta") and eta_scadenza > s["eta_assoluta"]:
        e.aggiungi("KO", intro + f" Età a scadenza oltre il massimo assoluto di {fmt_amg(s['eta_assoluta'])}.")
        return
    if s.get("anzianita_assoluta") and anz_contr_scadenza and anz_contr_scadenza > s["anzianita_assoluta"]:
        e.aggiungi("KO", intro + f" Anzianità a scadenza oltre il massimo assoluto di {fmt_amg(s['anzianita_assoluta'])}.")
        return
    if s.get("eta_max_adesione") and differenza_amg(p.nascita, p.decorrenza) > s["eta_max_adesione"]:
        e.aggiungi("KO", intro + f" In caso di superamento l'età max all'adesione è {fmt_amg(s['eta_max_adesione'])}.")
        return
    if s.get("durata24_ammessa") is False and p.durata == 24:
        e.aggiungi("KO", intro + " Superamento non applicabile con durata 24 mesi.")
        return
    if s.get("coesistenze_ammesse") is False and (p.rata_pignoramento > 0 or p.rata_delega > 0):
        e.aggiungi("KO", intro + " Con superamento dei limiti le coesistenze non sono ammesse.")
        return
    if s.get("pignoramento_ammesso") is False and p.rata_pignoramento > 0:
        e.aggiungi("KO", intro + " Con superamento dei limiti il pignoramento in coesistenza non è ammesso.")
        return
    if s.get("preacc"):
        e.aggiungi("PREACC", intro + " " + s["nota"])
        return
    if s.get("tipo") == "quota":
        limite = p.netto / 5 * s["perc_quinto"] / 100
        if p.rata <= limite + 0.005:
            e.aggiungi("OK", intro + f" Ammesso: rata entro il {s['perc_quinto']}% del quinto ({euro(limite)}). "
                       + s["nota"])
        else:
            e.aggiungi("KO", intro + f" Superamento ammesso solo con rata ≤ {euro(limite)} "
                                     f"({s['perc_quinto']}% del quinto). " + s["nota"])
        return
    if not p.tfr:
        e.aggiungi("VERIFICA", intro + " TFR non inserito: impossibile verificare la copertura. " + s["nota"])
        return
    copertura = tfr_disp * s["quota_tfr"]
    if residuo <= copertura:
        e.aggiungi("OK", intro + f" Coperto dal TFR ({euro(copertura)}). " + s["nota"])
    else:
        e.aggiungi("KO", intro + f" Il TFR utilizzabile ({euro(copertura)}) non copre il residuo. " + s["nota"])


def _valuta_tfr(p, c, e, montante, tfr_disp, anz_azienda):
    t = c.get("tfr_montante")
    if not t:
        return
    # residuo da togliere: per la CQS la delega in corso, per la delega la CQS in corso
    residuo = p.cqs_residuo if p.prodotto == "Delega" else p.residuo_delega
    nome_residuo = "residuo CQS" if p.prodotto == "Delega" else "residuo delega"

    # soglia sotto cui il rapporto non è richiesto
    v = _val(p, e.compagnia)
    if v.get("esito") == "Non assumibile":
        return          # vale la regola dell'azienda non assumibile (vedi _valuta_db)
    scoring = v.get("scoring") or p.scoring
    categoria = v.get("codice") if v.get("codice") in ("A", "B") else p.categoria_cardif
    esente = t.get("esente_fino")
    if isinstance(esente, dict):
        esente = esente.get(categoria, min(esente.values()))
    if esente:
        ok = montante <= esente
        if ok and t.get("esente_durata_max") and p.durata > t["esente_durata_max"]:
            ok = False
        if ok and t.get("esente_no_extraue") and p.cittadinanza == "Extra-UE":
            ok = False
        if ok and t.get("esente_no_coesistenze") and (p.rata_delega or p.rata_pignoramento):
            ok = False
        if ok and t.get("esente_anzianita_min_mesi") and mesi_tra(p.assunzione, p.decorrenza) < t["esente_anzianita_min_mesi"]:
            ok = False
        if ok:
            e.aggiungi("INFO", f"Rapporto TFR/montante non richiesto (montante fino a {euro(esente)}).")
            return

    if p.tfr <= 0:
        e.aggiungi("VERIFICA", "TFR non inserito: rapporto TFR/montante non verificato.")
        return

    if t["tipo"] in ("fisso", "cardif_categoria"):
        k = t["moltiplicatore"]
        fonte = f"rapporto TFR/montante 1/{k:g}" + (f" (ATC categoria {categoria})"
                                                     if t["tipo"] == "cardif_categoria" else "")
    elif t["tipo"] == "hdi":
        dip = p.dipendenti_azienda
        if dip is None:
            e.aggiungi("VERIFICA", "Numero dipendenti azienda non inserito (HDI: minimo 50, coop 200).")
            return
        soglia_min, soglia_grande = (200, 500) if p.cooperativa else (50, 150)
        if dip < soglia_min:
            e.aggiungi("KO", f"Azienda con {dip} {'soci' if p.cooperativa else 'dipendenti'}: HDI richiede almeno {soglia_min}.")
            return
        lunga = anz_azienda >= (6, 0, 0)
        k = (5 if lunga else 3) if dip >= soglia_grande else (4 if lunga else 2)
        fonte = f"rapporto TFR/montante 1/{k} (azienda {dip} {'soci' if p.cooperativa else 'dip.'}, " \
                f"anzianità {'≥ 6 anni' if lunga else 'fino a 5 anni e 11 mesi'})"
    else:  # scoring
        if not scoring:
            e.aggiungi("VERIFICA", f"Scoring azienda da inserire (DB {t['db']}"
                                   + (f", max {t['scoring_max']}/1" if t.get("scoring_max") else "") + ")"
                                   + f": serve montante ≤ TFR × scoring" + (f" − {nome_residuo}" if residuo else "") + ".")
            return
        k = min(scoring, t["scoring_max"]) if t.get("scoring_max") else scoring
        fonte = f"scoring {k:g}/1 (DB {t['db']})"

    capacita = tfr_disp * k - residuo
    dettaglio = f"{fonte}: capacità {euro(capacita)}" + (f" (al netto del {nome_residuo} {euro(residuo)})" if residuo else "")
    if montante <= capacita:
        e.aggiungi("INFO", f"TFR/montante OK — {dettaglio}.")
    elif t.get("preacc_fino") and montante <= t["preacc_fino"]:
        e.aggiungi("PREACC", f"Rapporto TFR/montante non rispettato ({dettaglio}): fino a {euro(t['preacc_fino'])} "
                             f"valutabile in pre-accettazione.")
    else:
        e.aggiungi("KO", f"Montante {euro(montante)} oltre la capacità TFR — {dettaglio}.")


def _valuta_coesistenze(p, c, e, perc):
    co = c.get("coesistenze", {})
    ha_dlg = p.rata_delega > 0
    ha_pign = p.rata_pignoramento > 0
    if not (ha_dlg or ha_pign):
        return
    if co.get("senza_limiti"):
        e.aggiungi("INFO", f"Coesistenze ammesse senza limiti percentuali ({perc:.1f}% dello stipendio).")
        return
    if ha_dlg and ha_pign:
        limite, nome = co.get("dlg_pign"), "CQS + delega + pignoramento"
    elif ha_dlg:
        limite, nome = co.get("dlg"), "CQS + delega/prestito aziendale"
    else:
        limite, nome = co.get("pign"), "CQS + pignoramento"

    if ha_pign and co.get("pign_residuo_max") and p.residuo_pignoramento > co["pign_residuo_max"]:
        e.aggiungi("KO", f"Residuo pignoramento {euro(p.residuo_pignoramento)} oltre {euro(co['pign_residuo_max'])}: "
                         f"non assumibile.")
    if limite == 0:
        e.aggiungi("KO", f"{nome}: coesistenza non ammessa.")
    elif limite is None:
        if ha_dlg and ha_pign:
            e.aggiungi("PREACC", f"{nome}: valutabile in pre-accettazione ({perc:.1f}% dello stipendio).")
        else:
            e.aggiungi("INFO", f"{nome}: nessun limite percentuale previsto ({perc:.1f}%).")
    elif perc <= limite + 0.005:
        e.aggiungi("INFO", f"{nome}: {perc:.1f}% dello stipendio, entro il limite del {limite}%.")
    elif co.get("preacc_fino") and perc <= co["preacc_fino"] + 0.005 and \
            (not co.get("preacc_solo_con_altre") or p.altre_trattenute > 0):
        e.aggiungi("PREACC", f"{nome}: {perc:.1f}% (oltre {limite}%, fino al {co['preacc_fino']}% valutabile in "
                             f"pre-accettazione).")
    else:
        e.aggiungi("KO", f"{nome}: {perc:.1f}% dello stipendio, oltre il limite del {limite}%.")


def _valuta_coesistenze_delega(p, c, e, perc):
    co = c.get("coesistenze", {})
    ha_cqs = p.cqs_rata > 0 or p.cqs_compagnia != "Nessuna CQS in corso"
    ha_pign = p.rata_pignoramento > 0
    if co.get("nessuna"):
        if ha_cqs or ha_pign or p.rata_delega > 0:
            e.aggiungi("KO", "Coesistenze non ammesse (nessuna CQS, delega o pignoramento in corso).")
        return
    if co.get("senza_limiti"):
        e.aggiungi("INFO", f"DLG + CQS / pignoramento: nessun limite percentuale ({perc:.1f}% dello stipendio).")
        return
    if ha_pign:
        limite = co.get("dlg_cqs_pign")
        nome = "DLG + CQS + pignoramento"
        if limite == 0:
            if co.get("pign_alimenti_preacc") and p.pignoramento_alimenti:
                e.aggiungi("PREACC", f"{nome} per alimenti: valutabile in pre-accettazione ({perc:.1f}%).")
            else:
                e.aggiungi("KO", f"{nome}: non ammesso" + (f" ({co['nota_pign']})" if co.get("nota_pign") else "") + ".")
            return
        if limite is None:
            e.aggiungi("PREACC", f"{nome}: da valutare in pre-accettazione ({perc:.1f}% dello stipendio).")
            return
    else:
        limite, nome = co.get("dlg_cqs"), "DLG + CQS"
    if limite is None:
        return
    if perc <= limite + 0.005:
        e.aggiungi("INFO", f"{nome}: {perc:.1f}% dello stipendio, entro il limite del {limite}%.")
    elif co.get("preacc_fino") and perc <= co["preacc_fino"] + 0.005:
        e.aggiungi("PREACC", f"{nome}: {perc:.1f}% (oltre {limite}%, fino al {co['preacc_fino']}% valutabile in "
                             f"pre-accettazione).")
    else:
        e.aggiungi("KO", f"{nome}: {perc:.1f}% dello stipendio, oltre il limite del {limite}%.")


def _documenti(p, c, e, eta_decorrenza, eta_scadenza):
    richiesto = False
    if c.get("inps_sempre") or (p.militare and c.get("inps_militari_sempre")):
        richiesto = True
    elif p.militare and c.get("inps_militari_se_eta_scadenza"):
        richiesto = eta_scadenza >= (c["inps_militari_se_eta_scadenza"][1], 0, 0)
    elif c.get("inps_se_eta_inizio"):
        op, soglia = c["inps_se_eta_inizio"]
        richiesto = eta_decorrenza >= (soglia, 0, 0) if op == ">=" else eta_decorrenza > (soglia, 0, 0)
    elif c.get("inps_se_eta_scadenza"):
        richiesto = eta_scadenza >= (c["inps_se_eta_scadenza"][1], 0, 0)
    if richiesto:
        e.aggiungi("INFO", "Richiesto estratto conto contributivo INPS.")


# ======================= MOTORE STATALI / PUBBLICI (CQS) =======================
def verifica_statale(p: Pratica, regole=None):
    R_ = regole or carica_regole("CQS", "Statale / pubblico")
    g = R_.REQUISITI_GENERALI
    b, calcoli, generali = _base(p, g)
    calcoli.append("Rapporto TFR/montante: non richiesto per i dipendenti statali/pubblici.")
    generali.append(("INFO", R_.NOTA_STANDARD))
    quinto = p.netto / 5
    coesistenze = sum(1 for x in (p.rata_delega, p.rata_pignoramento) if x > 0)

    esiti = []
    for codice, c in R_.COMPAGNIE.items():
        e = Esito(codice, c["nome"])
        for livello, testo in generali:
            if livello != "INFO":
                e.aggiungi(livello, testo)
        _anzianita_minima(p, c, e, b)
        _valuta_db(p, c, e, b, g)

        # ---- età all'adesione ed età massima a scadenza ----
        if c.get("eta_massima_adesione") and b["eta_decorrenza"] > c["eta_massima_adesione"]:
            e.aggiungi("KO", f"Età all'adesione {fmt_amg(b['eta_decorrenza'])}: massimo "
                             f"{fmt_amg(c['eta_massima_adesione'])}.")
        if p.ferroviere and c.get("eta_massima_scadenza_ferrovieri"):
            eta_max = c["eta_massima_scadenza_ferrovieri"]
        elif p.militare:
            eta_max = c["eta_massima_scadenza_militari"]
        else:
            eta_max = c["eta_massima_scadenza"]
        if b["eta_scadenza"] > eta_max:
            if p.militare and c.get("superamento_eta_militari") == "PREACC":
                e.aggiungi("PREACC", f"Età a scadenza {fmt_amg(b['eta_scadenza'])} oltre {fmt_amg(eta_max)}: "
                                     f"superamento (solo militari) valutabile in pre-accettazione.")
            elif p.ferroviere and codice == "HDI":
                e.aggiungi("VERIFICA", f"Ferroviere: età a scadenza oltre {fmt_amg(eta_max)}. Superamento ammesso "
                                       f"(max 75) se il TFR copre il debito residuo all'età pensionabile.")
            else:
                limite = primo_giorno_oltre(p.nascita, eta_max)
                mesi_max = mesi_tra(p.decorrenza, limite) if limite > p.decorrenza else 0
                e.aggiungi("KO", f"Età a scadenza {fmt_amg(b['eta_scadenza'])}: massimo {fmt_amg(eta_max)}"
                                 + (" (militari)" if p.militare else "")
                                 + (f". Durata massima possibile: {mesi_max} mesi." if mesi_max >= 24 else "."))

        # ---- limiti pensionistici ----
        lp = c.get("limiti_pensione", {})
        date_lim = []
        ic = b["inizio_contributi"]
        if lp.get("eta") and not p.militare:
            date_lim.append((primo_giorno_oltre(p.nascita, lp["eta"]), f"età {fmt_amg(lp['eta'])}"))
        if ic:
            if p.militare and lp.get("anzianita_militari"):
                date_lim.append((primo_giorno_oltre(ic, lp["anzianita_militari"]),
                                 f"anzianità militari {fmt_amg(lp['anzianita_militari'])}"))
            elif p.ferroviere and lp.get("anzianita_ferrovieri"):
                a = lp["anzianita_ferrovieri"][p.sesso]
                date_lim.append((primo_giorno_oltre(ic, a), f"anzianità ferrovieri {fmt_amg(a)}"))
            elif not p.militare and lp.get("anzianita"):
                a = lp["anzianita"][p.sesso]
                date_lim.append((primo_giorno_oltre(ic, a), f"anzianità {fmt_amg(a)}"))
            if p.militare and lp.get("dato_combinato_militari"):
                eta_dc, anz_dc = lp["dato_combinato_militari"]
                date_lim.append((max(aggiungi_amg(p.nascita, (eta_dc, 0, 0)), aggiungi_amg(ic, (anz_dc, 0, 0))),
                                 f"dato combinato militari età ≥ {eta_dc} e anzianità ≥ {anz_dc}"))
            if c.get("anzianita_massima_adesione") and b["anz_contr_decorrenza"] > c["anzianita_massima_adesione"]:
                e.aggiungi("KO", f"Anzianità all'adesione {fmt_amg(b['anz_contr_decorrenza'])}: massimo "
                                 f"{fmt_amg(c['anzianita_massima_adesione'])}.")
        elif lp.get("anzianita") or lp.get("anzianita_militari"):
            e.aggiungi("VERIFICA", "Anzianità contributiva non inserita: limiti pensionistici di anzianità non verificati.")
        if lp.get("formula_cardif"):
            eta_ingresso = b["eta_decorrenza"][0] + b["eta_decorrenza"][1] / 12
            base = 60 if p.militare else 65
            if eta_ingresso + p.durata / 12 - base >= 3:
                date_lim.append((p.decorrenza, f"[età ingresso + durata − {base}] ≥ 3"))

        superati = [(d, t) for d, t in date_lim if d <= b["scadenza"]]
        if superati:
            d_lim = min(d for d, _ in superati)
            descr = "; ".join(t for _, t in superati)
            if d_lim <= p.decorrenza and c.get("alla_decorrenza") == "KO":
                e.aggiungi("KO", f"Limiti pensionistici già raggiunti alla decorrenza ({descr}).")
            else:
                entro3 = d_lim < aggiungi_mesi(p.decorrenza, 36)
                _azione_statali(p, e, c["durante"], f"Limiti pensionistici raggiunti il {fmt_data(max(d_lim, p.decorrenza))} "
                                                    f"({descr})", quinto, coesistenze, entro3)

        # Great American: dato combinato con codice STANDARD/SENIOR nei primi 3 anni
        dcg = c.get("dato_combinato_ga")
        if dcg and ic:
            eta_dc, anz_dc = dcg["militari"] if p.militare else dcg["civili"]
            d = max(aggiungi_amg(p.nascita, (eta_dc, 0, 0)), aggiungi_amg(ic, (anz_dc, 0, 0)))
            if d < aggiungi_mesi(p.decorrenza, 36):
                _azione_statali(p, e, {"azione": "standard_entro_3", "perc": dcg["perc"]},
                                f"Dato combinato (età ≥ {eta_dc} e anzianità ≥ {anz_dc}) raggiunto entro i primi 3 anni",
                                quinto, coesistenze, True)

        # ---- soglie di età a scadenza (SENIOR / quinto ridotto) ----
        for s in c.get("soglie_eta_scadenza", []):
            soglia = s.get("oltre_militari") if p.militare and s.get("oltre_militari") else s["oltre"]
            if b["eta_scadenza"] > soglia:
                _azione_statali(p, e, s, f"Età a scadenza oltre {fmt_amg(soglia)}", quinto, coesistenze, True)

        if c.get("senior_una_coesistenza") and coesistenze > 1:
            e.aggiungi("INFO", "Con codice prodotto SENIOR è ammessa una sola coesistenza.")

        # ---- part-time specifico (Great American) ----
        _valuta_coesistenze(p, c, e, b["perc"])
        _comuni_finali(p, c, e, b)
        esiti.append(e)

    esiti.sort(key=lambda x: ORDINE[x.livello])
    calcoli += [f"ℹ️ {t}" for l, t in generali if l == "INFO"]
    return calcoli, generali, esiti


def _azione_statali(p, e, regola, motivo, quinto, coesistenze, entro3):
    azione = regola["azione"]
    if azione == "senior":
        e.aggiungi("INFO", f"{motivo}: con rata pari al V° pieno o con coesistenze serve il codice prodotto SENIOR.")
    elif azione == "quota":
        limite = quinto * regola["perc"] / 100
        if p.rata > limite + 0.005:
            e.aggiungi("KO", f"{motivo}: il V° va calcolato {_art(regola['perc'], 'sul')} dello stipendio, rata max "
                             f"{euro(limite)}.")
        else:
            e.aggiungi("INFO", f"{motivo}: rata entro il V° {_art(regola['perc'])} dello stipendio ({euro(limite)}).")
    elif azione == "cardif15":
        limite = p.netto * 0.15
        altre = p.rata_delega + p.rata_pignoramento + p.altre_trattenute
        if p.rata > limite + 0.005 or altre > 0:
            e.aggiungi("KO", f"{motivo}: ammesso solo con quota ≤ 15% dello stipendio (max {euro(limite)}) e "
                             f"nessun'altra trattenuta oltre alla cessione.")
        else:
            e.aggiungi("INFO", f"{motivo}: ammesso (quota ≤ 15% e nessun'altra trattenuta). I finanziamenti pregressi "
                               f"vanno estinti entro la data del pensionamento.")
    elif azione in ("standard_entro_3", "standard_soglia"):
        if azione == "standard_entro_3" and not entro3:
            return
        limite = quinto * regola["perc"] / 100
        if p.rata <= limite + 0.005 and coesistenze == 0:
            e.aggiungi("INFO", f"{motivo}: codice prodotto STANDARD possibile (rata entro il V° del "
                               f"{regola['perc']}%: {euro(limite)}).")
        else:
            e.aggiungi("INFO", f"{motivo}: codice prodotto SENIOR (STANDARD solo con rata ≤ {euro(limite)}, V° del "
                               f"{regola['perc']}%, e senza coesistenze).")
    elif azione == "ko":
        e.aggiungi("KO", f"{motivo}: non assumibile.")


def testo_risultato(calcoli, generali, esiti):
    righe = ["CALCOLI"] + [f"  • {c}" for c in calcoli] + [""]
    ok = [e.nome for e in esiti if e.livello == "OK"]
    pre = [e.nome for e in esiti if e.livello == "PREACC"]
    ver = [e.nome for e in esiti if e.livello == "VERIFICA"]
    righe.append("RIEPILOGO")
    righe.append(f"  ✅ Assumibile con: {', '.join(ok) if ok else 'nessuna compagnia'}")
    if pre:
        righe.append(f"  ⚠️ Pre-accettazione: {', '.join(pre)}")
    if ver:
        righe.append(f"  ❔ Da verificare (dati mancanti o casi non previsti): {', '.join(ver)}")
    righe.append("")
    for e in esiti:
        righe.append(f"{SIMBOLO[e.livello]} {e.nome} — {ESITO[e.livello]}")
        visti = set()
        for livello, testo in e.motivi:
            if testo in visti:
                continue
            visti.add(testo)
            righe.append(f"     {SIMBOLO.get(livello, '•')} {testo}")
        righe.append("")
    righe.append("Verifica indicativa basata sui Criteri Assuntivi Compass 07/2026. "
                 "L'esito vincolante è quello del simulatore / pre-accettazione Compass.")
    return "\n".join(righe)



# =====================================================================
#                              PENSIONATI
# =====================================================================


@dataclass
class PraticaPensionato:
    nascita: date
    pensione_netta: float           # pensione netta mensile
    quota_cedibile: float           # dalla Comunicazione di quota cedibile dell'Ente
    rata: float
    durata: int
    decorrenza: date
    altre_trattenute: float = 0     # altre trattenute già presenti sulla pensione
    invalidita: str = "Nessuna"     # Nessuna / Invalido / Sordomuto
    residenza: str = "Italia"       # Italia / UE / Regno Unito / Tunisia / Portogallo / Altro
    buono_stato_salute: bool = True # può firmare la Dichiarazione di Buono Stato di Salute
    oggi: date = field(default_factory=date.today)


def verifica_pensionato(p: PraticaPensionato):
    RP = carica_regole("CQS", "Pensionato")
    g = RP.REQUISITI_GENERALI
    calcoli, generali = [], []

    scadenza = aggiungi_mesi(p.decorrenza, p.durata) - timedelta(days=1)
    montante = p.rata * p.durata
    eta_oggi = differenza_amg(p.nascita, p.oggi)
    eta_decorrenza = differenza_amg(p.nascita, p.decorrenza)
    eta_scadenza = differenza_amg(p.nascita, scadenza)
    residuo = p.pensione_netta - p.rata - p.altre_trattenute

    calcoli += [
        f"Decorrenza {fmt_data(p.decorrenza)} → scadenza {fmt_data(scadenza)} ({p.durata} mesi)",
        f"Età oggi: {fmt_amg(eta_oggi)} · alla decorrenza: {fmt_amg(eta_decorrenza)} · "
        f"a scadenza: {fmt_amg(eta_scadenza)}",
        f"Montante: {euro(p.rata)} × {p.durata} = {euro(montante)}",
        f"Quota cedibile (comunicazione Ente): {euro(p.quota_cedibile)} · rata richiesta {euro(p.rata)}",
        f"Pensione residua dopo le trattenute: {euro(residuo)} "
        f"(minimo di salvaguardia {euro(g['pensione_minima_salvaguardia'])})",
    ]

    # ---- requisiti generali ----
    if eta_oggi < g["eta_minima_caricamento"]:
        generali.append(("KO", f"Età {fmt_amg(eta_oggi)}: servono almeno 40 anni compiuti al caricamento."))
    if p.rata < g["rata_minima"]:
        generali.append(("KO", f"Rata {euro(p.rata)} sotto il minimo di {euro(g['rata_minima'])}."))
    if p.quota_cedibile <= 0:
        generali.append(("VERIFICA", "Quota cedibile non inserita: serve la Comunicazione di quota cedibile "
                                     "dell'Ente pensionistico."))
    elif p.rata > p.quota_cedibile + 0.005:
        generali.append(("KO", f"Rata {euro(p.rata)} oltre la quota cedibile comunicata dall'Ente "
                               f"({euro(p.quota_cedibile)})."))
    if residuo < g["pensione_minima_salvaguardia"]:
        generali.append(("KO", f"Pensione residua {euro(residuo)} sotto la pensione minima di salvaguardia "
                               f"({euro(g['pensione_minima_salvaguardia'])})."))
    if not g["durata_min"] <= p.durata <= g["durata_max"]:
        generali.append(("KO", f"Durata {p.durata} mesi fuori dai limiti "
                               f"({g['durata_min']}-{g['durata_max']} mesi)."))
    if p.decorrenza < p.oggi:
        generali.append(("VERIFICA", "La decorrenza è nel passato: controlla la data."))

    esiti = []
    for codice, c in RP.COMPAGNIE.items():
        e = Esito(codice, c["nome"])
        for livello, testo in generali:
            if livello != "INFO":
                e.aggiungi(livello, testo)

        if c["eta_minima_ingresso"] and eta_decorrenza < c["eta_minima_ingresso"]:
            e.aggiungi("KO", f"Età all'ingresso {fmt_amg(eta_decorrenza)}: minimo "
                             f"{fmt_amg(c['eta_minima_ingresso'])}.")
        if eta_scadenza > c["eta_massima_scadenza"]:
            # durata massima possibile con questa compagnia
            limite = aggiungi_amg(p.nascita, c["eta_massima_scadenza"]) + timedelta(days=1)
            mesi_max = mesi_tra(p.decorrenza, limite) if limite > p.decorrenza else 0
            suggerimento = (f" Durata massima possibile: {mesi_max} mesi." if mesi_max >= g["durata_min"]
                            else "")
            e.aggiungi("KO", f"Età a scadenza {fmt_amg(eta_scadenza)}: massimo "
                             f"{fmt_amg(c['eta_massima_scadenza'])}.{suggerimento}")

        if montante > c["montante_massimo"]:
            e.aggiungi("KO", f"Montante {euro(montante)} oltre il massimo di {euro(c['montante_massimo'])}.")
        elif c["montante_preacc_oltre"] and montante > c["montante_preacc_oltre"]:
            e.aggiungi("PREACC", f"Montante {euro(montante)} oltre {euro(c['montante_preacc_oltre'])}: "
                                 f"{c['nota_montante_preacc']}.")

        if p.invalidita != "Nessuna":
            livello, testo = c["invalido" if p.invalidita == "Invalido" else "sordomuto"]
            e.aggiungi(livello if livello != "OK" else "INFO", f"{p.invalidita}: {testo}.")

        if p.residenza != "Italia":
            livello = c["estero"].get(p.residenza, "KO")
            if livello == "KO":
                e.aggiungi("KO", f"Residente all'estero ({p.residenza}): non ammesso.")
            else:
                e.aggiungi(livello, f"Residente all'estero ({p.residenza}): {c.get('nota_estero', '')}.")
                if p.residenza == "Portogallo" and c.get("decurtazione_portogallo"):
                    quota = p.quota_cedibile * (1 - c["decurtazione_portogallo"])
                    if p.rata > quota + 0.005:
                        e.aggiungi("KO", f"Portogallo: quota cedibile ridotta a {euro(quota)}, "
                                         f"inferiore alla rata.")

        if not p.buono_stato_salute:
            livello, testo = c["senza_buono_stato_salute"]
            e.aggiungi(livello, f"Non può firmare la Dichiarazione di Buono Stato di Salute: {testo}.")

        if not c["teleunderwriting"]:
            e.aggiungi("INFO", "Processo di teleunderwriting non previsto.")
        e.aggiungi("INFO", f"Documento per verifica tipologia pensione: cedolino, Obis-m o CUD. "
                           f"Validità documentazione medica: {c['validita_doc_medica_giorni']} giorni.")
        esiti.append(e)

    esiti.sort(key=lambda x: ORDINE[x.livello])
    return calcoli, generali, esiti
