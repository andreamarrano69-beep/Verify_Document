"""
REGOLE COMPASS - DELEGAZIONE DI PAGAMENTO - DIPENDENTI PRIVATI
Fonte: "Criteri Assuntivi DLG 07/2026", pagine 1-10
Requisiti minimi: rata max 1/5 dello stipendio netto, durata 24-120 mesi, n. minimo dipendenti 16.
La delega NON è ammessa senza una CQS in corso. HDI: delegazione non assumibile.

Campi in più rispetto alle CQS:
  montante_massimo_cqs_stessa / _cqs_altra -> montante max se la CQS in corso è assicurata con la stessa
                                              compagnia oppure con un'altra (None = non ammessa)
  variante_se_cqs_altra -> codice della variante da usare se la CQS è con un'altra compagnia (Net Delega Plus)
  coesistenze: dlg_cqs = % max CQS+DLG; dlg_cqs_pign = % max con anche il pignoramento (0 = non ammesso)
  tfr_montante scoring: montante <= TFR x scoring - montante residuo della CQS
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
        "condizioni_azienda": "DB GARF (scoring max 6/1; +1 solo con rinnovo interno se 'Applicabile solo "
                              "l'upgrade in caso di rinnovo interno').",
        "solo_se_cqs_stessa": True, "variante_se_cqs_altra": "NET_PLUS",
        "anzianita_minima_mesi": 3,
        "anzianita_massima": {"M": (42, 10, 0), "F": (41, 10, 0)},
        "eta_massima_scadenza": (66, 5, 29),
        "dato_combinato": None,
        "superamento": {
            "ammesso": True, "preacc": False, "eta_assoluta": None, "quota_tfr": 1.0,
            "pignoramento_ammesso": True,
            "nota": "Al raggiungimento dei limiti il debito residuo di tutti gli impegni non deve superare il "
                    "TFR disponibile presso l'ATC. Se i limiti pensionistici sono già raggiunti alla decorrenza "
                    "non si può procedere.",
        },
        "montante_massimo": 65000,
        "montante_preacc_oltre": 50000,
        "nota_montante_preacc": "pre-accettazione + modulo adesione con intervista telefonica",
        "cumulo": "cumulo max € 65.000 (€ 75.000 se TFR ≥ € 35.000) se CQS+DLG entrambe con NET",
        "tfr_montante": {"tipo": "scoring", "scoring_max": 6, "db": "GARF", "meno_residuo_cqs": True},
        "coesistenze": {"dlg_cqs": 40, "dlg_cqs_pign": 50},
        "stipendio_minimo": None,
        "inps_se_eta_inizio": (">", 50),
        "interinale": "KO", "part_time": _PT,
        "cig": {"ordinaria": "VERIFICA", "straordinaria": "KO", "maltempo": "OK"},
        "cittadinanza": "UE/Extra-UE equiparati con contratto a tempo indeterminato.",
    },
    "NET_PLUS": {   # Delega PLUS: usata al posto di NET quando la CQS NON è assicurata con NET (pag. 9-10)
        "nome": "Net Insurance – Delega Plus (CQS non NET)",
        "condizioni_azienda": "DB GARF: solo ATC \"PRIME\" o \"PRIME ESG\".",
        "codici_ammessi": ["PRIME", "PRIME ESG"],
        "anzianita_minima_mesi": 3,
        "anzianita_massima": {"M": (42, 10, 0), "F": (41, 10, 0)},
        "eta_massima_scadenza": (66, 5, 29),
        "dato_combinato": {"eta": 62, "anzianita": 41},
        "superamento": {
            "ammesso": True, "preacc": False, "eta_assoluta": None, "quota_tfr": 1.0,
            "pignoramento_ammesso": False,
            "nota": "Al raggiungimento dei limiti il debito residuo di tutti gli impegni non deve superare il "
                    "TFR disponibile presso l'ATC.",
        },
        "durata_max": 60,
        "montante_massimo": 9000,
        "cumulo": "Delega Plus: CQS assicurata con un'altra compagnia",
        "tfr_montante": {"tipo": "scoring", "scoring_max": 6, "db": "GARF", "meno_residuo_cqs": True},
        "coesistenze": {"dlg_cqs": 40, "dlg_cqs_pign": 0},
        "stipendio_minimo": None,
        "inps_se_eta_inizio": (">", 50),
        "interinale": "KO", "part_time": _PT,
        "cig": {"ordinaria": "VERIFICA", "straordinaria": "VERIFICA", "maltempo": "VERIFICA"},
        "cittadinanza": "UE/Extra-UE equiparati con contratto a tempo indeterminato.",
    },
    "CARDIF": {
        "nome": "Cardif (BNP Paribas)",
        "scoring_minimo": 3,
        "condizioni_azienda": "DB Cardif: scoring minimo ATC 1/3. Esclusi i cedenti con qualifica di dirigente. "
                              "Con CQS+DLG istruite contestualmente da Compass è assumibile solo la delega.",
        "solo_cittadini_italiani": True,
        "anzianita_minima_mesi": 36,
        "anzianita_massima": {"M": (43, 11, 29), "F": (42, 11, 29)},
        "eta_massima_scadenza": (67, 11, 29),
        "eta_massima_scadenza_durata24": (66, 11, 29),
        "dato_combinato": None,
        "superamento": {"ammesso": False},
        "montante_massimo": 15000,
        "cumulo": "cumulo max € 64.000 se CQS+DLG entrambe con CARDIF",
        "tfr_montante": None,   # € 15.000 senza considerare il rapporto TFR/montante
        "coesistenze": {"dlg_cqs": 40, "dlg_cqs_pign": 0},
        "stipendio_minimo": 550,
        "inps_se_eta_scadenza": (">=", 62),
        "interinale": "PREACC", "part_time": _PT,
        "cig": {"ordinaria": "KO", "straordinaria": "KO", "maltempo": "OK"},
        "cittadinanza": "solo cittadini italiani.",
    },
    "SOGECAP": {
        "nome": "Sogecap (Société Générale)",
        "condizioni_azienda": "DB Ses@me. Escluso chi usufruisce di permessi L.104/92 (anche per familiari).",
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
        "condizioni_azienda": "DB Quintohub (scoring max 6/1).",
        "solo_se_cqs_stessa": True,
        "anzianita_minima_mesi": 6,
        "anzianita_massima": {"M": (44, 2, 0), "F": (43, 2, 0)},
        "eta_massima_scadenza": (67, 11, 29),
        "dato_combinato": None,
        "superamento": {"ammesso": False},
        "montante_massimo": 30000,
        "cumulo": "cumulo max € 70.000 se CQS+DLG entrambe con AMTRUST",
        "tfr_montante": {"tipo": "scoring", "scoring_max": 6, "db": "Quintohub", "meno_residuo_cqs": True},
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
        "condizioni_azienda": "DB Ses@me. Esclusi i dipendenti bancari.",
        "solo_se_cqs_stessa": True, "cqs_stipulata_compass": True,
        "anzianita_minima_mesi": 12,
        "anzianita_massima": {"M": (44, 2, 0), "F": (43, 2, 0)},
        "eta_massima_scadenza": (67, 11, 29),
        "dato_combinato": None,
        "superamento": {"ammesso": False},
        "montante_massimo": 30000,
        "cumulo": "cumulo max € 105.000 se CQS+DLG entrambe con AXA",
        "tfr_montante": {"tipo": "scoring", "scoring_max": None, "db": "Ses@me", "meno_residuo_cqs": True},
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
        "condizioni_azienda": "DB All Risks. Esclusi invalidi/inabili. Eventuali prestiti aziendali devono essere "
                              "estinti (serve dichiarazione assenza pignoramenti/prestiti aziendali accodati).",
        "anzianita_minima_mesi": 36,
        "anzianita_massima": {"M": (42, 10, 0), "F": (41, 10, 0)},
        "eta_massima_scadenza": (66, 5, 29),
        "dato_combinato": {"eta": 62, "anzianita": 38},
        "superamento": {"ammesso": False},
        "montante_massimo": 15000,
        "cumulo": "cumulo max € 52.000 se CQS+DLG entrambe con Gaiil/MetLife",
        "tfr_montante": {"tipo": "scoring", "scoring_max": 5, "db": "All Risks", "meno_residuo_cqs": True},
        "coesistenze": {"dlg_cqs": 40, "dlg_cqs_pign": 0},
        "stipendio_minimo": 500,
        "inps_se_eta_inizio": (">=", 50),
        "interinale": "KO", "part_time": {"verticale": "KO", "misto": "KO", "orizzontale_min_perc": 50},
        "cig": {"ordinaria": "KO", "straordinaria": "KO", "maltempo": "VERIFICA"},
        "cittadinanza": "UE con residenza in Italia. Extra-UE con permesso a tempo indeterminato / lungo "
                        "periodo (non ammessa carta per Familiare UE art. 20).",
    },
}
