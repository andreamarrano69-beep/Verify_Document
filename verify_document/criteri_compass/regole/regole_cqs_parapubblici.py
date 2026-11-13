"""
REGOLE COMPASS - CESSIONE DEL QUINTO - DIPENDENTI PARAPUBBLICI
Fonte: "Criteri Assuntivi CQS 07/2026", pagine 17-25 (aggiornamento 06/2026)
Stesso formato di regole_cqs_privati.py.

tfr_montante:
  esente_fino   -> sotto questo montante il rapporto TFR/montante non è richiesto
  tipo "fisso"  -> montante <= TFR x moltiplicatore
  tipo "scoring"-> montante <= TFR x scoring del DB compagnia
  preacc_fino   -> oltre la soglia e fino a questo montante: pre-accettazione se il rapporto non è rispettato
"""

REQUISITI_GENERALI = {
    "rata_max_quota": 1 / 5,
    "durata_min": 24,
    "durata_max": 120,
    # ATC "non assumibile" nel DB della compagnia: valutabile in pre-accettazione solo con TFR/Montante 1/1
    "non_assumibile_preacc_1_1": True,
}

_PT = {"verticale": "OK", "misto": "VERIFICA", "orizzontale_min_perc": None}
_NOTA_ATC_NON_ASSUMIBILE = "ATC non assumibile: valutabile in pre-accettazione solo con TFR/Montante 1/1."

