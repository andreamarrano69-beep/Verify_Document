"""Fattibilità della cessione del quinto (dati inventati)."""

import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

from verify_document.cli import analizza_documento, analizza_testo
from verify_document.fattibilita import valuta
from verify_document.report import Report

ESEMPI = Path(__file__).resolve().parent.parent / "esempi"


def busta(**dati):
    r = Report("Busta paga")
    r.dati.update({"periodo": "Ottobre 2026", "cessione_disponibile": Decimal("300"),
                   "delegazione_disponibile": Decimal("300"), "data_nascita_da_cf": date(1980, 1, 1),
                   "tipo_contratto": "Tempo indeterminato"})
    r.dati.update(dati)
    return r


class TestFattibilita(unittest.TestCase):
    def test_dipendente_indeterminato(self):
        f = valuta(busta())
        self.assertTrue(f.possibile)
        self.assertEqual(f.durata_massima, 120)
        self.assertEqual([s[0] for s in f.simulazione], [60, 84, 120])
        self.assertEqual(f.simulazione[-1][2], Decimal("36000"))   # montante 300 × 120
        self.assertLess(f.simulazione[-1][3], Decimal("36000"))    # capitale al netto degli interessi
        self.assertEqual(f.delegazione, Decimal("300"))

    def test_tempo_determinato(self):
        f = valuta(busta(tipo_contratto="Tempo determinato", data_fine_contratto=date(2029, 4, 30)))
        self.assertEqual(f.durata_massima, 30)                      # da ottobre 2026 ad aprile 2029
        self.assertEqual([s[0] for s in f.simulazione], [30])
        f = valuta(busta(tipo_contratto="Tempo determinato", data_fine_contratto=date(2027, 6, 30)))
        self.assertFalse(f.possibile)                               # 8 mesi: sotto il minimo di 24
        f = valuta(busta(tipo_contratto="Tempo determinato", data_fine_contratto=date(2026, 8, 31)))
        self.assertIn("già scaduto", f.motivi[0])
        f = valuta(busta(tipo_contratto="Tempo determinato"))
        self.assertTrue(f.durata_incerta)
        self.assertEqual(f.simulazione, [])

    def test_eta(self):
        f = valuta(busta(data_nascita_da_cf=date(1961, 5, 1)))      # 70 anni a maggio 2031
        self.assertEqual(f.durata_massima, 55)
        self.assertTrue(any("età" in n for n in f.note))

    def test_quinto_gia_impegnato(self):
        f = valuta(busta(cessione_disponibile=Decimal("0")))
        self.assertFalse(f.possibile)

    def test_pensionato_e_assegno_sociale(self):
        _, r = analizza_documento(ESEMPI / "pensionato" / "cedolino_pensione_03_marzo_2025.txt")
        f = valuta(r)
        self.assertTrue(f.possibile)
        self.assertEqual(f.durata_massima, 120)                      # 70 anni: fino a 90
        self.assertEqual(r.dati["fattibilita_quinto"], "Possibile")
        testo = (ESEMPI / "pensionato" / "cedolino_pensione_03_marzo_2025.txt").read_text(encoding="utf-8")
        r = analizza_testo(testo.replace("Categoria pensione: VO", "Categoria pensione: AS"), "pensione")
        self.assertFalse(valuta(r).possibile)
        self.assertEqual(r.dati["fattibilita_quinto"], "Non possibile")

    def test_nella_busta_analizzata(self):
        _, r = analizza_documento(ESEMPI / "busta_paga_esempio.txt")
        nomi = [c.nome for c in r.controlli if c.gruppo == "Fattibilità cessione del quinto"]
        self.assertIn("Cessione del quinto", nomi)
        self.assertIn("Importo finanziabile (stima)", nomi)

    def test_non_si_applica_ad_altri_documenti(self):
        self.assertIsNone(valuta(Report("Certificazione Unica (CU)")))


if __name__ == "__main__":
    unittest.main()
