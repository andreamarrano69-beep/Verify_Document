"""
REGOLE COMPASS - CESSIONE DEL QUINTO - MEDICI CONVENZIONATI
Fonte: "Criteri Assuntivi CQS 07/2026", pagine 33-35 (aggiornamento 06/2026)
Rapporto TFR/montante: non richiesto. Coesistenze non ammesse (tranne HDI).
Stesso formato di regole_cqs_privati.py, con in più:
  quota_cedibile_perc -> la rata non può superare il quinto di questa % dello stipendio netto
  superamento tipo "quota" -> superamento ammesso solo se la rata non supera questa % del quinto
"""

REQUISITI_GENERALI = {
    "rata_max_quota": 1 / 5,
    "durata_min": 24,
    "durata_max": 120,
}

_NO_COES = {"dlg": 0, "pign": 0, "dlg_pign": 0, "preacc_fino": None, "pign_residuo_max": None}
_PT = {"verticale": "OK", "misto": "VERIFICA", "orizzontale_min_perc": None}
_CIG = {"ordinaria": "VERIFICA", "straordinaria": "VERIFICA", "maltempo": "VERIFICA"}
_BASE = {"tfr_montante": None, "coesistenze": _NO_COES, "stipendio_minimo": None, "interinale": "VERIFICA",
         "part_time": _PT, "cig": _CIG, "cittadinanza": "verificare i requisiti di cittadinanza con Compass.",
         "dato_combinato": None, "cumulo": "coesistenze non ammesse"}

COMPAGNIE = {
    "NET": dict(_BASE, **{
        "nome": "Net Insurance",
        "condizioni_azienda": "Estensione: si può usare come data di assunzione la data di laurea, con "
                              "autocertificazione che non abbia riscattato gli anni di laurea.",
        "anzianita_minima_mesi": 12,
        "anzianita_massima": {"M": (42, 10, 0), "F": (41, 10, 0)},
        "eta_massima_scadenza": (66, 5, 29),
        "superamento": {"ammesso": True, "tipo": "quota", "perc_quinto": 50, "eta_assoluta": (75, 5, 29),
                        "nota": "Superamento di età (max 75a 5m 29g) e anzianità consentito solo se la quota "
                                "cedibile non supera il 50% del quinto dello stipendio netto. Se i limiti "
                                "pensionistici sono già raggiunti alla decorrenza non si può procedere."},
        "montante_massimo": 75000,
        "montante_preacc_oltre": 50000,
        "nota_montante_preacc": "pre-accettazione + modulo adesione con intervista telefonica",
        "inps_se_eta_inizio": (">", 50),
    }),
    "CARDIF": dict(_BASE, **{
        "nome": "Cardif (BNP Paribas)",
        "anzianita_minima_mesi": 12,
        "anzianita_massima": {"M": (43, 11, 29), "F": (42, 11, 29)},
        "eta_massima_scadenza": (67, 11, 29),
        "eta_massima_scadenza_durata24": (66, 11, 29),
        "superamento": {"ammesso": False},
        "montante_massimo": 90000,
        "inps_se_eta_scadenza": (">=", 62),
    }),
    "SOGECAP": dict(_BASE, **{
        "nome": "Sogecap (Société Générale)",
        "condizioni_azienda": "Quota cedibile calcolata solo da BP: retribuzione lorda mensile − oneri "
                              "previdenziali e fiscali − altre trattenute di legge; eliminare i pazienti fino a "
                              "14 anni e/o oltre 70 anni (reddito non garantito).",
        "anzianita_minima_mesi": 12,
        "anzianita_massima": {"M": (40, 0, 0), "F": (40, 0, 0)},
        "eta_massima_scadenza": (67, 11, 29),
        "superamento": {"ammesso": False},
        "montante_massimo": 60000,
        "quota_cedibile_perc": 80,
        "inps_se_eta_inizio": (">=", 50),
    }),
    "AMTRUST": dict(_BASE, **{
        "nome": "AmTrust / MetLife",
        "anzianita_minima_mesi": 6,
        "anzianita_massima": {"M": (44, 2, 0), "F": (43, 2, 0)},
        "eta_massima_scadenza": (68, 0, 0),             # 68 compiuti, da 68 anni e 1 giorno non assumibili
        "superamento": {"ammesso": False},
        "montante_massimo": 75000,
        "inps_sempre": True,
    }),
    "AXA": dict(_BASE, **{
        "nome": "AXA",
        "anzianita_minima_mesi": 24,
        "anzianita_massima": {"M": (44, 2, 0), "F": (42, 2, 0)},
        "eta_massima_scadenza": (66, 11, 29),
        "superamento": {"ammesso": False},
        "montante_massimo": 55000,
        "montante_preacc_oltre": 49999.99,
        "nota_montante_preacc": "da € 50.000: questionario anamnestico compilato e firmato dal cedente + "
                                "pre-accettazione",
        "quota_cedibile_perc": 70,
        "inps_sempre": True,
    }),
    "GREAT_AMERICAN": dict(_BASE, **{
        "nome": "Great American / MetLife",
        "anzianita_minima_mesi": 12,
        "anzianita_massima": {"M": (40, 0, 0), "F": (40, 0, 0)},
        "eta_massima_scadenza": (65, 5, 29),
        "dato_combinato": {"eta": 62, "anzianita": 38},
        "superamento": {"ammesso": False},
        "montante_massimo": 65000,
        "montante_preacc_oltre": 55000,
        "nota_montante_preacc": "pre-accettazione",
        "quota_cedibile_perc": 80,
        "inps_se_eta_inizio": (">=", 50),
    }),
    "HDI": dict(_BASE, **{
        "nome": "HDI Assicurazioni",
        "anzianita_minima_mesi": 6,
        "anzianita_massima": {"M": (43, 0, 0), "F": (42, 0, 0)},
        "eta_massima_scadenza": (75, 5, 29),
        "superamento": {"ammesso": False},
        "montante_massimo": None,
        "sempre_preacc": "È sempre richiesta la pre-accettazione: fino a € 90.000 con 730 o Modello Unico; "
                         "oltre € 90.000 con 730/Modello Unico e questionario anamnestico.",
        "coesistenze": {"dlg": None, "pign": None, "dlg_pign": None, "preacc_fino": None,
                        "pign_residuo_max": None, "senza_limiti": True},
        "cumulo": "CQS+DLG/pignoramento ammessi senza limiti sull'importo residuo del pignoramento",
        "inps_sempre": True,
    }),
}
