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
        self.assertIn("mancano: Estratto contributivo", riepilogo(stato_documenti("Privato", docs)))
        testo = riepilogo(stato_documenti("Privato", docs + [doc("Estratto contributivo")]))
        self.assertEqual(testo, "Documenti richiesti: 4 di 4 — completo ✔")

    def test_riepilogo_mancanti_e_estranei(self):
        docs = [doc("Cedolino pensione"), doc("Busta paga")]
        self.assertIn("mancano: ObisM, CU, Documento d'identità, Estratto contributivo", riepilogo(stato_documenti("Pensionato", docs)))
        self.assertEqual(documenti_estranei("Pensionato", docs), ["Busta paga"])

    def test_estratto_richiesto_per_tutti(self):
        for nome, info in SETTORI.items():
            self.assertTrue(any(v.chiave == "estratto" and v.richiesto for v in info["documenti"]), nome)

    def test_autonomo(self):
        stati = stato_documenti("Autonomo", [doc("Modello Redditi PF (ex Unico)")])
        self.assertEqual(stati[0].testo, "◐ Unico / Redditi 1 di 2")


if __name__ == "__main__":
    unittest.main()


class TestRiconoscimentoSettore(unittest.TestCase):
    """Il settore si riconosce dai documenti caricati dalla Home."""

    @staticmethod
    def _docs(*percorsi):
        from pathlib import Path

        from verify_document.cli import analizza_documento

        base = Path(__file__).resolve().parent.parent / "esempi"
        return [analizza_documento(base / p)[1] for p in percorsi]

    def test_esempi(self):
        from verify_document.settori import riconosci_settore

        casi = {
            ("busta_paga_esempio.txt",): "Privato",
            ("pensionato/cedolino_pensione_03_marzo_2025.txt", "pensionato/cu_pensione_2025.txt"): "Pensionato",
            ("modello_redditi_forfettario.txt", "ricevuta_redditi_esempio.txt"): "Autonomo",
            ("cu_esempio.txt",): "Privato",
            ("estratto/estratto_contributivo_esempio.txt",): "Privato",  # soprattutto lavoro dipendente
            ("busta_paga_esempio.txt", "carta_identita_esempio.txt"): "Privato",  # l'identità non conta
        }
        for percorsi, atteso in casi.items():
            settore, motivo = riconosci_settore(self._docs(*percorsi))
            self.assertEqual(settore, atteso, (percorsi, motivo))
            self.assertTrue(motivo)

    def test_non_riconosciuto(self):
        from verify_document.settori import riconosci_settore

        settore, motivo = riconosci_settore(self._docs("carta_identita_esempio.txt"))
        self.assertIsNone(settore)
        self.assertIn("documenti d'identità", motivo)
        self.assertEqual(riconosci_settore([]), (None, riconosci_settore([None])[1]))

    def test_busta_pubblica_statale(self):
        from verify_document.report import Report
        from verify_document.settori import riconosci_settore

        r = Report("Busta paga")
        r.dati["datore_di_lavoro"] = "Pubblico"
        self.assertEqual(riconosci_settore([r])[0], "Statale")
        cu = Report("Certificazione Unica (CU)")
        cu.dati.update({"tipo_reddito": "Lavoro dipendente", "sostituto_imposta": "MINISTERO DELL'ISTRUZIONE"})
        self.assertEqual(riconosci_settore([cu])[0], "Statale")

    def test_settori_diversi_in_parita(self):
        from verify_document.settori import riconosci_settore

        settore, motivo = riconosci_settore(self._docs("busta_paga_esempio.txt",
                                                       "pensionato/cedolino_pensione_03_marzo_2025.txt"))
        self.assertIsNone(settore)
        self.assertIn("settori diversi", motivo)
