"""
REGOLE COMPASS - DELEGAZIONE DI PAGAMENTO - DIPENDENTI STATALI / PUBBLICI
Fonte: "Criteri Assuntivi DLG 07/2026", pagine 19-23 (aggiornamento 06/2026)
Requisiti minimi: rata max 1/5, durata 24-120 mesi. Rapporto TFR/montante non richiesto. Delega mai senza CQS.
Stesso formato di regole_dlg_privati.py, con le varianti per militari e docenti neoassunti.
"""

REQUISITI_GENERALI = {
    "rata_max_quota": 1 / 5,
    "durata_min": 24,
    "durata_max": 120,
    "dipendenti_minimi": None,
    "cqs_obbligatoria": True,
}

_PT = {"verticale": "OK", "misto": "VERIFICA", "orizzontale_min_perc": None}
_CIG = {"ordinaria": "VERIFICA", "straordinaria": "VERIFICA", "maltempo": "VERIFICA"}
_BASE = {"tfr_montante": None, "superamento": {"ammesso": False}, "interinale": "VERIFICA",
         "part_time": _PT, "cig": _CIG, "dato_combinato": None}

COMPAGNIE = {
    "NET": dict(_BASE, **{
        "nome": "Net Insurance",
        "condizioni_azienda": "Esclusi gli insegnanti di religione.",
        "anzianita_minima_mesi": 3, "anzianita_minima_docente_neo": 12,
        "anzianita_massima": {"M": (42, 10, 0), "F": (41, 10, 0)}, "anzianita_massima_militari": (40, 0, 0),
        "eta_massima_scadenza": (66, 5, 29), "eta_massima_scadenza_militari": (59, 5, 29),
        "dato_combinato_militari": {"eta": 57, "anzianita": 35},
        "montante_massimo": 75000,
        "montante_preacc_oltre": 50000,
        "nota_montante_preacc": "pre-accettazione + modulo adesione con intervista telefonica",
        "cumulo": "cumulo max € 150.000 se DLG+CQS entrambe con NET",
        "coesistenze": {"dlg_cqs": 40, "dlg_cqs_pign": None},   # con pignoramento: pre-accettazione
        "stipendio_minimo": None,
        "inps_se_eta_inizio": (">", 50),
        "cittadinanza": "UE/Extra-UE equiparati con contratto a tempo indeterminato.",
    }),
    "CARDIF": dict(_BASE, **{
        "nome": "Cardif (BNP Paribas)",
        "condizioni_azienda": "Non assumibili pratiche con pensionamento previsto entro i primi 12 mesi. Con DLG+CQS "
                              "istruite contestualmente da Compass non è assumibile la sola delega.",
        "solo_cittadini_italiani": True,
        "anzianita_minima_mesi": 3, "anzianita_minima_docente_neo": 24,
        "anzianita_massima": {"M": (43, 11, 29), "F": (42, 11, 29)}, "anzianita_massima_militari": (41, 0, 0),
        "eta_massima_scadenza": (67, 11, 29), "eta_massima_scadenza_militari": (59, 11, 29),
        "eta_massima_scadenza_durata24": (66, 11, 29),
        "dato_combinato_militari": {"eta": 58, "anzianita": 35},
        "montante_massimo": 52000,
        "cumulo": "cumulo max € 132.000 se DLG+CQS entrambe con CARDIF",
        "coesistenze": {"dlg_cqs": 40, "dlg_cqs_pign": 0,
                        "nota_pign": "il pignoramento deve essere estinto (dichiarazione assenza pignoramenti accodati)"},
        "stipendio_minimo": 550,
        "inps_se_eta_scadenza": (">=", 62), "inps_militari_se_eta_scadenza": (">=", 50),
        "cittadinanza": "solo cittadini italiani.",
    }),
    "SOGECAP": dict(_BASE, **{
        "nome": "Sogecap (Société Générale)",
        "anzianita_minima_mesi": 12, "anzianita_minima_docente_neo": 12,
        "anzianita_massima": {"M": (42, 11, 29), "F": (42, 11, 29)}, "anzianita_massima_militari": (40, 0, 0),
        "anzianita_massima_adesione": (40, 11, 0),
        "eta_massima_scadenza": (66, 11, 29), "eta_massima_scadenza_militari": (59, 11, 29),
        "dato_combinato_militari": {"eta": 57, "anzianita": 35},
        "montante_massimo": 40000,
        "cumulo": "cumulo max € 100.000 se DLG+CQS entrambe con SOGECAP",
        "coesistenze": {"dlg_cqs": 50, "dlg_cqs_pign": 0},
        "stipendio_minimo": 611.85,
        "inps_se_eta_inizio": (">=", 50),
        "cittadinanza": "UE con residenza in Italia. Extra-UE solo con TUTTI: ≥ 5 anni in Italia, ≥ 3 anni presso "
                        "la stessa ATC, contratto a tempo indeterminato, salario minimo € 1.000 netti, permesso "
                        "a tempo indeterminato / lungo periodo.",
    }),
    "AMTRUST": dict(_BASE, **{
        "nome": "AmTrust / MetLife",
        "condizioni_azienda": "Personale docente: non assumibile con clausola di revoca nella documentazione.",
        "solo_se_cqs_stessa": True,
        "anzianita_minima_mesi": 6, "anzianita_minima_docente_neo": 12,
        "anzianita_massima": {"M": (44, 2, 0), "F": (43, 2, 0)}, "anzianita_massima_militari": (35, 0, 0),
        "eta_massima_scadenza": (67, 11, 29), "eta_massima_scadenza_militari": (60, 0, 0),
        "dato_combinato_militari": {"eta": 58, "anzianita": 35},
        "montante_massimo": 20000,
        "cumulo": "cumulo max € 100.000 se DLG+CQS entrambe con AMTRUST",
        "coesistenze": {"dlg_cqs": 40, "dlg_cqs_pign": 0},
        "stipendio_minimo": 600,
        "inps_se_eta_scadenza": (">=", 55), "inps_militari_se_eta_scadenza": (">=", 45),
        "cittadinanza": "UE/Extra-UE equiparati se: ≥ 5 anni in Italia o ≥ 3 anni presso la stessa ATC, e "
                        "permesso a tempo indeterminato / lungo periodo (Extra-UE).",
    }),
    "AXA": dict(_BASE, **{
        "nome": "AXA",
        "condizioni_azienda": "Docenti di religione: contratto a tempo indeterminato > 3 anni.",
        "anzianita_minima_mesi": 12, "anzianita_minima_docente_neo": 24,
        "anzianita_massima": {"M": (44, 2, 0), "F": (43, 2, 0)}, "anzianita_massima_militari": (35, 0, 0),
        "eta_massima_scadenza": (60, 11, 29), "eta_massima_scadenza_militari": (60, 11, 29),
        "dato_combinato_militari": {"eta": 58, "anzianita": 35},
        "montante_massimo": 50000,
        "cumulo": "cumulo max € 125.000 se DLG+CQS entrambe con AXA",
        "coesistenze": {"dlg_cqs": 40, "dlg_cqs_pign": 0, "pign_alimenti_preacc": True, "preacc_fino": 50},
        "stipendio_minimo": 500,
        "inps_se_eta_inizio": (">=", 55), "inps_militari_sempre": True,
        "cittadinanza": "UE con residenza in Italia. Extra-UE con permesso a tempo indeterminato / lungo "
                        "periodo e uno tra: ≥ 5 anni in Italia, ≥ 3 anni presso la stessa ATC.",
    }),
    "GREAT_AMERICAN": dict(_BASE, **{
        "nome": "Great American / MetLife",
        "condizioni_azienda": "Richiedere conferma che non abbia fatto richiesta di pensionamento. Tr. Int. L. 21/2020 "
                              "in busta paga: non considerabile nel calcolo del V°.",
        "anzianita_minima_mesi": 3, "anzianita_minima_docente_neo": 12,
        "anzianita_massima": {"M": (42, 10, 0), "F": (41, 10, 0)}, "anzianita_massima_militari": (40, 0, 0),
        "eta_massima_scadenza": (66, 5, 29), "eta_massima_scadenza_militari": (59, 5, 29),
        "dato_combinato": {"eta": 62, "anzianita": 38},
        "dato_combinato_militari": {"eta": 57, "anzianita": 35},
        "montante_massimo": 40000,
        "cumulo": "cumulo max € 90.000 se DLG+CQS entrambe con Gaiil/MetLife",
        "coesistenze": {"dlg_cqs": 40, "dlg_cqs_pign": 0},
        "stipendio_minimo": 500,
        "part_time": {"verticale": "KO", "misto": "KO", "orizzontale_min_perc": 50},
        "inps_se_eta_inizio": (">=", 50),
        "cittadinanza": "UE con residenza in Italia. Extra-UE con permesso a tempo indeterminato / lungo "
                        "periodo (non ammessa carta per Familiare UE art. 20).",
    }),
    "HDI": dict(_BASE, **{
        "nome": "HDI Assicurazioni",
        "condizioni_azienda": "Esclusi militari e personale amministrativo che percepiscono rendita INAIL o pensione "
                              "di invalidità.",
        "solo_cittadini_italiani": True,
        "anzianita_minima_mesi": 6, "anzianita_minima_giorni_extra": 1, "anzianita_minima_docente_neo": 6,
        "anzianita_massima": {"M": (43, 0, 0), "F": (42, 0, 0)},
        "eta_massima_scadenza": (67, 5, 29),
        "eta_massima_scadenza_militari": (45, 5, 29),      # militari e personale amministrativo: 45 compiuti
        "dato_combinato": {"eta": 62, "anzianita": 41},
        "superamento_ferrovieri": "Ferrovieri: superamento limiti di età (max 75) / anzianità ammesso se al "
                                  "raggiungimento dell'età pensionabile il debito residuo non supera il TFR "
                                  "disponibile presso l'ATC.",
        "montante_massimo": 60000,
        "cumulo": "cumulo max € 60.000 se DLG+CQS entrambe con HDI",
        "coesistenze": {"dlg_cqs": None, "dlg_cqs_pign": None, "senza_limiti": True},
        "stipendio_minimo": None,
        "inps_sempre": True,
        "cittadinanza": "solo cittadini italiani.",
    }),
}
