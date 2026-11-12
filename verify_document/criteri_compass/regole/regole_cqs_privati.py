"""
REGOLE COMPASS - CESSIONE DEL QUINTO - DIPENDENTI PRIVATI
Fonte: "Criteri Assuntivi CQS 07/2026" (pagine 1-10, aggiornamento 06/2026)

Questo file contiene i limiti numerici delle tabelle Compass, compagnia per compagnia.
Quando Compass aggiorna i criteri, basta cambiare i numeri qui sotto.

Convenzioni:
  - le età e le anzianità sono scritte come (anni, mesi, giorni)
  - i limiti "da intendersi" del PDF sono già scritti nella forma esatta
    (es. "67 anni non compiuti, da intendersi 66 anni 5 mesi e 29 giorni" -> (66, 5, 29))
  - percentuali in %, importi in euro
  - livelli: "OK" assumibile, "PREACC" valutabile in pre-accettazione,
             "KO" non assumibile, "VERIFICA" non previsto/da verificare
"""

REQUISITI_GENERALI = {
    "rata_max_quota": 1 / 5,        # rata max 1/5 dello stipendio netto
    "durata_min": 24,               # mesi
    "durata_max": 120,              # mesi
    # ATC "non assumibile" nel DB della compagnia: valutabile in pre-accettazione solo con TFR/Montante 1/1
    "non_assumibile_preacc_1_1": True,
}

