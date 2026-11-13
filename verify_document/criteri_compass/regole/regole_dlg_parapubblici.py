"""
REGOLE COMPASS - DELEGAZIONE DI PAGAMENTO - DIPENDENTI PARAPUBBLICI
Fonte: "Criteri Assuntivi DLG 07/2026", pagine 11-18 (aggiornamento 06/2026)
Requisiti minimi: rata max 1/5, durata 24-120 mesi, n. minimo dipendenti 16. Delega mai senza CQS.
Stesso formato di regole_dlg_privati.py.
"""

REQUISITI_GENERALI = {
    "rata_max_quota": 1 / 5,
    "durata_min": 24,
    "durata_max": 120,
    "dipendenti_minimi": 16,
    "cqs_obbligatoria": True,
}

_PT = {"verticale": "OK", "misto": "VERIFICA", "orizzontale_min_perc": None}

COMPAGNIE = {
    "NET": {
        "nome": "Net Insurance",
        "condizioni_azienda": "DB GARF: con 'Applicare criteri parapubblici e tassi privati' caricare con "
                              "prodotto privato e criteri parapubblici.",
        "anzianita_minima_mesi": 3,
        "anzianita_massima": {"M": (42, 10, 0), "F": (41, 10, 0)},
        "eta_massima_scadenza": (66, 5, 29),
        "dato_combinato": None,
        "superamento": {
            "ammesso": True, "preacc": False, "eta_assoluta": (75, 0, 0), "quota_tfr": 1.0,
            "pignoramento_ammesso": True,
            "nota": "Al raggiungimento dei limiti il debito residuo di tutti gli impegni non deve superare il "
                    "TFR disponibile presso l'ATC. Se i limiti pensionistici sono già raggiunti alla decorrenza "
                    "non si può procedere.",
        },
        "montante_massimo": 20000,                   # senza tener conto del TFR
        "cumulo": "cumulo max € 75.000 se CQS+DLG entrambe con NET",
        "tfr_montante": None,
        "coesistenze": {"dlg_cqs": 40, "dlg_cqs_pign": 50},
        "stipendio_minimo": None,
        "inps_se_eta_inizio": (">", 50),
        "interinale": "KO", "part_time": _PT,
        "cig": {"ordinaria": "VERIFICA", "straordinaria": "KO", "maltempo": "OK"},
        "cittadinanza": "UE/Extra-UE equiparati con contratto a tempo indeterminato.",
    },
    "CARDIF": {
        "codici_ammessi": ["A", "B"],
        "nome": "Cardif (BNP Paribas)",
        "condizioni_azienda": "DB Cardif: ATC categoria A o B (rapporto TFR/montante 1/4). Esclusi i dirigenti. "
                              "Con DLG+CQS istruite contestualmente da Compass non è assumibile la sola delega.",
        "solo_cittadini_italiani": True,
        "anzianita_minima_mesi": 3,
        "anzianita_massima": {"M": (43, 11, 29), "F": (42, 11, 29)},
        "eta_massima_scadenza": (67, 11, 29),
        "eta_massima_scadenza_durata24": (66, 11, 29),
        "dato_combinato": None,
        "superamento": {"ammesso": False},
        "montante_massimo": 30000,
        "cumulo": "cumulo max € 82.000 se CQS+DLG entrambe con CARDIF",
        "tfr_montante": {"tipo": "fisso", "moltiplicatore": 4, "meno_residuo_cqs": True},
        "coesistenze": {"dlg_cqs": 40, "dlg_cqs_pign": 0},
        "stipendio_minimo": 550,
        "inps_se_eta_scadenza": (">=", 62),
        "interinale": "VERIFICA", "part_time": _PT,
        "cig": {"ordinaria": "KO", "straordinaria": "KO", "maltempo": "OK"},
        "cittadinanza": "solo cittadini italiani.",
    },
    "SOGECAP": {
        "nome": "Sogecap (Société Générale)",
        "condizioni_azienda": "DB Ses@me: con 'Parificata Pubblica' usare prodotto e criteri parapubblici.",
        "anzianita_minima_mesi": 12,
        "anzianita_massima": {"M": (42, 11, 29), "F": (42, 11, 29)},
        "anzianita_massima_adesione": (30, 11, 0),
        "eta_massima_scadenza": (66, 11, 29),
        "dato_combinato": None,
        "superamento": {"ammesso": False},
        "montante_massimo": 40000, "montante_massimo_cqs_altra": 20000,
        "cumulo": "cumulo max € 100.000 se CQS+DLG entrambe con SOGECAP",
        "tfr_montante": {"tipo": "scoring", "scoring_max": None, "db": "Ses@me", "meno_residuo_cqs": True},
        "coesistenze": {"dlg_cqs": 50, "dlg_cqs_pign": 0},
        "stipendio_minimo": 611.85,
        "inps_se_eta_inizio": (">=", 50),
        "interinale": "KO", "part_time": _PT,
        "cig": {"ordinaria": "KO", "straordinaria": "KO", "maltempo": "OK"},
        "cittadinanza": "UE con residenza in Italia. Extra-UE solo con TUTTI: ≥ 5 anni in Italia, ≥ 3 anni presso "
                        "la stessa ATC, contratto a tempo indeterminato, salario minimo € 1.000 netti, permesso "
                        "a tempo indeterminato / lungo periodo.",
    },
    "AMTRUST": {
        "nome": "AmTrust / MetLife",
        "condizioni_azienda": "DB Quintohub.",
        "solo_se_cqs_stessa": True,
        "anzianita_minima_mesi": 6,
        "anzianita_massima": {"M": (43, 11, 0), "F": (42, 11, 0)},
        "eta_massima_scadenza": (67, 11, 29),
        "dato_combinato": None,
        "superamento": {"ammesso": False},
        "montante_massimo": 20000,
        "cumulo": "cumulo max € 100.000 se CQS+DLG entrambe con AMTRUST",
        "tfr_montante": {"tipo": "scoring", "scoring_max": None, "db": "Quintohub", "meno_residuo_cqs": True},
        "coesistenze": {"dlg_cqs": 40, "dlg_cqs_pign": 0},
        "stipendio_minimo": 600,
        "inps_se_eta_inizio": (">=", 55),
        "interinale": "VERIFICA", "part_time": _PT,
        "cig": {"ordinaria": "KO", "straordinaria": "KO", "maltempo": "OK"},
        "cittadinanza": "UE/Extra-UE equiparati se: ≥ 5 anni in Italia o ≥ 3 anni presso la stessa ATC, e "
                        "permesso a tempo indeterminato / lungo periodo (Extra-UE).",
    },
    "AXA": {
        "nome": "AXA",
        "condizioni_azienda": "DB Ses@me: il rapporto TFR/montante non può mai superare 1/5 anche nel cumulo di "
                              "impegni che vincolano il TFR.",
        "solo_se_cqs_stessa": True, "cqs_stipulata_compass": True,
        "anzianita_minima_mesi": 12,
        "anzianita_massima": {"M": (43, 11, 0), "F": (42, 11, 0)},
        "eta_massima_scadenza": (67, 11, 29),
        "dato_combinato": None,
        "superamento": {"ammesso": False},
        "montante_massimo": 30000,
        "cumulo": "cumulo max € 105.000 se CQS+DLG entrambe con AXA",
        "tfr_montante": {"tipo": "scoring", "scoring_max": 5, "db": "Ses@me", "meno_residuo_cqs": True},
        "coesistenze": {"dlg_cqs": 40, "dlg_cqs_pign": 0, "pign_alimenti_preacc": True, "preacc_fino": 50},
        "stipendio_minimo": 500,
        "inps_se_eta_inizio": (">=", 55),
        "interinale": "KO", "part_time": _PT,
        "cig": {"ordinaria": "KO", "straordinaria": "KO", "maltempo": "OK"},
        "cittadinanza": "UE con residenza in Italia. Extra-UE con permesso a tempo indeterminato / lungo "
                        "periodo e uno tra: ≥ 5 anni in Italia, ≥ 3 anni presso la stessa ATC.",
    },
    "GREAT_AMERICAN": {
        "nome": "Great American / MetLife",
        "condizioni_azienda": "DB All Risks (rapporto mai superiore a 1/5). Esclusi invalidi/inabili. Dipendenti "
                              "postali non assumibili con voce 'Rec. Somme Acc.' in busta paga. Eventuali prestiti "
                              "aziendali devono essere estinti.",
        "anzianita_minima_mesi": 3,
        "anzianita_massima": {"M": (42, 10, 0), "F": (41, 10, 0)},
        "eta_massima_scadenza": (66, 5, 29),
        "dato_combinato": {"eta": 62, "anzianita": 38},
        "superamento": {"ammesso": False},
        "montante_massimo": 30000,
        "cumulo": "cumulo max € 60.000 se CQS+DLG entrambe con Gaiil/MetLife",
        "tfr_montante": {"tipo": "scoring", "scoring_max": 5, "db": "All Risks", "meno_residuo_cqs": True},
        "coesistenze": {"dlg_cqs": 40, "dlg_cqs_pign": 0},
        "stipendio_minimo": 500,
        "inps_se_eta_inizio": (">=", 50),
        "interinale": "KO", "part_time": {"verticale": "KO", "misto": "KO", "orizzontale_min_perc": 50},
        "cig": {"ordinaria": "KO", "straordinaria": "KO", "maltempo": "VERIFICA"},
        "cittadinanza": "UE con residenza in Italia. Extra-UE con permesso a tempo indeterminato / lungo "
                        "periodo (non ammessa carta per Familiare UE art. 20).",
    },
    "HDI": {
        "nome": "HDI Assicurazioni",
        "condizioni_azienda": "Società partecipate: da Enti locali almeno 40%, dallo Stato almeno 50%, da altre "
                              "aziende 100%. Esclusi i dipendenti postali.",
        "solo_cittadini_italiani": True,
        "anzianita_minima_mesi": 6,
        "anzianita_minima_giorni_extra": 1,
        "durata_max_se_anzianita_sotto": ((6, 0, 0), 60),
        "anzianita_massima": {"M": (43, 0, 0), "F": (42, 0, 0)},
        "eta_massima_scadenza": (67, 5, 29),
        "dato_combinato": {"eta": 62, "anzianita": 41},
        "superamento": {
            "ammesso": True, "preacc": False, "eta_assoluta": (75, 0, 0), "quota_tfr": 1.0,
            "pignoramento_ammesso": True,
            "nota": "Al raggiungimento dei limiti il debito residuo non deve superare il TFR disponibile presso "
                    "l'ATC. Con trattenuta previdenziale INDAP il superamento non è ammesso.",
        },
        "montante_massimo": 60000,
        "cumulo": "cumulo max € 60.000 se CQS+DLG entrambe con HDI",
        "tfr_montante": None,
        "coesistenze": {"dlg_cqs": None, "dlg_cqs_pign": None, "senza_limiti": True},
        "stipendio_minimo": None,
        "inps_sempre": True,
        "interinale": "KO", "part_time": _PT,
        "cig": {"ordinaria": "PREACC", "straordinaria": "KO", "maltempo": "OK"},
        "cig_ordinaria_nota": "con dichiarazione ATC su ore applicate, rotazione e durata",
        "cittadinanza": "solo cittadini italiani.",
    },
}
