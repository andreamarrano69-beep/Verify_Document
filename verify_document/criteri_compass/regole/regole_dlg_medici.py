"""
REGOLE COMPASS - DELEGAZIONE DI PAGAMENTO - MEDICI CONVENZIONATI
Fonte: "Criteri Assuntivi DLG 07/2026", pagine 24-25 (aggiornamento 09/2025)
Solo Net Insurance. Delega assumibile SOLO se l'ATC non accetta cessioni del quinto
(serve dichiarazione ATC di non assumibilità della cessione). Coesistenze non ammesse.
"""

REQUISITI_GENERALI = {
    "rata_max_quota": 1 / 5,
    "durata_min": 24,
    "durata_max": 120,
    "dipendenti_minimi": None,
    "cqs_obbligatoria": False,
    "nota_settore": "Delega assumibile solo se l'ATC non accetta operazioni di cessione del quinto (serve "
                    "dichiarazione dell'ATC sulla non assumibilità della cessione).",
}

COMPAGNIE = {
    "NET": {
        "nome": "Net Insurance",
        "condizioni_azienda": "Estensione: si può usare come data di assunzione la data di laurea, con "
                              "autocertificazione che non abbia riscattato gli anni di laurea. Quota 103 valida "
                              "solo se raggiunta nel 2025.",
        "anzianita_minima_mesi": 12,
        "anzianita_massima": {"M": (42, 10, 0), "F": (41, 10, 0)},
        "eta_massima_scadenza": (66, 5, 29),
        "dato_combinato": {"eta": 62, "anzianita": 41},
        "superamento": {"ammesso": False},
        "montante_massimo": 75000,
        "montante_preacc_oltre": 50000,
        "nota_montante_preacc": "pre-accettazione + modulo adesione con intervista telefonica",
        "cumulo": "coesistenze non ammesse",
        "tfr_montante": None,
        "coesistenze": {"nessuna": True},
        "stipendio_minimo": None,
        "inps_se_eta_inizio": (">", 50),
        "interinale": "VERIFICA", "part_time": {"verticale": "OK", "misto": "VERIFICA", "orizzontale_min_perc": None},
        "cig": {"ordinaria": "VERIFICA", "straordinaria": "VERIFICA", "maltempo": "VERIFICA"},
        "cittadinanza": "UE/Extra-UE equiparati con contratto a tempo indeterminato.",
    },
}
