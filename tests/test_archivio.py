"""Archivio dei documenti: copia per cliente, nomi, duplicati, eliminazione sicura."""

import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

from verify_document import archivio
from verify_document.cli import analizza_documento

ESEMPI = Path(__file__).resolve().parent.parent / "esempi"


class TestArchivio(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.arch = self.base / "documenti"
        self.scansioni = self.base / "Scansioni"
        self.scansioni.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def _copia_scansione(self, esempio: str, nome: str) -> Path:
        p = self.scansioni / nome
        p.write_bytes((ESEMPI / esempio).read_bytes())
        return p

    def test_copia_per_cliente_con_nome_leggibile(self):
        p = self._copia_scansione("confronto/busta_10_ottobre_2026.txt", "[Untitled]_2023012715060859.txt")
        _, r = analizza_documento(p)
        copia, nuova = archivio.archivia(p, r, self.arch)
        self.assertTrue(nuova)
        self.assertEqual(copia.parent.name, "RSSMRA80A01H501U - ROSSI MARIO")
        self.assertEqual(copia.name, "Busta paga - Ottobre 2026 - [Untitled]_2023012715060859.txt")
        self.assertTrue(p.exists())  # l'originale resta dov'era

    def test_nessun_duplicato_e_nomi_diversi(self):
        p = self._copia_scansione("confronto/busta_10_ottobre_2026.txt", "a.txt")
        _, r = analizza_documento(p)
        primo, _ = archivio.archivia(p, r, self.arch)
        secondo, nuovo = archivio.archivia(p, r, self.arch)  # stesso contenuto
        self.assertEqual(primo, secondo)
        self.assertFalse(nuovo)
        # stesso nome ma contenuto diverso -> "(2)"
        p.write_text(p.read_text(encoding="utf-8") + "\nnota", encoding="utf-8")
        terzo, nuovo = archivio.archivia(p, r, self.arch)
        self.assertTrue(nuovo)
        self.assertTrue(terzo.name.endswith("(2).txt"))

    def test_cartella_cliente_riusata_e_senza_cf(self):
        busta = self._copia_scansione("confronto/busta_08_agosto_2026.txt", "b.txt")
        cu = self._copia_scansione("cu_esempio.txt", "c.txt")
        c1, _ = archivio.archivia(busta, analizza_documento(busta)[1], self.arch)
        c2, _ = archivio.archivia(cu, analizza_documento(cu)[1], self.arch)
        self.assertEqual(c1.parent, c2.parent)  # stesso cliente RSSMRA80A01H501U
        from verify_document.report import Report

        c3, _ = archivio.archivia(busta, Report("Documento"), self.arch)
        self.assertEqual(c3.parent.name, archivio.SENZA_CF)

    def test_file_gia_in_archivio_non_ricopiato(self):
        p = self._copia_scansione("cu_esempio.txt", "c.txt")
        r = analizza_documento(p)[1]
        copia, _ = archivio.archivia(p, r, self.arch)
        di_nuovo, nuovo = archivio.archivia(copia, r, self.arch)
        self.assertEqual((di_nuovo, nuovo), (copia, False))
        self.assertEqual(len(archivio.elenco(self.arch)), 1)

    def test_elimina_solo_dentro_archivio(self):
        p = self._copia_scansione("cu_esempio.txt", "c.txt")
        copia, _ = archivio.archivia(p, analizza_documento(p)[1], self.arch)
        with self.assertRaises(ValueError):
            archivio.elimina(p, self.arch)  # originale fuori dall'archivio: mai
        with self.assertRaises(ValueError):
            archivio.elimina(self.arch, self.arch)  # l'archivio intero: mai
        with mock.patch.dict("sys.modules", {"send2trash": None}):  # senza cestino: eliminazione diretta
            dove = archivio.elimina(copia, self.arch)
        self.assertEqual(dove, "eliminato definitivamente")
        self.assertFalse(copia.exists())
        self.assertFalse(copia.parent.exists())  # cartella cliente vuota rimossa
        self.assertTrue(p.exists())

    def test_data_documento(self):
        self.assertEqual(archivio.data_documento(analizza_documento(ESEMPI / "confronto/busta_09_settembre_2026.txt")[1]),
                         date(2026, 9, 1))
        self.assertEqual(archivio.data_documento(analizza_documento(ESEMPI / "cu_esempio.txt")[1]), date(2025, 12, 31))
        self.assertEqual(archivio.descrizione_periodo(analizza_documento(ESEMPI / "cu_esempio.txt")[1]), "Anno 2025")

    def test_periodo_dal_nome(self):
        self.assertEqual(archivio.periodo_da_nome("Busta paga - Ottobre 2026 - x.pdf"), (date(2026, 10, 1), "Ottobre 2026"))
        self.assertEqual(archivio.periodo_da_nome("CU - Anno 2025 - x.pdf"), (date(2025, 12, 31), "Anno 2025"))
        self.assertEqual(archivio.periodo_da_nome("[Untitled]_2023012715060859.pdf"), (None, ""))

    def test_nome_valido_per_windows(self):
        self.assertEqual(archivio._pulisci('a:b*c?"d<e>f|g/h\\i'), "a-b-c-d-e-f-g-h-i")


if __name__ == "__main__":
    unittest.main()
