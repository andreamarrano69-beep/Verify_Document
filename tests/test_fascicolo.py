"""Fascicolo cliente: documenti presenti, suggerimenti per altri controlli, esito incrociato."""

import unittest
from pathlib import Path

from verify_document.cli import analizza_documento, analizza_testo
from verify_document.confronto import fascicolo
from verify_document.report import Esito

ESEMPI = Path(__file__).resolve().parent.parent / "esempi"


def carica(*nomi):
    return [(n, analizza_documento(ESEMPI / n)[1]) for n in nomi]


class TestFascicolo(unittest.TestCase):
    def test_buste_e_identita_suggerisce_cu(self):
        docs = carica("confronto/busta_08_agosto_2026.txt", "confronto/busta_09_settembre_2026.txt",
                      "confronto/busta_10_ottobre_2026.txt", "confronto/carta_identita_rossi.txt")
        (s,) = fascicolo(docs, anno_corrente=2026)
        self.assertEqual(s.codice_fiscale, "RSSMRA80A01H501U")
        self.assertEqual(s.nominativo, "ROSSI MARIO")
        self.assertIn("Buste paga: 3 (Agosto 2026 – Ottobre 2026)", s.presenti)
        self.assertEqual(s.esito, Esito.OK)
        self.assertTrue(any(x.startswith("CU 2026") for x in s.suggerimenti))
        self.assertFalse(any("Documento d'identità" in x for x in s.suggerimenti))

    def test_una_sola_busta(self):
        (s,) = fascicolo(carica("confronto/busta_10_ottobre_2026.txt"), anno_corrente=2026)
        self.assertIsNone(s.esito)  # nessun confronto con un solo documento
        self.assertTrue(any("almeno 3 mesi" in x for x in s.suggerimenti))
        self.assertTrue(any("Documento d'identità" in x for x in s.suggerimenti))

    def test_cu_senza_buste_dello_stesso_anno(self):
        (s,) = fascicolo(carica("cu_esempio.txt"), anno_corrente=2026)
        self.assertTrue(any(x.startswith("Buste paga 2025") for x in s.suggerimenti))

    def test_buste_anno_passato_senza_cu(self):
        buste = [(p.name, analizza_testo(p.read_text(encoding="utf-8").replace(" 2026", " 2025")))
                 for p in sorted((ESEMPI / "confronto").glob("busta*.txt"))]
        (s,) = fascicolo(buste, anno_corrente=2026)
        self.assertTrue(any(x.startswith("CU 2026 (redditi 2025)") for x in s.suggerimenti))

    def test_modello_redditi_senza_cu(self):
        (s,) = fascicolo(carica("pensionato/modello_redditi_pensionato_2025.txt"), anno_corrente=2026)
        self.assertTrue(any("Modello Redditi 2025" in x for x in s.suggerimenti))

    def test_pensionato_completo(self):
        docs = [(p.name, analizza_documento(p)[1]) for p in sorted((ESEMPI / "pensionato").glob("*.txt"))]
        (s,) = fascicolo(docs, anno_corrente=2026)
        self.assertEqual(s.esito, Esito.OK)
        self.assertFalse(any(x.startswith("CU") for x in s.suggerimenti))

    def test_due_clienti(self):
        schede = fascicolo(carica("confronto/busta_10_ottobre_2026.txt", "modello_redditi_forfettario.txt"),
                           anno_corrente=2026)
        self.assertEqual({s.codice_fiscale for s in schede}, {"RSSMRA80A01H501U", "VRDGPP90E10L219Y"})


if __name__ == "__main__":
    unittest.main()
