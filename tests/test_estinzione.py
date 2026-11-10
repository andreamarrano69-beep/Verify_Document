"""Test del conteggio sommario di estinzione anticipata."""

import unittest
from datetime import date
from decimal import Decimal as D

from verify_document.estinzione import calcola, mesi_tra, tan_da_capitale, valore_attuale

OGGI = date(2026, 11, 10)


class TestEstinzione(unittest.TestCase):
    def test_mesi(self):
        self.assertEqual(mesi_tra(date(2022, 1, 1), date(2031, 12, 1)), 120)
        self.assertEqual(mesi_tra(date(2026, 11, 1), date(2026, 11, 30)), 1)

    def test_ammortamento_francese(self):
        # 10.000 € in 60 rate al 6%: rata nota 193,33
        self.assertAlmostEqual(float(valore_attuale(D("193.33"), 60, D("6"))), 10000, delta=1)
        self.assertAlmostEqual(float(tan_da_capitale(D("193.33"), 60, D("10000"))), 6.0, delta=0.01)
        self.assertEqual(valore_attuale(D("100"), 10, D("0")), D("1000"))

    def test_da_date_con_tan(self):
        c = calcola(D("300"), date(2022, 1, 1), date(2031, 12, 1), tan=D("6.5"), costi=D("1500"), data_conteggio=OGGI)
        self.assertEqual((c.rate_totali, c.rate_pagate, c.rate_residue), (120, 59, 61))
        self.assertEqual(c.montante_residuo, D("18300.00"))
        self.assertEqual(c.capitale_residuo + c.interessi_non_dovuti, c.montante_residuo)
        self.assertEqual(c.indennizzo, (c.capitale_residuo / 100).quantize(D("0.01")))  # 1%: più di 12 mesi
        self.assertEqual(c.costi_restituiti, D("762.50"))  # 1500 × 61/120
        self.assertEqual(c.totale_estinzione, c.capitale_residuo + c.indennizzo - c.costi_restituiti)
        self.assertFalse(c.avvisi)

    def test_indennizzo_mezzo_per_cento_e_soglia(self):
        c = calcola(D("900"), rate_totali=120, rate_residue=10, tan=D("7"), data_conteggio=OGGI)
        self.assertEqual(c.indennizzo, D(0))  # capitale residuo sotto 10.000 €
        c = calcola(D("2000"), rate_totali=120, rate_residue=12, tan=D("7"), data_conteggio=OGGI)
        self.assertGreater(c.capitale_residuo, 10000)
        self.assertEqual(c.indennizzo, (c.capitale_residuo * D("0.005")).quantize(D("0.01")))

    def test_rate_non_pagate(self):
        c = calcola(D("200"), date(2024, 1, 1), date(2033, 12, 1), rate_residue=100, tan=D("5"), data_conteggio=OGGI)
        self.assertEqual(c.rate_pagate, 20)
        self.assertTrue(any("non pagate" in a for a in c.avvisi))  # scadute 35

    def test_senza_tan(self):
        c = calcola(D("250"), rate_totali=120, rate_residue=80, data_conteggio=OGGI)
        self.assertEqual(c.montante_residuo, D("20000.00"))
        self.assertIsNone(c.totale_estinzione)
        self.assertIn("TAN", c.testo())

    def test_rinnovo_quinto(self):
        c = calcola(D("250"), rate_totali=120, rate_residue=80, tan=D("8"), data_conteggio=OGGI)
        self.assertTrue(any("ne mancano 8" in n for n in c.note))
        c = calcola(D("250"), rate_totali=120, rate_residue=72, tan=D("8"), data_conteggio=OGGI)
        self.assertTrue(any("Rinnovo possibile" in n for n in c.note))

    def test_errori(self):
        with self.assertRaises(ValueError):
            calcola(D("0"), rate_totali=10, rate_residue=5)
        with self.assertRaises(ValueError):
            calcola(D("100"), rate_totali=10, rate_residue=20)
        with self.assertRaises(ValueError):
            calcola(D("100"))


if __name__ == "__main__":
    unittest.main()
