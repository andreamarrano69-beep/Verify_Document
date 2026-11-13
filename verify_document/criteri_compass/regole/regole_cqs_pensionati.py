"""
REGOLE COMPASS - CESSIONE DEL QUINTO DELLA PENSIONE - PENSIONATI
Fonte: "Criteri Assuntivi Pensionati" 07/2026 (2 pagine)

Quando Compass aggiorna i criteri, basta cambiare i numeri qui sotto.
Età scritte come (anni, mesi, giorni), importi in euro.
"""

REQUISITI_GENERALI = {
    "eta_minima_caricamento": (40, 0, 0),   # 40 anni compiuti al caricamento
    "pensione_minima_salvaguardia": 611.85, # pensione minima INPS 2026: deve restare dopo le trattenute
    "rata_minima": 50.0,
    "durata_min": 24,
    "durata_max": 120,
    # quota cedibile massima: quella indicata nella Comunicazione di quota cedibile dell'Ente
    # non è possibile istruire deleghe di pagamento per i pensionati
}

# Livelli: "OK", "PREACC" (pre-accettazione), "KO", "VERIFICA"
COMPAGNIE = {
    "NET": {
        "nome": "Net Insurance",
        "teleunderwriting": True,
        "eta_minima_ingresso": None,
        "eta_massima_scadenza": (87, 5, 29),            # 87 anni
        "montante_massimo": 100000,
        "montante_preacc_oltre": 80000,                 # > 80.000: pre-acc + intervista telefonica + esami
        "nota_montante_preacc": "pre-accettazione + modulo adesione con intervista telefonica + esami "
                                "medici (urine, sangue, emocromo, glicemia, transaminasi, lipidi, PSA, "
                                "bilirubina, VES, elettroforesi, HIV)",
        "invalido": ("OK", "ammesso con verbale d'invalidità e/o inabilità"),
        "sordomuto": ("OK", "non occorre pre-accettazione, polizza con verbale d'invalidità"),
        "estero": {"UE": "KO", "Regno Unito": "KO", "Tunisia": "KO", "Portogallo": "KO", "Altro": "KO"},
        "senza_buono_stato_salute": ("VERIFICA", "documentazione medica non prevista: verificare"),
        "validita_doc_medica_giorni": 30,
    },
    "METLIFE": {
        "nome": "MetLife",
        "teleunderwriting": True,
        "eta_minima_ingresso": (45, 0, 0),
        "eta_massima_scadenza": (88, 5, 29),            # 88 anni
        "montante_massimo": 100000,
        "montante_preacc_oltre": None,
        "invalido": ("PREACC", "pre-accettazione + RVM + RVM additional e verbale di prima istanza"),
        "sordomuto": ("PREACC", "pre-accettazione + RVM"),
        "estero": {"UE": "KO", "Regno Unito": "KO", "Tunisia": "KO", "Portogallo": "KO", "Altro": "KO"},
        "senza_buono_stato_salute": ("PREACC", "RVM + pre-accettazione"),
        "validita_doc_medica_giorni": 180,
    },
    "SOGECAP": {
        "nome": "Sogecap (Société Générale)",
        "teleunderwriting": True,
        "eta_minima_ingresso": (55, 0, 0),
        "eta_massima_scadenza": (88, 6, 1),             # 88 anni, "da intendersi 88a 6m 1g"
        "montante_massimo": 75000,
        "montante_preacc_oltre": None,
        "invalido": ("OK", "verbale di prima istanza d'invalidità e Obis-m (in assenza: documento del "
                           "medico curante con tipologia, % e data dell'insorgenza)"),
        "sordomuto": ("PREACC", "pre-accettazione + RVM timbrato e firmato dal medico"),
        "estero": {"UE": "PREACC", "Regno Unito": "PREACC", "Tunisia": "PREACC",
                   "Portogallo": "PREACC", "Altro": "KO"},
        "nota_estero": "valutabile in richiesta polizza con: pensione erogata da INPS/Ente italiano, quota "
                       "cedibile, cedolino, ultimo CUD, Obis-M (Regno Unito: serve iscrizione AIRE)",
        "senza_buono_stato_salute": ("VERIFICA", "documentazione medica non prevista: verificare"),
        "validita_doc_medica_giorni": 180,
    },
    "AXA": {
        "nome": "AXA",
        "teleunderwriting": True,
        "eta_minima_ingresso": None,
        "eta_massima_scadenza": (85, 11, 29),           # 86 anni non compiuti
        "montante_massimo": 75000,
        "montante_preacc_oltre": None,
        "invalido": ("OK", "verbale di prima istanza d'invalidità e Obis-m (in assenza: documento del "
                           "medico curante con tipologia, % e data dell'insorgenza)"),
        "sordomuto": ("PREACC", "pre-accettazione + QMA timbrato e firmato dal medico"),
        "estero": {"UE": "PREACC", "Regno Unito": "KO", "Tunisia": "KO",
                   "Portogallo": "PREACC", "Altro": "KO"},
        "nota_estero": "solo residenti UE, in pre-accettazione con: pensione INPS/Ente italiano, iscrizione "
                       "AIRE, cedolino, ultimo CUD. Portogallo: quota cedibile decurtata del 30%",
        "decurtazione_portogallo": 0.30,
        "senza_buono_stato_salute": ("VERIFICA", "documentazione medica non prevista: verificare"),
        "validita_doc_medica_giorni": 180,
    },
    "CARDIF": {
        "nome": "Cardif (BNP Paribas)",
        "teleunderwriting": False,
        "eta_minima_ingresso": None,
        "eta_massima_scadenza": (87, 11, 29),           # 88 anni non compiuti
        "montante_massimo": 100000,
        "montante_preacc_oltre": 50000,
        "nota_montante_preacc": "pre-accettazione; documentazione medica: certificato anamnestico firmato "
                                "dal medico (> € 50.000 e ≤ € 70.000), RVM (> € 70.000)",
        "invalido": ("PREACC", "pre-accettazione + RVM + verbale d'invalidità (in assenza del verbale di "
                               "prima istanza: RVM)"),
        "sordomuto": ("PREACC", "pre-accettazione + RVM + verbale d'invalidità"),
        "estero": {"UE": "KO", "Regno Unito": "KO", "Tunisia": "KO", "Portogallo": "KO", "Altro": "KO"},
        "senza_buono_stato_salute": ("PREACC", "questionario medico compilato e firmato dall'assicurando "
                                               "+ pre-accettazione"),
        "validita_doc_medica_giorni": 90,
    },
    "ELIPSLIFE": {
        "nome": "ElipsLife",
        "teleunderwriting": False,
        "eta_minima_ingresso": None,
        "eta_massima_scadenza": (87, 11, 29),           # 88 anni non compiuti
        "montante_massimo": 140000,
        "montante_preacc_oltre": 50000,
        "nota_montante_preacc": "pre-accettazione; documentazione medica: questionario medico anamnestico "
                                "firmato dal medico (> € 50.000 e < € 70.000), RVM con esami medici "
                                "(≥ € 70.000)",
        "invalido": ("PREACC", "pre-accettazione + QMA + verbale d'invalidità"),
        "sordomuto": ("PREACC", "pre-accettazione + QMA + verbale d'invalidità"),
        "estero": {"UE": "KO", "Regno Unito": "KO", "Tunisia": "KO", "Portogallo": "KO", "Altro": "KO"},
        "senza_buono_stato_salute": ("PREACC", "questionario medico anamnestico firmato dal medico + "
                                               "pre-accettazione"),
        "validita_doc_medica_giorni": 120,
    },
}
