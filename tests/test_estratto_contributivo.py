"""Test dell'estratto conto contributivo (dati inventati)."""

import unittest
from datetime import date
from pathlib import Path

from verify_document.cli import analizza_documento, riconosci_tipo
from verify_document.estratto_contributivo import analizza, anni_mesi, leggi_periodi
from verify_document.report import Esito

ESEMPI = Path(__file__).resolve().parent.parent / "esempi"
OGGI = date(2026, 11, 10)
CF = "VRDLCU75C15F205E"


def esiti(r):
    return {c.nome: c for c in r.controlli}


class TestEstrattoContributivo(unittest.TestCase):
    def test_esempio(self):
        nome, r = analizza_documento(ESEMPI / "estratto" / "estratto_contributivo_esempio.txt")
        self.assertEqual(r.tipo_documento, "Estratto contributivo")
        self.assertEqual(r.dati["periodi_letti"], 11)
        self.assertEqual(r.dati["somma_contributi_settimane"], 1607)
        self.assertEqual(r.dati["anzianita_contributiva"], "30 anni e 11 mesi")
        self.assertEqual(esiti(r)["Totale del documento"].esito, Esito.OK)

    def test_riconoscimento_non_confonde_gli_altri_documenti(self):
        testo = (ESEMPI / "estratto" / "estratto_contributivo_esempio.txt").read_text(encoding="utf-8")
        self.assertEqual(riconosci_tipo(testo), "estratto")
        for p in [*ESEMPI.glob("*.txt"), *(ESEMPI / "pensionato").glob("*.txt")]:
            self.assertNotEqual(riconosci_tipo(p.read_text(encoding="utf-8")), "estratto", p.name)

    def test_sovrapposizioni_non_contano_due_volte(self):
        testo = f"""ESTRATTO CONTO CONTRIBUTIVO
Codice fiscale {CF}
01/01/2020 31/12/2020 Lavoro dipendente 52 Settimane 20.000,00 ALFA SRL
01/01/2020 31/12/2020 Lavoro dipendente 30 Settimane 8.000,00 BETA SRL
01/01/2021 31/12/2021 Lavoro dipendente 52 Settimane 21.000,00 ALFA SRL
"""
        r = analizza(testo, OGGI)
        self.assertEqual(r.dati["somma_contributi_settimane"], 134)
        self.assertEqual(r.dati["anzianita_settimane"], 104)
        self.assertEqual(r.dati["anzianita_contributiva"], "2 anni")
        self.assertEqual(esiti(r)["Periodi sovrapposti"].esito, Esito.ATTENZIONE)
        self.assertEqual(esiti(r)["Anzianità contributiva (stima)"].esito, Esito.ATTENZIONE)

    def test_dipendente_pubblico_in_giorni(self):
        testo = f"""ESTRATTO CONTO CONTRIBUTIVO - Gestione dipendenti pubblici
Codice fiscale {CF}
Dal Al Cassa Giorni Retribuzione
01/09/2010 31/08/2020 CTPS Stato 3600 giorni 300.000,00 MINISTERO ISTRUZIONE
"""
        periodi = leggi_periodi(testo)
        self.assertEqual(len(periodi), 1)
        self.assertEqual(periodi[0].unita, "giorni")
        r = analizza(testo, OGGI)
        self.assertEqual(r.dati["anzianita_contributiva"], "10 anni")  # 360 giorni = 1 anno

    def test_totale_diverso_e_troppe_settimane(self):
        testo = f"""ESTRATTO CONTO CONTRIBUTIVO
Codice fiscale {CF}
01/01/2019 31/12/2019 Lavoro dipendente 52 Settimane 20.000,00 ALFA SRL
01/01/2020 30/06/2020 Lavoro dipendente 40 Settimane 9.000,00 ALFA SRL
Totale settimane: 120
"""
        r = analizza(testo, OGGI)
        self.assertEqual(esiti(r)["Totale del documento"].esito, Esito.ERRORE)
        riga_2020 = [c for c in r.controlli if c.nome == "2020"][0]
        self.assertEqual(riga_2020.esito, Esito.ATTENZIONE)
        self.assertIn("troppe", riga_2020.dettaglio)

    def test_buco_e_requisiti(self):
        testo = f"""ESTRATTO CONTO CONTRIBUTIVO
Codice fiscale {CF}
01/01/2015 31/12/2016 Lavoro dipendente 104 Settimane ALFA SRL
01/01/2019 31/12/2019 Gestione separata 12 Mesi COLLABORAZIONE
"""
        r = analizza(testo, OGGI)
        self.assertEqual(r.dati["anzianita_contributiva"], "3 anni")
        self.assertIn("2 anni", esiti(r)["Periodi senza contributi"].dettaglio)
        self.assertIn("mancano", esiti(r)["Pensione anticipata"].dettaglio)
        self.assertIn("mancano 17 anni", esiti(r)["Pensione di vecchiaia"].dettaglio)

    def test_nessun_periodo(self):
        r = analizza(f"ESTRATTO CONTO CONTRIBUTIVO\nCodice fiscale {CF}\n", OGGI)
        self.assertEqual(r.esito_globale, Esito.ERRORE)

    def test_anni_mesi(self):
        self.assertEqual(anni_mesi(52), "1 anno")
        self.assertEqual(anni_mesi(26), "6 mesi")
        self.assertEqual(anni_mesi(2227), "42 anni e 10 mesi")


if __name__ == "__main__":
    unittest.main()
