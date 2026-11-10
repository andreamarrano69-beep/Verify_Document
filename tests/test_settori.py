"""Test dell'elenco dei documenti per settore."""

import unittest

from verify_document.report import Report
from verify_document.settori import SETTORI, documenti_estranei, riepilogo, stato_documenti, tipo_caricato


def doc(tipo):
    return Report(tipo)


class TestSettori(unittest.TestCase):
    def test_quattro_settori(self):
        self.assertEqual(list(SETTORI), ["Privato", "Pensionato", "Statale", "Autonomo"])
        tipi_gui = {"Busta paga", "Modello Redditi PF", "Certificazione Unica (CU)", "Pensione (cedolino / ObisM)",
                    "Estratto contributivo", "Documento d'identità"}
        for info in SETTORI.values():
            for v in info["documenti"]:
                self.assertIn(v.tipo_analisi, tipi_gui)

    def test_tipo_caricato(self):
        self.assertEqual(tipo_caricato(doc("Busta paga")), "busta")
        self.assertEqual(tipo_caricato(doc("Certificato di pensione (ObisM)")), "obism")
        self.assertEqual(tipo_caricato(doc("Cedolino pensione")), "cedolino_pensione")
        self.assertEqual(tipo_caricato(doc("Carta d'identità elettronica (CIE)")), "identita")
        self.assertIsNone(tipo_caricato(None))

    def test_privato_parziale_poi_completo(self):
        stati = {s.voce.chiave: s for s in stato_documenti("Privato", [doc("Busta paga")] * 2)}
        self.assertEqual(stati["busta"].stato, "parziale")
        self.assertEqual(stati["busta"].testo, "◐ Buste paga 2 di 3")
        self.assertEqual(stati["cu"].stato, "manca")
        self.assertEqual(stati["redditi"].stato, "facoltativo")
        docs = [doc("Busta paga")] * 3 + [doc("Certificazione Unica (CU)"), doc("Carta d'identità elettronica (CIE)")]
        testo = riepilogo(stato_documenti("Privato", docs))
        self.assertEqual(testo, "Documenti richiesti: 3 di 3 — completo ✔")

    def test_riepilogo_mancanti_e_estranei(self):
        docs = [doc("Cedolino pensione"), doc("Busta paga")]
        self.assertIn("mancano: ObisM, CU, Documento d'identità", riepilogo(stato_documenti("Pensionato", docs)))
        self.assertEqual(documenti_estranei("Pensionato", docs), ["Busta paga"])

    def test_autonomo(self):
        stati = stato_documenti("Autonomo", [doc("Modello Redditi PF (ex Unico)")])
        self.assertEqual(stati[0].testo, "◐ Unico / Redditi 1 di 2")


if __name__ == "__main__":
    unittest.main()
