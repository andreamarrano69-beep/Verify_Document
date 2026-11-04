"""Test dell'analisi di autenticità: genera PDF originali e falsificati come farebbe un falsario."""

import io
import tempfile
import unittest
from pathlib import Path

from verify_document.autenticita import _classifica, parse_data_pdf
from verify_document.cli import analizza_file
from verify_document.report import Esito

try:
    from pypdf import PdfReader, PdfWriter
    from pypdf.annotations import FreeText
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    LIBRERIE = True
except ImportError:  # servono solo per generare i PDF di prova
    LIBRERIE = False

ESEMPIO = Path(__file__).resolve().parent.parent / "esempi" / "busta_paga_esempio.txt"
GRUPPO = "Autenticità file PDF"


def controlli_pdf(report):
    return {c.nome: c for c in report.controlli if c.gruppo == GRUPPO}


@unittest.skipUnless(LIBRERIE, "servono reportlab e pypdf per generare i PDF di prova")
class TestAutenticitaPdf(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.dir = Path(cls.tmp.name)
        cls.righe = ESEMPIO.read_text(encoding="utf-8").splitlines()
        cls.originale = cls.dir / "originale.pdf"
        cls.pos_netto = cls._disegna(cls.originale)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    @classmethod
    def _disegna(cls, percorso, netto_grassetto=False):
        c = canvas.Canvas(str(percorso), pagesize=A4)
        c.setProducer("Zucchetti HR Paghe")
        y, pos = 800, None
        for riga in cls.righe:
            c.setFont("Courier", 9)
            if "NETTO IN BUSTA" in riga:
                i = riga.index("1.632")
                pos = (30 + c.stringWidth(riga[:i], "Courier", 9), y)
                c.drawString(30, y, riga[:i])
                c.setFont("Courier-Bold" if netto_grassetto else "Courier", 9)
                c.drawString(pos[0], y, riga[i:])
            else:
                c.drawString(30, y, riga)
            y -= 12
        c.save()
        return pos

    def _sovrapponi(self, nome, font, copri, incrementale=False, metadati=None):
        ov = io.BytesIO()
        c = canvas.Canvas(ov, pagesize=A4)
        x, y = self.pos_netto
        if copri:
            c.setFillColorRGB(1, 1, 1)
            c.rect(x - 1, y - 2, 40, 11, fill=1, stroke=0)
            c.setFillColorRGB(0, 0, 0)
        c.setFont(font, 9)
        c.drawString(x, y, "1.932,00")
        c.save()
        w = PdfWriter(str(self.originale), incremental=True) if incrementale else \
            PdfWriter(clone_from=str(self.originale))
        w.pages[0].merge_page(PdfReader(ov).pages[0])
        if metadati:
            w.add_metadata(metadati)
        out = self.dir / nome
        with open(out, "wb") as f:
            w.write(f)
        return analizza_file(out, usa_ocr=False)

    def test_originale_rischio_basso(self):
        r = analizza_file(self.originale, usa_ocr=False)
        c = controlli_pdf(r)
        self.assertEqual(c["Indice di rischio alterazione"].esito, Esito.OK)
        self.assertTrue(r.dati["rischio_alterazione"].startswith("BASSO"))

    def test_netto_in_grassetto_non_e_errore(self):
        p = self.dir / "grassetto.pdf"
        self._disegna(p, netto_grassetto=True)
        c = controlli_pdf(analizza_file(p, usa_ocr=False))
        self.assertNotEqual(c["Caratteri degli importi"].esito, Esito.ERRORE)
        self.assertNotEqual(c["Indice di rischio alterazione"].esito, Esito.ERRORE)

    def test_editor_online_con_importo_riscritto(self):
        r = self._sovrapponi("editor.pdf", "Helvetica", copri=True, incrementale=True,
                             metadati={"/Producer": "iLovePDF"})
        c = controlli_pdf(r)
        self.assertEqual(c["Indice di rischio alterazione"].esito, Esito.ERRORE)
        self.assertEqual(c["Programma di creazione"].esito, Esito.ERRORE)
        self.assertEqual(c["Modifiche successive"].esito, Esito.ATTENZIONE)
        self.assertEqual(c["Caratteri degli importi"].esito, Esito.ERRORE)
        self.assertIn("1.932,00", c["Caratteri degli importi"].dettaglio)

    def test_testo_sovrapposto_stesso_font(self):
        c = controlli_pdf(self._sovrapponi("sovrapposto.pdf", "Courier", copri=False))
        self.assertEqual(c["Testo sovrapposto"].esito, Esito.ERRORE)
        self.assertIn("«6» coperto da «9»", c["Testo sovrapposto"].dettaglio)

    def test_modulo_prestampato_non_e_sovrapposizione(self):
        """Intestazioni stampate una sopra l'altra e scritte verticali (moduli Zucchetti): nessun allarme."""
        p = self.dir / "prestampato.pdf"
        c = canvas.Canvas(str(p), pagesize=A4)
        c.setProducer("Zucchetti HR Paghe")
        c.setFont("Courier", 9)
        for i, riga in enumerate(self.righe):
            c.drawString(30, 800 - 12 * i, riga)
        c.setFont("Helvetica", 6)
        c.drawString(300, 300, "Detrazioni")
        c.drawString(300, 300, "Giorni")            # due intestazioni nello stesso punto
        c.saveState()
        c.translate(15, 400)
        c.rotate(90)
        c.drawString(0, 0, "Quota da Assoggettare Inps")  # scritta verticale sul bordo
        c.drawString(0, 0, "Maggiorazione edili")
        c.restoreState()
        c.save()
        k = controlli_pdf(analizza_file(p, usa_ocr=False))
        self.assertNotIn("Testo sovrapposto", k)
        self.assertEqual(k["Indice di rischio alterazione"].esito, Esito.OK)

    def test_annotazione_e_word(self):
        w = PdfWriter(clone_from=str(self.originale))
        x, y = self.pos_netto
        w.add_annotation(0, FreeText(text="1.932,00", rect=(x, y - 2, x + 50, y + 10)))
        w.add_metadata({"/Producer": "Microsoft® Word per Microsoft 365"})
        p = self.dir / "annotazione.pdf"
        with open(p, "wb") as f:
            w.write(f)
        c = controlli_pdf(analizza_file(p, usa_ocr=False))
        self.assertEqual(c["Elementi aggiunti sopra la pagina"].esito, Esito.ERRORE)
        self.assertEqual(c["Programma di creazione"].esito, Esito.ATTENZIONE)

    def test_creato_prima_del_periodo(self):
        w = PdfWriter(clone_from=str(self.originale))
        w.add_metadata({"/CreationDate": "D:20260901100000+01'00'"})
        p = self.dir / "data.pdf"
        with open(p, "wb") as f:
            w.write(f)
        c = controlli_pdf(analizza_file(p, usa_ocr=False))
        self.assertEqual(c["Data creazione / periodo"].esito, Esito.ERRORE)


class TestFunzioni(unittest.TestCase):
    def test_data_pdf(self):
        d = parse_data_pdf("D:20261031153000+01'00'")
        self.assertEqual((d.year, d.month, d.day, d.hour), (2026, 10, 31, 14))  # in UTC
        self.assertEqual(parse_data_pdf("D:2026").year, 2026)
        self.assertIsNone(parse_data_pdf("boh"))

    def test_classifica(self):
        self.assertEqual(_classifica("iLovePDF")[1], Esito.ERRORE)
        self.assertEqual(_classifica("Zucchetti Infinity")[1], Esito.OK)
        self.assertEqual(_classifica("Microsoft® Word for Microsoft 365")[1], Esito.ATTENZIONE)
        self.assertEqual(_classifica("Microsoft: Print To PDF")[1], Esito.ATTENZIONE)
        self.assertEqual(_classifica("CamScanner")[1], Esito.INFO)
        self.assertIsNone(_classifica("Programma sconosciuto"))


if __name__ == "__main__":
    unittest.main()
