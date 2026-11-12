"""
REGOLE COMPASS - CESSIONE DEL QUINTO - DIPENDENTI STATALI / PUBBLICI
Fonte: "Criteri Assuntivi CQS 07/2026", pagine 26-32 (aggiornamento 07/2026)
Rapporto TFR/montante: NON richiesto. Durata 24-120 mesi. Rata max 1/5 dello stipendio netto.

Formato specifico dei pubblici:
  eta_massima_scadenza / _militari       -> età massima a scadenza (anni, mesi, giorni)
  anzianita_minima_mesi / _docente_neo   -> anzianità minima (docenti neoassunti a tempo indeterminato)
  limiti_pensione  -> {"eta": amg, "anzianita": {"M","F"}, "anzianita_militari": amg,
                       "dato_combinato": (età, anzianità), "dato_combinato_militari": (età, anzianità)}
  alla_decorrenza  -> cosa succede se i limiti sono già raggiunti alla decorrenza ("KO" o come durante)
  durante          -> cosa succede se i limiti si raggiungono durante l'ammortamento:
        {"azione": "senior"}                  codice prodotto SENIOR per V° pieno o coesistenze
        {"azione": "quota", "perc": 80}       la rata non può superare il V° dell'80% dello stipendio
        {"azione": "cardif15"}                quota ≤ 15% dello stipendio e nessun'altra trattenuta
        {"azione": "standard_entro_3", "perc": 80}   se raggiunti entro i primi 3 anni: STANDARD solo con
                                              rata ≤ V° dell'80%, altrimenti SENIOR
        {"azione": "ko"}
  soglie_eta_scadenza -> lista di regole per età a scadenza oltre una soglia (stesse azioni)
"""

REQUISITI_GENERALI = {
    "rata_max_quota": 1 / 5,
    "durata_min": 24,
    "durata_max": 120,
}

NOTA_STANDARD = ("Con il codice prodotto STANDARD devono essere estinte tutte le eventuali posizioni debitorie "
                 "presenti in busta paga.")
NOTA_CARABINIERI = "Carabinieri in \"ferma quadriennale volontaria\": non assumibili."

