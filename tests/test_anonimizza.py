"""Testo anonimizzato da inviare per l'assistenza."""

import unittest
from pathlib import Path

from verify_document.anonimizza import anonimizza
from verify_document.cli import analizza_documento

ESEMPI = Path(__file__).resolve().parent.parent / "esempi"


class TestAnonimizza(unittest.TestCase):
    def test_toglie_dati_personali_e_lascia_importi(self):
        testo, r = analizza_documento(ESEMPI / "busta_paga_esempio.txt")
        a = anonimizza(testo + "\nIBAN IT60X0542811101000000123456\nCF OCR RSSMRA8OA01H5O1U", r)
        for dato in ("RSSMRA80A01H501U", "RSSMRA8OA01H5O1U", "ROSSI", "MARIO", "IT60X0542811101000000123456"):
            self.assertNotIn(dato, a)
        for resta in ("NETTO IN BUSTA", "1.632,00", "TOTALE TRATTENUTE", "517,74", "OTTOBRE 2026", "12345678903"):
            self.assertIn(resta, a)


class TestNettoNonTrovato(unittest.TestCase):
    def test_netto_calcolato_e_contributi_impossibili(self):
        from decimal import Decimal

        from verify_document import busta_paga
        from verify_document.report import Esito, sintesi

        testo = (ESEMPI / "busta_paga_esempio.txt").read_text(encoding="utf-8")
        testo = testo.replace("NETTO IN BUSTA                1.632,00\n", "")
        testo = testo.replace("Contributi dipendente           197,59", "Contributi dipendente           843,59")
        testo = testo.replace("1000 Contributo IVS", "1000 Voce")
        r = busta_paga.analizza(testo)
        k = {c.nome: c for c in r.controlli}
        self.assertEqual(r.dati["netto_calcolato"], Decimal("1632.00"))
        self.assertEqual(sintesi(r).mensile_netto, Decimal("1632.00"))
        self.assertIn("CALCOLATO", sintesi(r).nota)
        self.assertEqual(k["Quadratura netto"].esito, Esito.ATTENZIONE)
        self.assertEqual(k["Contributi INPS"].esito, Esito.ATTENZIONE)  # 39% impossibile: scartato
        self.assertIsNone(r.dati["contributi_dipendente"])
        self.assertNotIn("Imponibile fiscale", k)  # nessun controllo costruito su un valore sbagliato


if __name__ == "__main__":
    unittest.main()