COMPAGNIE = {
    "NET": {
        "nome": "Net Insurance",
        "condizioni_azienda": "DB GARF: con messaggio 'Applicare criteri parapubblici e tassi privati' caricare "
                              "con prodotto privato e criteri parapubblici. " + _NOTA_ATC_NON_ASSUMIBILE,
        "anzianita_minima_mesi": 3,
        "anzianita_massima": {"M": (42, 10, 0), "F": (41, 10, 0)},
        "eta_massima_scadenza": (66, 5, 29),
        "dato_combinato": None,
        "superamento": {
            "ammesso": True, "preacc": False, "eta_assoluta": (75, 5, 29), "quota_tfr": 1.0,
            "eta_max_adesione": (64, 11, 0), "pignoramento_ammesso": False,
            "nota": "V° pieno: al raggiungimento dei limiti il debito residuo non deve superare il TFR "
                    "disponibile presso l'ATC. Alla decorrenza non devono essere già raggiunti i requisiti "
                    "pensionistici.",
        },
        "montante_massimo": 52000,
        "montante_preacc_oltre": 50000,
        "nota_montante_preacc": "pre-accettazione + modulo adesione con intervista telefonica",
        "cumulo": "cumulo max € 75.000 se CQS+DLG entrambe con NET",
        "tfr_montante": {"tipo": "fisso", "moltiplicatore": 3, "esente_fino": 30000},
        "coesistenze": {"dlg": 40, "pign": 40, "dlg_pign": 50, "preacc_fino": None, "pign_residuo_max": None},
        "stipendio_minimo": None,
        "inps_se_eta_inizio": (">", 50),
        "interinale": "VERIFICA", "part_time": _PT,
        "cig": {"ordinaria": "VERIFICA", "straordinaria": "KO", "maltempo": "OK"},
        "cittadinanza": "UE/Extra-UE equiparati con contratto a tempo indeterminato.",
    },
    "CARDIF": {
        "codici_ammessi": ["A", "B"],
        "nome": "Cardif (BNP Paribas)",
        "condizioni_azienda": "DB Cardif: ATC categoria A o B (inserire la categoria nel modulo). "
                              + _NOTA_ATC_NON_ASSUMIBILE,
        "anzianita_minima_mesi": 3,
        "anzianita_massima": {"M": (43, 11, 29), "F": (42, 11, 29)},
        "eta_massima_scadenza": (67, 11, 29),
        "eta_massima_scadenza_durata24": (66, 11, 29),
        "dato_combinato": None,
        "superamento": {
            "ammesso": True, "preacc": False, "eta_assoluta": None, "quota_tfr": 0.75,
            "coesistenze_ammesse": False, "durata24_ammessa": False,
            "nota": "Al raggiungimento dei limiti il debito residuo non deve superare il TFR NETTO "
                    "(tassazione 25%) disponibile in ATC. Con rata ≤ 15%: età max a scadenza 69 non compiuti "
                    "(72-120 mesi) o 68 non compiuti (36-60 mesi). Non assumibili pratiche con pensionamento "
                    "previsto entro i primi 12 mesi.",
        },
        "montante_massimo": 52000,
        "cumulo": "cumulo max € 82.000 se CQS+DLG entrambe con CARDIF",
        "tfr_montante": {"tipo": "cardif_categoria", "moltiplicatore": 4,
                         "esente_fino": {"A": 40000, "B": 30000}},
        "coesistenze": {"dlg": 40, "pign": 40, "dlg_pign": 50, "preacc_fino": None, "pign_residuo_max": 50000},
        "stipendio_minimo": 550,
        "inps_se_eta_scadenza": (">=", 62),
        "interinale": "PREACC", "part_time": _PT,
        "cig": {"ordinaria": "PREACC", "straordinaria": "KO", "maltempo": "OK"},
        "cig_ordinaria_nota": "solo con TFR/Montante max 1/1 e montante max € 10.000",
        "cittadinanza": "UE/Extra-UE equiparati se presente uno tra: ≥ 5 anni in Italia; ≥ 3 anni presso la "
                        "stessa ATC; permesso a tempo indeterminato / lungo periodo. Altrimenti TFR/Montante 2/1.",
    },
    "SOGECAP": {
        "nome": "Sogecap (Société Générale)",
        "condizioni_azienda": "DB Ses@me: con 'Parificata Pubblica' usare prodotto e criteri parapubblici. "
                              + _NOTA_ATC_NON_ASSUMIBILE,
        "anzianita_minima_mesi": 6,
        "anzianita_massima": {"M": (42, 11, 29), "F": (42, 11, 29)},
        "anzianita_massima_adesione": (40, 11, 0),
        "eta_massima_scadenza": (66, 11, 29),
        "dato_combinato": None,
        "superamento": {"ammesso": False},
        "montante_massimo": 100000,
        "cumulo": "cumulo max € 100.000 se CQS+DLG entrambe con SOGECAP",
        "tfr_montante": {"tipo": "scoring", "scoring_max": None, "db": "Ses@me"},
        "coesistenze": {"dlg": 50, "pign": 50, "dlg_pign": 50, "preacc_fino": None, "pign_residuo_max": None},
        "stipendio_minimo": 611.85,
        "inps_se_eta_inizio": (">", 50),
        "interinale": "KO", "part_time": _PT,
        "cig": {"ordinaria": "KO", "straordinaria": "KO", "maltempo": "OK"},
        "cittadinanza": "UE con residenza in Italia. Extra-UE solo con TUTTI: ≥ 5 anni in Italia, ≥ 3 anni "
                        "presso la stessa ATC, contratto a tempo indeterminato, salario minimo € 1.000 netti, "
                        "permesso a tempo indeterminato / lungo periodo.",
    },
    "AMTRUST": {
        "nome": "AmTrust / MetLife",
        "condizioni_azienda": "DB Quintohub. " + _NOTA_ATC_NON_ASSUMIBILE,
        "anzianita_minima_mesi": 6,
        "anzianita_massima": {"M": (44, 2, 0), "F": (43, 2, 0)},
        "eta_massima_scadenza": (67, 11, 29),
        "dato_combinato": None,
        "superamento": {
            "ammesso": True, "preacc": False, "eta_assoluta": (75, 0, 0), "quota_tfr": 1.0,
            "pignoramento_ammesso": True,
            "nota": "Al raggiungimento dei limiti il debito residuo non deve superare il TFR disponibile in "
                    "ATC o presso il Fondo Pensione escutibile (TFR attualizzato sulla mensilità netta).",
        },
        "montante_massimo": 80000,
        "cumulo": "cumulo max € 100.000 se CQS+DLG entrambe con AMTRUST",
        "tfr_montante": {"tipo": "scoring", "scoring_max": None, "db": "Quintohub"},
        "coesistenze": {"dlg": 40, "pign": 40, "dlg_pign": None, "preacc_fino": 50,
                        "pign_residuo_max": None, "preacc_solo_con_altre": True},
        "stipendio_minimo": 600,
        "inps_se_eta_inizio": (">=", 55),
        "interinale": "VERIFICA", "part_time": _PT,
        "cig": {"ordinaria": "KO", "straordinaria": "KO", "maltempo": "OK"},
        "cittadinanza": "UE/Extra-UE equiparati se: ≥ 5 anni in Italia o ≥ 3 anni presso la stessa ATC, e "
                        "permesso a tempo indeterminato / lungo periodo (Extra-UE).",
    },
    "AXA": {
        "nome": "AXA",
        "condizioni_azienda": "DB Ses@me: con 'Parificata Pubblica' usare prodotto e criteri parapubblici. "
                              + _NOTA_ATC_NON_ASSUMIBILE + " Dipendenti MPS: età massima a scadenza 60 anni.",
        "anzianita_minima_mesi": 6,
        "anzianita_massima": {"M": (44, 2, 0), "F": (43, 2, 0)},
        "eta_massima_scadenza": (67, 11, 29),
        "dato_combinato": None,
        "superamento": {
            "ammesso": True, "preacc": False, "eta_assoluta": (75, 0, 0), "quota_tfr": 0.8,
            "pignoramento_ammesso": True,
            "nota": "Al raggiungimento dei limiti il debito residuo non deve superare il TFR disponibile in "
                    "ATC diminuito del 20% (Fondo Pensione escutibile: 1/5 del TFR presso il Fondo).",
        },
        "montante_massimo": 75000,
        "montante_preacc_oltre": 49999.99,
        "nota_montante_preacc": "da € 50.000: questionario anamnestico compilato e firmato dal cedente + "
                                "pre-accettazione",
        "cumulo": "cumulo max € 105.000 se CQS+DLG entrambe con AXA",
        "tfr_montante": {"tipo": "scoring", "scoring_max": 5, "db": "Ses@me", "esente_fino": 30000,
                         "preacc_fino": 40000},
        "coesistenze": {"dlg": 40, "pign": 40, "dlg_pign": 40, "preacc_fino": 50, "pign_residuo_max": None},
        "stipendio_minimo": 500,
        "inps_se_eta_inizio": (">=", 55),
        "interinale": "KO", "part_time": _PT,
        "cig": {"ordinaria": "KO", "straordinaria": "KO", "maltempo": "OK"},
        "cittadinanza": "UE con residenza in Italia. Extra-UE con permesso a tempo indeterminato / lungo "
                        "periodo e uno tra: ≥ 5 anni in Italia, ≥ 3 anni presso la stessa ATC.",
    },
    "GREAT_AMERICAN": {
        "nome": "Great American / MetLife",
        "condizioni_azienda": "DB All Risks. ATC non assumibili: TFR/Montante 1/1 in pre-accettazione solo con "
                              "TFR presso un Fondo Gradito, decurtato del 20%. Dipendenti postali non assumibili "
                              "se in busta paga c'è la voce 'Rec. Somme Acc.'.",
        "anzianita_minima_mesi": 3,
        "anzianita_massima": {"M": (42, 10, 0), "F": (41, 10, 0)},
        "eta_massima_scadenza": (66, 5, 29),
        "dato_combinato": {"eta": 62, "anzianita": 38},
        "superamento": {
            "ammesso": True, "preacc": True, "eta_assoluta": (68, 0, 0), "anzianita_assoluta": (44, 0, 0),
            "nota": "Superamento limiti di età (max 68) / anzianità (max 44) / dato combinato: valutabile in "
                    "pre-accettazione. Richiedere conferma che non abbia fatto richiesta di pensionamento.",
        },
        "montante_massimo": 60000,
        "cumulo": "cumulo max € 60.000 se CQS+DLG entrambe con Gaiil/MetLife",
        "tfr_montante": {"tipo": "scoring", "scoring_max": 5, "db": "All Risks", "esente_fino": 25000,
                         "esente_durata_max": 84, "esente_no_extraue": True, "esente_no_coesistenze": True,
                         "esente_anzianita_min_mesi": 6},
        "coesistenze": {"dlg": 40, "pign": 40, "dlg_pign": 0, "preacc_fino": None, "pign_residuo_max": 50000},
        "stipendio_minimo": 500,
        "inps_se_eta_inizio": (">=", 50),
        "interinale": "KO", "part_time": {"verticale": "KO", "misto": "KO", "orizzontale_min_perc": 50},
        "cig": {"ordinaria": "PREACC", "straordinaria": "KO", "maltempo": "VERIFICA"},
        "cig_ordinaria_nota": "con dichiarazione ATC su ore applicate, rotazione e durata",
        "cittadinanza": "UE con residenza in Italia. Extra-UE con permesso a tempo indeterminato / lungo "
                        "periodo (non ammessa carta per Familiare UE art. 20).",
    },
    "HDI": {
        "nome": "HDI Assicurazioni",
        "condizioni_azienda": "Società partecipate: da Enti locali almeno 40%, dallo Stato almeno 50%, da altre "
                              "aziende 100%. " + _NOTA_ATC_NON_ASSUMIBILE,
        "anzianita_minima_mesi": 6,                       # 6 mesi e un giorno (effettivi)
        "anzianita_minima_giorni_extra": 1,
        "durata_max_se_anzianita_sotto": ((6, 0, 0), 60), # fino a 5a 11m -> durata max 60 mesi
        "anzianita_massima": {"M": (43, 0, 0), "F": (42, 0, 0)},
        "eta_massima_scadenza": (67, 5, 29),
        "dato_combinato": {"eta": 62, "anzianita": 41},
        "superamento": {
            "ammesso": True, "preacc": False, "eta_assoluta": (75, 0, 0), "quota_tfr": 1.0,
            "pignoramento_ammesso": True,
            "nota": "Al raggiungimento dei limiti il debito residuo non deve superare il TFR disponibile "
                    "presso l'ATC (Fondo Pensione escutibile: 1/5 del TFR presso il Fondo).",
        },
        "montante_massimo": 60000,
        "cumulo": "cumulo max € 60.000 se CQS+DLG entrambe con HDI",
        "tfr_montante": None,                              # rapporto TFR/montante non richiesto
        "coesistenze": {"dlg": None, "pign": None, "dlg_pign": None, "preacc_fino": None,
                        "pign_residuo_max": None, "senza_limiti": True},
        "stipendio_minimo": None,
        "inps_sempre": True,
        "interinale": "KO", "part_time": _PT,
        "cig": {"ordinaria": "PREACC", "straordinaria": "KO", "maltempo": "OK"},
        "cig_ordinaria_nota": "con dichiarazione ATC su ore applicate, rotazione e durata",
        "cittadinanza": "Extra-UE con permesso di soggiorno (se 'in corso di rinnovo' serve la ricevuta).",
    },
}
