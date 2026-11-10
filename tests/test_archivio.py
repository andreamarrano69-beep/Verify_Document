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
        self.assertEqual(copia.parent.parent.name, "ROSSI MARIO")   # cartella del cliente
        self.assertEqual(copia.parent.name, "Buste paga")              # sottocartella del prodotto
        self.assertEqual((copia.parent.parent / archivio.FILE_CF).read_text(), "RSSMRA80A01H501U")
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
        self.assertEqual(c1.parent.parent, c2.parent.parent)  # stesso cliente RSSMRA80A01H501U
        self.assertEqual((c1.parent.name, c2.parent.name), ("Buste paga", "CU"))
        from verify_document.report import Report

        c3, _ = archivio.archivia(busta, Report("Documento"), self.arch)
        self.assertEqual(c3.parent.parent.name, archivio.SENZA_CF)

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
        self.assertFalse(copia.parent.exists())          # sottocartella vuota rimossa
        self.assertFalse(copia.parent.parent.exists())   # e cartella cliente rimasta senza documenti
        self.assertTrue(p.exists())

    def test_omonimi_separati_e_nome_letto_diversamente(self):
        from verify_document.report import Report

        p = self._copia_scansione("cu_esempio.txt", "c.txt")
        r1 = Report("Certificazione Unica (CU)", {"codice_fiscale_dipendente": "RSSMRA80A01H501U",
                                                  "nominativo": "ROSSI MARIO"})
        r2 = Report("Certificazione Unica (CU)", {"codice_fiscale_dipendente": "RSSMRA85B01F205Z",
                                                  "nominativo": "ROSSI MARIO"})
        r3 = Report("Busta paga", {"codice_fiscale_dipendente": "RSSMRA80A01H501U", "nominativo": "ROSSI MARI0"})
        c1, _ = archivio.archivia(p, r1, self.arch)
        p.write_text("altro contenuto", encoding="utf-8")
        c2, _ = archivio.archivia(p, r2, self.arch)
        p.write_text("terzo contenuto", encoding="utf-8")
        c3, _ = archivio.archivia(p, r3, self.arch)
        self.assertEqual(c1.parent.parent.name, "ROSSI MARIO")
        self.assertEqual(c2.parent.parent.name, "ROSSI MARIO (RSSMRA85B01F205Z)")  # omonimo
        self.assertEqual(c3.parent.parent.name, "ROSSI MARIO")  # stesso CF: stessa cartella anche se letto male

    def test_categorie(self):
        from verify_document.report import Report

        self.assertEqual(archivio.categoria(Report("Carta d'identità elettronica")), archivio.CATEGORIA_IDENTITA)
        self.assertEqual(archivio.categoria(Report("Certificato di pensione (ObisM)")), "ObisM")
        self.assertEqual(archivio.categoria(Report("Modello Redditi PF (ex Unico)")), "Modello Redditi")

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


