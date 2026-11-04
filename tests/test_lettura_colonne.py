"""Lettura di buste paga con valori SOTTO le etichette (colonne), PDF nativi e scansioni."""

import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from verify_document.cli import analizza_documento
from verify_document.estrazione import ocr_disponibile
from verify_document.layout import Parola, cerca_valore
from verify_document.report import Esito

from buste_realistiche import ATTESI, busta_a_colonne, scansione

ESEMPI = Path(__file__).resolve().parent.parent / "esempi"


def parole(*righe):
    """Parole finte: ogni riga è [(testo, x0)], altezza 10, righe distanziate di 14."""
    out = []
    for n, riga in enumerate(righe):
        for testo, x in riga:
            out.append(Parola(testo, x, x + 6 * len(testo), 14 * n, 14 * n + 10))
    return out


class TestRicercaPerPosizione(unittest.TestCase):
    def test_valore_nella_colonna_sotto(self):
        p = parole([("TOTALE", 0), ("COMPETENZE", 45), ("TOTALE", 150), ("TRATTENUTE", 195), ("NETTO", 300)],
                   [("2.150,00", 60), ("517,74", 210), ("1.632,00", 310)])
        self.assertEqual(cerca_valore(r"totale\s+trattenute", r"\d[\d.]*,\d{2}", p), (True, "517,74"))
        self.assertEqual(cerca_valore(r"netto", r"\d[\d.]*,\d{2}", p), (True, "1.632,00"))

    def test_stessa_riga(self):
        p = parole([("Netto", 0), ("in", 40), ("busta", 60), ("1.632,00", 200)])
        self.assertEqual(cerca_valore(r"netto\s+in\s+busta", r"\d[\d.]*,\d{2}", p), (True, "1.632,00"))

    def test_non_prende_valore_di_altro_campo(self):
        p = parole([("QUADRO", 0), ("RC", 45), ("Redditi", 70), ("di", 120), ("lavoro", 140), ("dipendente", 185)],
                   [("RC1", 0), ("Redditi", 30), ("di", 80), ("pensione", 100), ("24.050", 160)])
        self.assertEqual(cerca_valore(r"lavoro\s+dipendente", r"\d[\d.]*", p), (True, None))

    def test_etichetta_letta_male_dall_ocr(self):
        p = parole([("METTO", 0), ("DEL", 40), ("MESE", 65)], [("1.632,00", 10)])
        self.assertEqual(cerca_valore(r"netto\s+del\s+mese", r"\d[\d.]*,\d{2}", p), (True, "1.632,00"))


class TestBustaAColonne(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.nativa = busta_a_colonne(Path(cls.tmp.name) / "nativa.pdf")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def _verifica(self, percorso):
        testo, r = analizza_documento(percorso, autenticita=False)
        for chiave, atteso in ATTESI.items():
            # in caso di errore si vede il testo letto (utile perché l'OCR cambia tra versioni di Tesseract)
            self.assertEqual(r.dati.get(chiave), Decimal(atteso), f"{chiave}\n--- testo letto ---\n{testo}")
        letto = f"\n--- testo letto ---\n{testo}"
        self.assertEqual(r.dati["codice_fiscale_dipendente"], "RSSMRA80A01H501U", letto)
        self.assertEqual(r.dati["data_assunzione"].isoformat() if r.dati["data_assunzione"] else None,
                         "2019-03-01", letto)
        self.assertEqual(r.esito_globale, Esito.OK, f"{r.to_dict()['controlli']}{letto}")

    def test_pdf_nativo(self):
        self._verifica(self.nativa)

    @unittest.skipUnless(ocr_disponibile(), "Tesseract non installato")
    def test_scansione_storta_e_rumorosa(self):
        self._verifica(scansione(self.nativa, Path(self.tmp.name) / "scansione.pdf"))


class TestPdfComeTesto(unittest.TestCase):
    """Gli esempi trasformati in PDF devono dare esattamente gli stessi risultati dei file di testo."""

    def test_tutti_gli_esempi(self):
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas

        with tempfile.TemporaryDirectory() as tmp:
            for txt in sorted(ESEMPI.rglob("*.txt")):
                pdf = Path(tmp) / f"{txt.stem}.pdf"
                c = canvas.Canvas(str(pdf), pagesize=A4)
                c.setFont("Courier", 8)
                for i, riga in enumerate(txt.read_text(encoding="utf-8").splitlines()):
                    c.drawString(25, 800 - 11 * i, riga)
                c.save()
                da_testo, da_pdf = analizza_documento(txt)[1], analizza_documento(pdf, autenticita=False)[1]
                with self.subTest(esempio=txt.name):
                    self.assertEqual(da_testo.dati, da_pdf.dati)
                    self.assertEqual([(c.nome, c.esito) for c in da_testo.controlli],
                                     [(c.nome, c.esito) for c in da_pdf.controlli])


if __name__ == "__main__":
    unittest.main()
