"""
REGOLE COMPASS - CESSIONE PRIVATA NO TFR
Fonte: "Criteri Assuntivi CQS 07/2026", pagine 11-16 (aggiornamento 06/2026)
Non è ammesso alcun tipo di deroga. Coesistenze NON ammesse per tutte le compagnie.
Stesso formato di regole_cqs_privati.py.
"""

REQUISITI_GENERALI = {
    "rata_max_quota": 1 / 5,
    "durata_min": 24,
    "durata_max": 120,
}

_ESCLUSO_INTERINALE = "KO"
_PT = {"verticale": "OK", "misto": "VERIFICA", "orizzontale_min_perc": None}
_NESSUNA_COESISTENZA = {"dlg": 0, "pign": 0, "dlg_pign": 0, "preacc_fino": None, "pign_residuo_max": None}

COMPAGNIE = {
    "NET": {
        "nome": "Net Insurance (no TFR)",
        "condizioni_azienda": "Assumibilità azienda da DB GARF: solo ATC \"PRIME\" o \"ATC campagna Compass privati\".",
        "codici_ammessi": ["PRIME", "Campagna Compass privati"],
        "anzianita_minima_mesi": 18,
        "anzianita_massima": {"M": (42, 10, 0), "F": (41, 10, 0)},
        "anzianita_massima_adesione": None,
        "eta_massima_scadenza": (66, 5, 29),            # 67 non compiuti
        "dato_combinato": None,
        "superamento": {
            "ammesso": True, "preacc": False, "eta_assoluta": (75, 5, 29), "quota_tfr": 1.0,
            "eta_max_adesione": (64, 11, 0), "pignoramento_ammesso": False,
            "nota": "V° pieno se al raggiungimento dei limiti il debito residuo non supera il TFR disponibile "
                    "presso l'ATC; con rata < 15% dello stipendio solo se i limiti sono raggiunti nei primi "
                    "5 anni. Se i limiti pensionistici sono già raggiunti alla decorrenza non si può procedere.",
        },
        "durata_max": 120,
        "montante_massimo": 15000,
        "cumulo": "coesistenze non ammesse",
        "tfr_montante": None,
        "coesistenze": _NESSUNA_COESISTENZA,
        "stipendio_minimo": None,
        "inps_se_eta_inizio": (">", 50),
        "interinale": "KO", "part_time": _PT,
        "cig": {"ordinaria": "VERIFICA", "straordinaria": "KO", "maltempo": "OK"},
        "cittadinanza": "UE/Extra-UE equiparati con contratto a tempo indeterminato.",
    },
    "AMTRUST": {
        "nome": "AmTrust / MetLife (no TFR)",
        "condizioni_azienda": "Assumibilità azienda da verificare su DB Quintohub.",
        "anzianita_minima_mesi": 12,
        "anzianita_massima": {"M": (44, 2, 0), "F": (43, 2, 0)},
        "anzianita_massima_adesione": None,
        "eta_massima_scadenza": (67, 11, 29),           # 67 compiuti
        "dato_combinato": None,
        "superamento": {
            "ammesso": True, "preacc": False, "eta_assoluta": (75, 0, 0), "quota_tfr": 1.0,
            "eta_max_adesione": None, "pignoramento_ammesso": True,
            "nota": "Al raggiungimento dei limiti il debito residuo non deve superare il TFR disponibile in "
                    "ATC (o presso Fondo Pensione escutibile), calcolato sulla mensilità netta.",
        },
        "durata_max": 120,
        "montante_massimo": 15000,
        "cumulo": "coesistenze non ammesse",
        "tfr_montante": None,
        "coesistenze": _NESSUNA_COESISTENZA,
        "stipendio_minimo": 600,
        "inps_se_eta_inizio": (">=", 55),
        "interinale": "VERIFICA", "part_time": _PT,
        "cig": {"ordinaria": "KO", "straordinaria": "KO", "maltempo": "OK"},
        "cittadinanza": "UE/Extra-UE equiparati se: ≥ 5 anni in Italia o > 3 anni presso la stessa ATC, e "
                        "permesso a tempo indeterminato / lungo periodo (Extra-UE).",
    },
    "NET_YOUNG": {
        "nome": "Net Insurance YOUNG (no TFR)",
        "condizioni_azienda": "Assumibilità azienda da DB GARF: scoring minimo ATC ≥ 1/4 (no upgrade).",
        "scoring_minimo": 4,
        "anzianita_minima_mesi": 3,
        "anzianita_massima": None,
        "anzianita_massima_adesione": None,
        "eta_massima_decorrenza": (45, 11, 29),         # 45 anni compiuti
        "eta_massima_scadenza": (49, 5, 29),            # 49 anni compiuti
        "dato_combinato": None,
        "superamento": {"ammesso": False},
        "durata_max": 48,
        "montante_massimo": 5000,
        "cumulo": "coesistenze non ammesse",
        "tfr_montante": None,
        "coesistenze": _NESSUNA_COESISTENZA,
        "stipendio_minimo": None,
        "interinale": "KO", "part_time": _PT,
        "cig": {"ordinaria": "VERIFICA", "straordinaria": "KO", "maltempo": "OK"},
        "cittadinanza": "UE/Extra-UE equiparati con contratto a tempo indeterminato.",
    },
    "CARDIF_YOUNG": {
        "nome": "Cardif YOUNG (no TFR)",
        "condizioni_azienda": "Assumibilità azienda da DB Cardif: solo ATC \"YOUNG\".",
        "codici_ammessi": ["YOUNG"],
        "anzianita_minima_mesi": 6,                     # con evidenza del superamento del periodo di prova
        "anzianita_massima_atc_decorrenza": (5, 0, 0),  # anzianità massima a decorrenza 5 anni
        "anzianita_massima": None,
        "anzianita_massima_adesione": None,
        "eta_massima_decorrenza": (40, 11, 29),         # 40 anni compiuti
        "eta_massima_scadenza": (47, 11, 29),           # 47 anni compiuti
        "dato_combinato": None,
        "superamento": {"ammesso": False},
        "durata_max": 84,
        "montante_massimo": 15000,
        "cumulo": "coesistenze non ammesse",
        "tfr_montante": None,
        "coesistenze": _NESSUNA_COESISTENZA,
        "stipendio_minimo": 550,
        "interinale": "PREACC", "part_time": _PT,
        "cig": {"ordinaria": "KO", "straordinaria": "KO", "maltempo": "OK"},
        "cittadinanza": "UE/Extra-UE equiparati se presente uno tra: ≥ 5 anni in Italia; > 3 anni presso la "
                        "stessa ATC; permesso a tempo indeterminato / lungo periodo.",
    },
}