COMPAGNIE = {
    # ------------------------------------------------------------------ NET
    "NET": {
        "nome": "Net Insurance",
        "anzianita_minima_mesi": 3,                          # + periodo di prova superato (pag. 3)
        "anzianita_massima": {"M": (42, 10, 0), "F": (41, 10, 0)},   # pag. 3
        "anzianita_massima_adesione": None,
        "eta_massima_scadenza": (66, 5, 29),                 # 67 non compiuti (pag. 3)
        "eta_massima_scadenza_durata24": None,
        "dato_combinato": None,                              # non previsto
        "superamento": {                                     # pag. 4
            "ammesso": True, "preacc": False,
            "eta_assoluta": (75, 5, 29),
            "quota_tfr": 1.0,                                # debito residuo <= TFR disponibile in ATC
            "eta_max_adesione": (64, 11, 0),
            "pignoramento_ammesso": False,
            "nota": "V° pieno: al raggiungimento dei limiti il debito residuo di tutti gli impegni "
                    "non deve superare il TFR disponibile presso l'ATC (con Fondo Pensione escutibile: "
                    "1/5 del TFR presso il Fondo). Alla decorrenza non devono essere già raggiunti i "
                    "requisiti pensionistici.",
        },
        "montante_massimo": 65000,                           # pag. 5
        "cumulo": "cumulo max € 65.000 (€ 75.000 se TFR ≥ € 35.000) se CQS+DLG entrambe con NET",
        "tfr_montante": {"tipo": "scoring", "scoring_max": 6, "db": "GARF"},   # pag. 1
        "coesistenze": {"dlg": 40, "pign": 40, "dlg_pign": 50,              # pag. 6
                        "preacc_fino": None, "pign_residuo_max": None},
        "stipendio_minimo": None,                                            # pag. 9
        "inps_se_eta_inizio": (">", 50),                                     # pag. 2
        "interinale": "KO", "part_time": {"verticale": "OK", "misto": "VERIFICA",
                                          "orizzontale_min_perc": None},
        "cig": {"ordinaria": "VERIFICA", "straordinaria": "KO", "maltempo": "OK"},
        "cittadinanza": "UE/Extra-UE equiparati al lavoratore italiano con contratto a tempo indeterminato.",
    },
    # ------------------------------------------------------------------ CARDIF
    "CARDIF": {
        "nome": "Cardif (BNP Paribas)",
        "anzianita_minima_mesi": 6,
        "anzianita_massima": {"M": (43, 11, 29), "F": (42, 11, 29)},
        "anzianita_massima_adesione": None,
        "eta_massima_scadenza": (67, 11, 29),                # 68 non compiuti
        "eta_massima_scadenza_durata24": (66, 11, 29),
        "dato_combinato": None,
        "superamento": {
            "ammesso": True, "preacc": False,
            "eta_assoluta": None,
            "quota_tfr": 0.75,                               # TFR NETTO (tassazione 25%)
            "eta_max_adesione": None,
            "coesistenze_ammesse": False,                    # coesistenze non ammesse
            "durata24_ammessa": False,
            "nota": "V° pieno: al raggiungimento dei limiti il debito residuo non deve superare il TFR "
                    "NETTO (tassazione 25%) presso l'ATC. Con rata ≤ 15% dello stipendio ci sono regole "
                    "speciali (età max a scadenza 69 non compiuti con durata 72-120 mesi, 68 con 36-60 mesi). "
                    "Coesistenze non ammesse. Non operazioni con pensionamento previsto entro 12 mesi.",
        },
        "montante_massimo": 52000,
        "cumulo": "cumulo max ≤ € 64.000 se CQS+DLG entrambe con CARDIF",
        "tfr_montante": {"tipo": "scoring", "scoring_max": None, "db": "Cardif"},
        "coesistenze": {"dlg": 40, "pign": 40, "dlg_pign": 50,
                        "preacc_fino": None, "pign_residuo_max": 50000},
        "stipendio_minimo": 550,
        "inps_se_eta_scadenza": (">=", 62),
        "interinale": "PREACC", "part_time": {"verticale": "OK", "misto": "VERIFICA",
                                              "orizzontale_min_perc": None},
        "cig": {"ordinaria": "PREACC", "straordinaria": "KO", "maltempo": "OK"},
        "cig_ordinaria_nota": "solo con TFR/Montante max 1/1, montante max € 20.000 e scoring azienda ≥ 4/1",
        "cittadinanza": "UE/Extra-UE equiparati se presente UNO tra: ≥ 5 anni in Italia; ≥ 3 anni presso "
                        "la stessa ATC; permesso di soggiorno a tempo indeterminato / soggiornante di lungo "
                        "periodo. Se non rispettati: TFR/Montante 2/1.",
    },
    # ------------------------------------------------------------------ SOGECAP
    "SOGECAP": {
        "nome": "Sogecap (Société Générale)",
        "anzianita_minima_mesi": 6,
        "anzianita_massima": {"M": (42, 11, 29), "F": (42, 11, 29)},
        "anzianita_massima_adesione": (40, 11, 0),          # all'adesione max 40 anni (40a 11m)
        "eta_massima_scadenza": (66, 11, 29),                # 67 non compiuti
        "eta_massima_scadenza_durata24": None,
        "dato_combinato": None,
        "superamento": {"ammesso": False},
        "montante_massimo": 100000,
        "cumulo": "cumulo max € 100.000 se CQS+DLG entrambe con SOGECAP",
        "tfr_montante": {"tipo": "scoring", "scoring_max": None, "db": "Ses@me"},
        "coesistenze": {"dlg": 50, "pign": 50, "dlg_pign": 50,
                        "preacc_fino": None, "pign_residuo_max": None},
        "stipendio_minimo": 611.85,
        "inps_se_eta_inizio": (">=", 50),
        "interinale": "KO", "part_time": {"verticale": "OK", "misto": "VERIFICA",
                                          "orizzontale_min_perc": None},
        "cig": {"ordinaria": "KO", "straordinaria": "KO", "maltempo": "OK"},
        "cittadinanza": "UE equiparato con residenza in Italia. Extra-UE solo se presenti TUTTI: ≥ 5 anni "
                        "in Italia, ≥ 3 anni presso la stessa ATC, contratto a tempo indeterminato, salario "
                        "minimo € 1.000 netti, permesso a tempo indeterminato / lungo periodo.",
    },
    # ------------------------------------------------------------------ AMTRUST
    "AMTRUST": {
        "nome": "AmTrust / MetLife",
        "anzianita_minima_mesi": 6,
        "anzianita_massima": {"M": (44, 2, 0), "F": (43, 2, 0)},
        "anzianita_massima_adesione": None,
        "eta_massima_scadenza": (67, 11, 29),                # 67 compiuti
        "eta_massima_scadenza_durata24": None,
        "dato_combinato": None,
        "superamento": {
            "ammesso": True, "preacc": False,
            "eta_assoluta": (75, 0, 0),                      # da 75 anni e 1 giorno non assumibili
            "quota_tfr": 1.0,
            "eta_max_adesione": None,
            "pignoramento_ammesso": True,
            "nota": "Al raggiungimento dei limiti il debito residuo non deve superare il TFR disponibile "
                    "in ATC (o presso Fondo Pensione escutibile). Il TFR va attualizzato al raggiungimento "
                    "dei limiti pensionistici.",
        },
        "montante_massimo": 60000,
        "cumulo": "cumulo max € 70.000 se CQS+DLG entrambe con AM TRUST",
        "tfr_montante": {"tipo": "scoring", "scoring_max": 6, "db": "Quintohub"},
        "coesistenze": {"dlg": 40, "pign": 40, "dlg_pign": None,             # DLG+pign: preaccettazione
                        "preacc_fino": 50, "pign_residuo_max": None,
                        # nota (1) pag. 6: oltre 40% fino 50% solo se ci sono altre trattenute
                        # (assicurazioni, canone alloggio, riscatto INDAP, alimenti)
                        "preacc_solo_con_altre": True},
        "stipendio_minimo": 600,
        "inps_se_eta_inizio": (">=", 55),
        "interinale": "VERIFICA", "part_time": {"verticale": "OK", "misto": "VERIFICA",
                                                "orizzontale_min_perc": None},
        "cig": {"ordinaria": "KO", "straordinaria": "KO", "maltempo": "OK"},
        "cittadinanza": "UE/Extra-UE equiparati se presenti: ≥ 5 anni in Italia o ≥ 3 anni presso la stessa "
                        "ATC, e permesso di soggiorno a tempo indeterminato / lungo periodo (Extra-UE).",
    },
    # ------------------------------------------------------------------ AXA
    "AXA": {
        "nome": "AXA",
        "anzianita_minima_mesi": 6,
        "anzianita_massima": {"M": (44, 2, 0), "F": (43, 2, 0)},
        "anzianita_massima_adesione": None,
        "eta_massima_scadenza": (67, 11, 29),                # 67 compiuti
        "eta_massima_scadenza_durata24": None,
        "dato_combinato": None,
        "superamento": {
            "ammesso": True, "preacc": False,
            "eta_assoluta": (75, 0, 0),
            "quota_tfr": 0.8,                                # TFR disponibile in ATC diminuito del 20%
            "eta_max_adesione": None,
            "pignoramento_ammesso": True,
            "nota": "Al raggiungimento dei limiti il debito residuo non deve superare il TFR disponibile "
                    "in ATC diminuito del 20% (Fondo Pensione escutibile: 1/5 del TFR presso il Fondo).",
        },
        "montante_massimo": 75000,
        "cumulo": "cumulo max € 105.000 se CQS+DLG entrambe con AXA",
        "tfr_montante": {"tipo": "scoring", "scoring_max": None, "db": "Ses@me"},
        "coesistenze": {"dlg": 40, "pign": 40, "dlg_pign": 40,
                        "preacc_fino": 50, "pign_residuo_max": None},
        "stipendio_minimo": 500,
        "inps_se_eta_inizio": (">=", 55),
        "interinale": "KO", "part_time": {"verticale": "OK", "misto": "VERIFICA",
                                          "orizzontale_min_perc": None},
        "cig": {"ordinaria": "KO", "straordinaria": "KO", "maltempo": "OK"},
        "nota_extra": "Dipendenti di istituti bancari: età < 60 anni, oppure > 60 se all'adesione TFR > "
                      "Montante + debiti residui.",
        "cittadinanza": "UE con residenza in Italia. Extra-UE con permesso a tempo indeterminato / lungo "
                        "periodo e uno tra: ≥ 5 anni in Italia, ≥ 3 anni presso la stessa ATC.",
    },
    # ------------------------------------------------------------------ METLIFE
    "METLIFE": {
        "nome": "MetLife (Montante/TFR < 1,5)",
        "anzianita_minima_mesi": 3,
        "anzianita_massima": {"M": (42, 10, 0), "F": (41, 10, 0)},
        "anzianita_massima_adesione": None,
        "eta_massima_scadenza": (66, 5, 29),                 # 67 non compiuti
        "eta_massima_scadenza_durata24": None,
        "dato_combinato": None,
        "superamento": {"ammesso": False},
        "montante_massimo": 75000,
        "cumulo": "cumulo con delega non ammesso",
        "tfr_montante": {"tipo": "fisso", "moltiplicatore": 1.5},   # montante < 1,5 x TFR
        "coesistenze": {"dlg": 40, "pign": 40, "dlg_pign": 0,       # 0 = non ammesso
                        "preacc_fino": None, "pign_residuo_max": None},
        "stipendio_minimo": 500,
        "inps_se_eta_inizio": (">", 50),
        "interinale": "VERIFICA", "part_time": {"verticale": "KO", "misto": "VERIFICA",
                                                "orizzontale_min_perc": None},
        "cig": {"ordinaria": "OK", "straordinaria": "KO", "maltempo": "OK"},
        "cig_ordinaria_nota": "possibile procedere solo nei limiti del 30% (no pre-accettazione)",
        "cittadinanza": "UE/Extra-UE equiparati con contratto a tempo indeterminato.",
    },
    # ------------------------------------------------------------------ GREAT AMERICAN
    "GREAT_AMERICAN": {
        "nome": "Great American / MetLife",
        "anzianita_minima_mesi": 3,
        "anzianita_massima": {"M": (42, 10, 0), "F": (41, 10, 0)},
        "anzianita_massima_adesione": None,
        "eta_massima_scadenza": (66, 5, 29),                 # 67 non compiuti
        "eta_massima_scadenza_durata24": None,
        "dato_combinato": {"eta": 62, "anzianita": 38},      # età ≥ 62 e anzianità ≥ 38
        "superamento": {
            "ammesso": True, "preacc": True,                 # valutabile in pre-accettazione
            "eta_assoluta": (68, 0, 0), "anzianita_assoluta": (44, 0, 0),
            "quota_tfr": None,
            "nota": "Superamento limiti di età (max 68) / anzianità (max 44) / dato combinato: "
                    "valutabile in pre-accettazione. Richiedere conferma che non abbia fatto richiesta "
                    "di pensionamento.",
        },
        "montante_massimo": 52000,
        "cumulo": "cumulo max € 52.000 se CQS+DLG entrambe con Gaiil/MetLife",
        "tfr_montante": {"tipo": "scoring", "scoring_max": 5, "db": "All Risks"},
        "coesistenze": {"dlg": 40, "pign": 40, "dlg_pign": 0,
                        "preacc_fino": None, "pign_residuo_max": 50000},
        "stipendio_minimo": 500,
        "inps_se_eta_inizio": (">=", 50),
        "interinale": "KO", "part_time": {"verticale": "KO", "misto": "KO",
                                          "orizzontale_min_perc": 50},
        "cig": {"ordinaria": "PREACC", "straordinaria": "KO", "maltempo": "OK"},
        "cig_ordinaria_nota": "con dichiarazione ATC su ore applicate, rotazione e durata",
        "cittadinanza": "UE con residenza in Italia. Extra-UE con permesso a tempo indeterminato / lungo "
                        "periodo (non ammessa carta per Familiare UE art. 20).",
    },
    # ------------------------------------------------------------------ HDI
    "HDI": {
        "nome": "HDI Assicurazioni",
        "anzianita_minima_mesi": 10,
        "anzianita_massima": {"M": (43, 0, 0), "F": (42, 0, 0)},
        "anzianita_massima_adesione": None,
        "eta_massima_scadenza": (67, 5, 29),                 # 67 compiuti
        "eta_massima_scadenza_durata24": None,
        "dato_combinato": {"eta": 62, "anzianita": 41},
        "superamento": {
            "ammesso": True, "preacc": False,
            "eta_assoluta": (75, 0, 0),
            "quota_tfr": 1.0,
            "eta_max_adesione": None,
            "pignoramento_ammesso": True,
            "nota": "Al raggiungimento dei limiti il debito residuo non deve superare il TFR disponibile "
                    "presso l'ATC (Fondo Pensione escutibile: 1/5 del TFR presso il Fondo).",
        },
        "montante_massimo": 60000,
        "cumulo": "cumulo max € 60.000 se CQS+DLG entrambe con HDI",
        "tfr_montante": {"tipo": "hdi"},   # dipende da dimensione azienda e anzianità (pag. 1)
        "azienda_min_dipendenti": 50, "coop_min_soci": 200,
        "coesistenze": {"dlg": 0, "pign": None, "dlg_pign": 0,      # DLG non ammessa, pign senza limite %
                        "preacc_fino": None, "pign_residuo_max": None},
        "stipendio_minimo": None,
        "inps_sempre": True,
        "interinale": "KO", "part_time": {"verticale": "OK", "misto": "VERIFICA",
                                          "orizzontale_min_perc": None},
        "cig": {"ordinaria": "PREACC", "straordinaria": "KO", "maltempo": "OK"},
        "cig_ordinaria_nota": "con dichiarazione ATC su ore applicate, rotazione e durata",
        "cittadinanza": "Extra-UE con permesso di soggiorno (se 'in corso di rinnovo' serve la ricevuta).",
    },
}

# Esclusioni comuni a tutte le compagnie (pag. 9): aspettativa, sospensioni/provvedimenti
# disciplinari, contratto di apprendistato, CIG straordinaria.