COMPAGNIE = {
    "NET": {
        "nome": "Net Insurance",
        "anzianita_minima_mesi": 3, "anzianita_minima_docente_neo": 12,
        "eta_massima_scadenza": (75, 5, 29), "eta_massima_scadenza_militari": (69, 5, 29),
        "limiti_pensione": {"eta": (66, 5, 29), "anzianita": {"M": (42, 10, 0), "F": (41, 10, 0)},
                            "anzianita_militari": (40, 0, 0), "dato_combinato_militari": (57, 35)},
        "alla_decorrenza": "KO",
        "durante": {"azione": "senior"},
        "soglie_eta_scadenza": [{"oltre": (70, 0, 0), "azione": "senior"}],
        "montante_massimo": 100000,
        "montante_preacc": [(50000, "pre-accettazione + modulo adesione con intervista telefonica"),
                            (80000, "pre-accettazione + intervista telefonica + esami medici")],
        "cumulo": "cumulo max € 150.000 se CQS+DLG entrambe con NET",
        "coesistenze": {"dlg": 40, "pign": 40, "dlg_pign": None, "preacc_fino": None, "pign_residuo_max": None},
        "stipendio_minimo": None,
        "inps_se_eta_inizio": (">", 50),
        "note": ["Insegnanti di religione: durata fino a 120 mesi valutabile in pre-accettazione, solo se di "
                 "ruolo e a tempo indeterminato."],
    },
    "CARDIF": {
        "nome": "Cardif (BNP Paribas)",
        "anzianita_minima_mesi": 3, "anzianita_minima_docente_neo": 24,
        "eta_massima_scadenza": (74, 11, 29), "eta_massima_scadenza_militari": (59, 11, 29),
        "limiti_pensione": {"eta": (66, 11, 29), "anzianita": {"M": (42, 11, 29), "F": (41, 11, 29)},
                            "anzianita_militari": (40, 11, 29), "dato_combinato_militari": (58, 35),
                            "formula_cardif": True},   # [età ingresso + durata - 65 (militari 60)] >= 3
        "alla_decorrenza": "come_durante",
        "durante": {"azione": "cardif15"},
        "soglie_eta_scadenza": [],
        "montante_massimo": 80000,
        "montante_preacc": [(90000, "RVM + pre-accettazione (considerando il cumulo con la delega Cardif)")],
        "cumulo": "cumulo max € 132.000 se CQS+DLG entrambe con CARDIF",
        "coesistenze": {"dlg": 40, "pign": 40, "dlg_pign": 50, "preacc_fino": None, "pign_residuo_max": 50000},
        "stipendio_minimo": 550,
        "inps_se_eta_scadenza": (">=", 62),
        "note": ["Non assumibili pratiche con pensionamento previsto entro i primi 12 mesi.",
                 "Con pignoramento serve sempre l'atto di assegnazione."],
    },
    "SOGECAP": {
        "nome": "Sogecap (Société Générale)",
        "anzianita_minima_mesi": 6, "anzianita_minima_docente_neo": 12,
        "anzianita_massima_adesione": (40, 11, 0),
        "eta_massima_scadenza": (74, 11, 29), "eta_massima_scadenza_militari": (59, 11, 29),
        "superamento_eta_militari": "PREACC",
        "limiti_pensione": {"anzianita_militari": (40, 0, 0)},
        "alla_decorrenza": "KO",
        "durante": {"azione": "ko"},
        "soglie_eta_scadenza": [{"oltre": (70, 0, 0), "azione": "senior"},
                                {"oltre": (72, 11, 29), "azione": "quota", "perc": 80}],
        "montante_massimo": 100000,
        "montante_preacc": [],
        "cumulo": "cumulo max € 100.000 se CQS+DLG entrambe con SOGECAP",
        "coesistenze": {"dlg": 50, "pign": 50, "dlg_pign": 50, "preacc_fino": None, "pign_residuo_max": None},
        "stipendio_minimo": 611.85,
        "inps_se_eta_inizio": (">=", 50),
        "note": [],
    },
    "AMTRUST": {
        "nome": "AmTrust / MetLife",
        "anzianita_minima_mesi": 6, "anzianita_minima_docente_neo": 12,
        "eta_massima_scadenza": (75, 0, 0), "eta_massima_scadenza_militari": (61, 0, 0),
        "limiti_pensione": {"eta": (67, 11, 0), "anzianita": {"M": (44, 2, 0), "F": (43, 2, 0)}},
        "alla_decorrenza": "come_durante",
        "durante": {"azione": "quota", "perc": 80},
        "soglie_eta_scadenza": [{"oltre": (70, 0, 0), "azione": "senior"},
                                {"oltre": (70, 0, 0), "azione": "quota", "perc": 80}],
        "montante_massimo": 80000,
        "montante_preacc": [],
        "cumulo": "cumulo max € 100.000 se CQS+DLG entrambe con AMTRUST (cumulo > € 80.000: RVM + "
                  "pre-accettazione)",
        "coesistenze": {"dlg": 40, "pign": 40, "dlg_pign": None, "preacc_fino": 50, "pign_residuo_max": None,
                        "preacc_solo_con_altre": True},
        "stipendio_minimo": 600,
        "inps_se_eta_inizio": (">=", 55),
        "note": ["Sempre necessari Allegato B e Certificazione Unica nel plico documentale.",
                 "Personale docente: non assumibile se nella documentazione c'è una clausola di revoca."],
    },
    "AXA": {
        "nome": "AXA",
        "anzianita_minima_mesi": 6, "anzianita_minima_docente_neo": 24,
        "eta_massima_scadenza": (72, 11, 29), "eta_massima_scadenza_militari": (61, 11, 29),
        "limiti_pensione": {"eta": (67, 5, 0), "anzianita": {"M": (42, 8, 0), "F": (42, 8, 0)},
                            "anzianita_militari": (35, 0, 0), "dato_combinato_militari": (58, 35)},
        "alla_decorrenza": "come_durante",
        "durante": {"azione": "quota", "perc": 70},
        "soglie_eta_scadenza": [],
        "montante_massimo": 75000,
        "montante_preacc": [(50000, "pre-accettazione + questionario anamnestico compilato e firmato dal "
                                    "cedente")],
        "cumulo": "cumulo max € 125.000 se CQS+DLG entrambe con AXA",
        "coesistenze": {"dlg": 40, "pign": 40, "dlg_pign": 40, "preacc_fino": 50, "pign_residuo_max": None},
        "stipendio_minimo": 500,
        "inps_se_eta_inizio": (">=", 55),
        "inps_militari_sempre": True,
        "note": ["Docenti di religione: contratto a tempo indeterminato > 3 anni.",
                 "Esclusi: dipendenti basi NATO; militari in missione con riconoscimento in busta paga per "
                 "missioni di pace."],
    },
    "GREAT_AMERICAN": {
        "nome": "Great American / MetLife",
        "anzianita_minima_mesi": 3, "anzianita_minima_docente_neo": 12,
        "eta_massima_scadenza": (74, 5, 29), "eta_massima_scadenza_militari": (59, 5, 29),
        "limiti_pensione": {"anzianita": {"M": (42, 10, 0), "F": (41, 10, 0)}, "anzianita_militari": (40, 0, 0)},
        "alla_decorrenza": "come_durante",
        "durante": {"azione": "standard_entro_3", "perc": 80},
        "dato_combinato_ga": {"civili": (62, 38), "militari": (57, 35), "perc": 90},
        "soglie_eta_scadenza": [{"oltre": (69, 11, 29), "oltre_militari": (59, 11, 29),
                                 "azione": "standard_soglia", "perc": 80}],
        "montante_massimo": 80000,
        "montante_preacc": [(80000, "RVM + pre-accettazione solo per codice prodotto STANDARD")],
        "cumulo": "cumulo max € 90.000 se CQS+DLG entrambe con Gaiil/MetLife (cumulo > € 80.000: RVM + "
                  "pre-accettazione)",
        "coesistenze": {"dlg": 40, "pign": 40, "dlg_pign": 0, "preacc_fino": None, "pign_residuo_max": 50000},
        "senior_una_coesistenza": True,
        "stipendio_minimo": 500,
        "part_time": {"verticale": "KO", "misto": "KO", "orizzontale_min_perc": 50},
        "inps_se_eta_inizio": (">=", 50),
        "note": ["Sempre necessario l'Allegato B (se non rilasciato: estratti contributivi per la data di "
                 "assunzione).", "Richiedere conferma che non abbia fatto richiesta di pensionamento.",
                 "Tr. Int. L. 21/2020 in busta paga: non considerabile nel calcolo del V°."],
    },
    "HDI": {
        "nome": "HDI Assicurazioni",
        "anzianita_minima_mesi": 6, "anzianita_minima_docente_neo": 6,
        "eta_massima_adesione": (73, 0, 0),
        "eta_massima_scadenza": (75, 5, 29), "eta_massima_scadenza_militari": (75, 5, 29),
        "eta_massima_scadenza_ferrovieri": (67, 5, 29),
        "limiti_pensione": {"anzianita_ferrovieri": {"M": (43, 0, 0), "F": (42, 0, 0)}},
        "alla_decorrenza": "KO",
        "durante": {"azione": "senior"},
        "soglie_eta_scadenza": [{"oltre": (70, 0, 0), "azione": "senior"}],
        "montante_massimo": 60000,
        "montante_preacc": [(60000, "730 o Modello Unico + pre-accettazione")],
        "cumulo": "cumulo max € 60.000 se CQS+DLG entrambe con HDI",
        "coesistenze": {"dlg": None, "pign": None, "dlg_pign": None, "preacc_fino": None,
                        "pign_residuo_max": None, "senza_limiti": True},
        "stipendio_minimo": None,
        "inps_sempre": True,
        "note": ["Sempre necessario l'Allegato B.", "Insegnanti di religione: valutabili in pre-accettazione.",
                 "Ferrovieri: superamento limiti di età (max 75) / anzianità ammesso se al raggiungimento "
                 "dell'età pensionabile il debito residuo non supera il TFR disponibile presso l'ATC."],
    },
}