class TestClienteSenzaCodiceFiscale(unittest.TestCase):
    """Scansioni in cui il codice fiscale non si legge: cartella dal nome, correzione a mano, spostamento."""

    def setUp(self):
        import tempfile

        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.archivio = self.dir / "archivio"
        self.originale = self.dir / "scansione.pdf"
        self.originale.write_bytes(b"%PDF-1.4 busta di prova")

    def tearDown(self):
        self.tmp.cleanup()

    def _busta(self, nominativo=None, cf=None):
        from verify_document.report import Report

        r = Report("Busta paga")
        r.dati.update({"periodo": "Ottobre 2026", "nominativo": nominativo, "codice_fiscale_dipendente": cf})
        return r

    def test_nome_letto_senza_cf(self):
        from verify_document.archivio import archivia

        copia, _ = archivia(self.originale, self._busta("DE SANTIS MARCO"), self.archivio)
        self.assertEqual(copia.parent.parent.name, "DE SANTIS MARCO")
        self.assertEqual(copia.parent.name, "Buste paga")

    def test_nome_ocr_sbagliato_va_in_senza_cf(self):
        from verify_document.archivio import SENZA_CF, archivia, nome_valido

        for sbagliato in ("rata conv", "E NOME", "A B", "COGNOME E NOME", "12 ROSSI"):
            self.assertFalse(nome_valido(sbagliato), sbagliato)
        copia, _ = archivia(self.originale, self._busta("rata conv"), self.archivio)
        self.assertEqual(copia.parent.parent.name, SENZA_CF)

    def test_poi_arriva_il_documento_con_cf_stessa_cartella(self):
        from verify_document.archivio import FILE_CF, archivia

        archivia(self.originale, self._busta("ROSSI MARIO"), self.archivio)
        altro = self.dir / "cu.pdf"
        altro.write_bytes(b"%PDF-1.4 cu")
        copia, _ = archivia(altro, self._busta("ROSSI MARIO", "RSSMRA80A01H501U"), self.archivio)
        self.assertEqual(copia.parent.parent.name, "ROSSI MARIO")
        self.assertEqual((self.archivio / "ROSSI MARIO" / FILE_CF).read_text(), "RSSMRA80A01H501U")

    def test_correzione_a_mano_e_spostamento(self):
        from verify_document.archivio import (SENZA_CF, archivia, cartella_cliente_manuale, codice_fiscale,
                                              imposta_cliente, sposta)

        report = self._busta()
        copia, _ = archivia(self.originale, report, self.archivio)
        self.assertEqual(copia.parent.parent.name, SENZA_CF)
        imposta_cliente(report, "Rossi Mario", "rssmra80a01h501u")
        self.assertEqual(codice_fiscale(report), "RSSMRA80A01H501U")
        self.assertEqual(report.dati["nominativo"], "ROSSI MARIO")
        cartella = cartella_cliente_manuale("ROSSI MARIO", "RSSMRA80A01H501U", self.archivio)
        nuova = sposta(copia, self.archivio, cartella, "RSSMRA80A01H501U")
        self.assertEqual((nuova.parent.parent.name, nuova.parent.name), ("ROSSI MARIO", "Buste paga"))
        self.assertFalse((self.archivio / SENZA_CF).exists())  # cartella rimasta vuota: tolta
        self.assertTrue(self.originale.exists())                # l'originale non si tocca

    def test_non_sposta_in_cartella_di_altro_cf(self):
        from verify_document.archivio import archivia, sposta

        archivia(self.originale, self._busta("ROSSI MARIO", "RSSMRA80A01H501U"), self.archivio)
        altro = self.dir / "b.pdf"
        altro.write_bytes(b"%PDF-1.4 altro")
        copia, _ = archivia(altro, self._busta(), self.archivio)
        with self.assertRaises(ValueError):
            sposta(copia, self.archivio, "ROSSI MARIO", "BNCGPP55A10H501F")


class TestStoricoCliente(unittest.TestCase):
    def setUp(self):
        import tempfile

        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.archivio = self.dir / "archivio"

    def tearDown(self):
        self.tmp.cleanup()

    def _archivia(self, nome, cf, contenuto, nominativo="ROSSI MARIO"):
        from verify_document.archivio import archivia
        from verify_document.report import Report

        f = self.dir / nome
        f.write_bytes(contenuto)
        r = Report("Busta paga")
        r.dati.update({"periodo": "Ottobre 2026", "nominativo": nominativo, "codice_fiscale_dipendente": cf})
        return archivia(f, r, self.archivio)[0]

    def test_file_e_clienti_recenti(self):
        import os
        import time

        from verify_document.archivio import clienti_recenti, file_cliente

        a = self._archivia("a.pdf", "RSSMRA80A01H501U", b"a")
        self._archivia("b.pdf", "RSSMRA80A01H501U", b"b")
        c = self._archivia("c.pdf", "BNCGPP55A10H501F", b"c", "BIANCHI GIUSEPPE")
        vecchio = time.time() - 86400
        os.utime(c, (vecchio, vecchio))
        self.assertEqual(len(file_cliente(self.archivio, "ROSSI MARIO")), 2)
        recenti = clienti_recenti(self.archivio)
        self.assertEqual([r[0] for r in recenti], ["ROSSI MARIO", "BIANCHI GIUSEPPE"])
        self.assertEqual(recenti[0][2], 2)
        self.assertTrue(a.exists())

    def test_cliente_della_cartella(self):
        from verify_document.archivio import SENZA_CF, cliente_della_cartella

        copia = self._archivia("a.pdf", "RSSMRA80A01H501U", b"a")
        self.assertEqual(cliente_della_cartella(copia, self.archivio), ("ROSSI MARIO", "RSSMRA80A01H501U"))
        senza = self._archivia("s.pdf", None, b"s", "rata conv")
        self.assertEqual(senza.parent.parent.name, SENZA_CF)
        self.assertIsNone(cliente_della_cartella(senza, self.archivio))
        self.assertIsNone(cliente_della_cartella(self.dir / "fuori.pdf", self.archivio))
