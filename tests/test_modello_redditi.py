"""Controlli sugli importi del Modello Redditi PF (quadri RN, RE, RG, RB, RV)."""

import unittest
from pathlib import Path

from verify_document import modello_redditi
from verify_document.report import Esito

ORDINARIO = (Path(__file__).resolve().parent.parent / "esempi" / "modello_redditi_ordinario.txt").read_text(
    encoding="utf-8")


def analizza(sostituzioni=(), testo=ORDINARIO):
    for vecchio, nuovo in sostituzioni:
        assert vecchio in testo, vecchio
        testo = testo.replace(vecchio, nuovo)
    r = modello_redditi.analizza(testo)
    return {c.nome: c for c in r.controlli}, r


class TestQuadroRN(unittest.TestCase):
    def test_esempio_coerente(self):
        k, r = analizza()
        for nome in ("Quadro RE", "Reddito complessivo", "Reddito imponibile", "Imposta lorda",
                     "Imposta netta", "Imposta a debito/credito", "Cedolare secca",
                     "Addizionale regionale", "Addizionale comunale"):
            self.assertEqual(k[nome].esito, Esito.OK, f"{nome}: {k[nome].dettaglio}")

    def test_reddito_gonfiato_senza_ricalcolare_imposta(self):
        """Il falsario alza reddito e imponibile di 20.000 € ma lascia l'imposta lorda originale."""
        k, _ = analizza([("RE23 Reddito netto da lavoro autonomo 41.500", "RE23 Reddito netto da lavoro autonomo 61.500"),
                         ("RN1 Reddito complessivo 41.500", "RN1 Reddito complessivo 61.500"),
                         ("RN4 Reddito imponibile 40.000", "RN4 Reddito imponibile 60.000")])
        self.assertEqual(k["Imposta lorda"].esito, Esito.ERRORE)
        self.assertIn("€ 18.440,00", k["Imposta lorda"].dettaglio)  # IRPEF corretta su 60.000
        self.assertEqual(k["Quadro RE"].esito, Esito.ERRORE)  # 60.000 − 18.500 ≠ 61.500

    def test_imponibile_errato(self):
        k, _ = analizza([("RN4 Reddito imponibile 40.000", "RN4 Reddito imponibile 41.000")])
        self.assertEqual(k["Reddito imponibile"].esito, Esito.ERRORE)

    def test_imposta_netta_errata(self):
        k, _ = analizza([("RN26 Imposta netta 10.300", "RN26 Imposta netta 9.800")])
        self.assertEqual(k["Imposta netta"].esito, Esito.ERRORE)

    def test_saldo_non_coerente(self):
        k, _ = analizza([("RN45 Imposta a debito 800", "RN45 Imposta a debito 300")])
        self.assertEqual(k["Imposta a debito/credito"].esito, Esito.ATTENZIONE)

    def test_saldo_a_credito(self):
        k, _ = analizza([("RN33 Ritenute totali 8.000", "RN33 Ritenute totali 9.500"),
                         ("RN45 Imposta a debito 800", "RN46 Imposta a credito 700")])
        self.assertEqual(k["Imposta a debito/credito"].esito, Esito.OK)
        self.assertIn("a credito", k["Imposta a debito/credito"].dettaglio)

    def test_complessivo_diverso_dai_quadri(self):
        k, _ = analizza([("RN1 Reddito complessivo 41.500", "RN1 Reddito complessivo 45.000"),
                         ("RN4 Reddito imponibile 40.000", "RN4 Reddito imponibile 43.500")])
        self.assertEqual(k["Reddito complessivo"].esito, Esito.ATTENZIONE)

    def test_anno_senza_scaglioni(self):
        k, _ = analizza([("Periodo d'imposta 2025", "Periodo d'imposta 2019")])
        self.assertEqual(k["Imposta lorda"].esito, Esito.INFO)

    def test_scaglioni_2023(self):
        # 2023: 23% fino a 15.000, 25% fino a 28.000, 35% fino a 50.000 → 3.450 + 3.250 + 4.200 = 10.900
        k, _ = analizza([("Periodo d'imposta 2025", "Periodo d'imposta 2023"),
                         ("RN5 Imposta lorda 10.640", "RN5 Imposta lorda 10.900"),
                         ("RN26 Imposta netta 10.300", "RN26 Imposta netta 10.560"),
                         ("RN45 Imposta a debito 800", "RN45 Imposta a debito 1.060")])
        self.assertEqual(k["Imposta lorda"].esito, Esito.OK)


class TestQuadriAttivita(unittest.TestCase):
    def test_reddito_re_inferiore(self):
        k, _ = analizza([("RE20 Totale spese 18.500", "RE20 Totale spese 15.000")])
        self.assertEqual(k["Quadro RE"].esito, Esito.ATTENZIONE)

    def test_quadro_rg(self):
        testo = ORDINARIO.replace(
            """QUADRO RE - Redditi di lavoro autonomo derivanti dall'esercizio di arti e professioni
RE2 Compensi 60.000
RE20 Totale spese 18.500
RE23 Reddito netto da lavoro autonomo 41.500""",
            """QUADRO RG - Reddito di impresa in regime di contabilità semplificata
RG10 Totale componenti positivi 120.000
RG22 Totale componenti negativi {costi}
RG31 Reddito di impresa 41.500""")
        k, r = analizza(testo=testo.format(costi="78.500"))
        self.assertEqual(r.dati["regime_fiscale"], "Impresa – contabilità semplificata")
        self.assertEqual(k["Quadro RG/RF"].esito, Esito.OK)
        k, _ = analizza(testo=testo.format(costi="90.000"))
        self.assertEqual(k["Quadro RG/RF"].esito, Esito.ERRORE)  # dichiarato più dei conti


class TestCedolareAddizionali(unittest.TestCase):
    def test_cedolare_aliquota_errata(self):
        k, _ = analizza([("RB11 Imposta cedolare secca 2.016", "RB11 Imposta cedolare secca 1.440")])
        self.assertEqual(k["Cedolare secca"].esito, Esito.ERRORE)  # 15%

    def test_cedolare_10(self):
        k, _ = analizza([("RB11 Imposta cedolare secca 2.016", "RB11 Imposta cedolare secca 960")])
        self.assertEqual(k["Cedolare secca"].esito, Esito.OK)

    def test_addizionale_regionale_fuori_range(self):
        k, _ = analizza([("dovuta 692", "dovuta 2.000")])
        self.assertEqual(k["Addizionale regionale"].esito, Esito.ATTENZIONE)

    def test_addizionale_comunale_troppo_alta(self):
        k, _ = analizza([("dovuta 320", "dovuta 600")])
        self.assertEqual(k["Addizionale comunale"].esito, Esito.ATTENZIONE)


if __name__ == "__main__":
    unittest.main()
