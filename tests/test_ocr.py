"""OCR di scansioni e foto (Tesseract) e messaggi quando manca."""

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from verify_document.cli import analizza_documento
from verify_document.estrazione import ISTRUZIONI_TESSERACT, ErroreEstrazione, normalizza_ocr, ocr_disponibile
from verify_document.report import Esito

ESEMPI = Path(__file__).resolve().parent.parent / "esempi"


def busta_scansionata(cartella: Path, formato: str = "pdf") -> Path:
    """Busta paga di esempio trasformata in immagine (come da scanner), salvata come PDF o JPG."""
    import pypdfium2 as pdfium
    from PIL import ImageFilter
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    nativa = cartella / "nativa.pdf"
    c = canvas.Canvas(str(nativa), pagesize=A4)
    c.setFont("Helvetica", 9)
    for i, riga in enumerate((ESEMPI / "busta_paga_esempio.txt").read_text(encoding="utf-8").splitlines()):
        c.drawString(40, 800 - 13 * i, riga)
    c.save()
    pdf = pdfium.PdfDocument(str(nativa))
    img = pdf[0].render(scale=200 / 72).to_pil().convert("L")
    pdf.close()
    img = img.rotate(0.5, fillcolor=255).filter(ImageFilter.GaussianBlur(0.6))
    out = cartella / f"scansione.{formato}"
    img.save(out, resolution=200) if formato == "pdf" else img.save(out, quality=80)
    return out


class TestNormalizzazione(unittest.TestCase):
    def test_errori_tipici(self):
        self.assertEqual(normalizza_ocr("NETTO 1.632,0O"), "NETTO 1.632,00")
        self.assertEqual(normalizza_ocr("TOTALE 2.l50,00"), "TOTALE 2.150,00")
        self.assertEqual(normalizza_ocr("IRPEF 32O,15"), "IRPEF 320,15")
        self.assertEqual(normalizza_ocr("Contributi 197, 59"), "Contributi 197,59")

    def test_non_tocca_testo_normale(self):
        for t in ("Codice fiscale RSSMRA80A01H501U", "OTTOBRE 2026", "Roma 00100", "Data 01/03/2019"):
            self.assertEqual(normalizza_ocr(t), t)


class TestCodiceFiscaleOcr(unittest.TestCase):
    def test_correzioni(self):
        from verify_document.validators import trova_codici_fiscali

        self.assertEqual(trova_codici_fiscali("CF RSSMRA8OA01H5O1U"), ["RSSMRA80A01H501U"])  # O al posto di 0
        self.assertEqual(trova_codici_fiscali("CF R5SMRA80AO1H501U"), ["RSSMRA80A01H501U"])  # 5/S e O/0
        self.assertEqual(trova_codici_fiscali("CF RSSMRA80A01 H501U"), ["RSSMRA80A01H501U"])  # spezzato
        # un CF scritto bene ma con controllo errato resta così (va segnalato come errore)
        self.assertEqual(trova_codici_fiscali("CF RSSMRA80A01H501X"), ["RSSMRA80A01H501X"])
        self.assertEqual(trova_codici_fiscali("ABCDEFGHIJKLMNOP"), [])  # 16 lettere qualsiasi: niente


class TestCodiceFiscaleLetteraSbagliata(unittest.TestCase):
    BUSTA = (ESEMPI / "busta_paga_esempio.txt").read_text(encoding="utf-8").replace("RSSMRA80A01H501U", "RSSNRA80A01H501U")

    def test_correzione_lettere_simili(self):
        from verify_document.validators import correggi_cf_letto

        self.assertEqual(correggi_cf_letto("RSSNRA80A01H501U", "ROSSI MARIO"), "RSSMRA80A01H501U")  # N/M
        self.assertEqual(correggi_cf_letto("RSSMRA80A01H501V", "ROSSI MARIO"), "RSSMRA80A01H501U")  # V/U
        self.assertIsNone(correggi_cf_letto("RSSMRA8OA01N501U"))  # due errori: non si indovina
        self.assertIsNone(correggi_cf_letto("RSSMRA80A01H501U"))  # già valido

    def test_scansione_corretta_con_avviso(self):
        from verify_document import busta_paga
        from verify_document.layout import Parola, contesto_parole

        with contesto_parole([Parola("x", 0, 1, 0, 1, ocr=True)]):
            r = busta_paga.analizza(self.BUSTA)
        k = {c.nome: c for c in r.controlli}
        self.assertEqual(r.dati["codice_fiscale_dipendente"], "RSSMRA80A01H501U")
        self.assertEqual(k["Codice fiscale corretto (OCR)"].esito, Esito.ATTENZIONE)
        self.assertIn("«N»→«M»", k["Codice fiscale corretto (OCR)"].dettaglio)
        self.assertEqual(k["Codice fiscale dipendente"].esito, Esito.OK)

    def test_pdf_nativo_resta_errore(self):
        from verify_document import busta_paga

        r = busta_paga.analizza(self.BUSTA)  # testo non da OCR: un CF sbagliato è un errore vero
        k = {c.nome: c for c in r.controlli}
        self.assertEqual(k["Codice fiscale dipendente"].esito, Esito.ERRORE)
        self.assertNotIn("Codice fiscale corretto (OCR)", k)


class TestSenzaTesseract(unittest.TestCase):
    def test_messaggio_con_istruzioni(self):
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch("verify_document.estrazione.trova_tesseract", return_value=(None, "")):
            pdf = busta_scansionata(Path(tmp))
            with self.assertRaises(ErroreEstrazione) as ctx:
                analizza_documento(pdf)
            self.assertEqual(str(ctx.exception), ISTRUZIONI_TESSERACT)
            self.assertIn("UB-Mannheim", str(ctx.exception))


@unittest.skipUnless(ocr_disponibile(), "Tesseract non installato")
class TestOcr(unittest.TestCase):
    def _verifica(self, formato):
        with tempfile.TemporaryDirectory() as tmp:
            _, r = analizza_documento(busta_scansionata(Path(tmp), formato))
        k = {c.nome: c for c in r.controlli}
        self.assertEqual(r.tipo_documento, "Busta paga")
        self.assertEqual(k["Quadratura netto"].esito, Esito.OK, k["Quadratura netto"].dettaglio)
        self.assertEqual(r.dati["codice_fiscale_dipendente"], "RSSMRA80A01H501U")
        self.assertEqual(r.dati["partita_iva_azienda"], "12345678903")
        return r

    def test_pdf_scansionato(self):
        r = self._verifica("pdf")
        self.assertIn("Tipo di PDF", {c.nome for c in r.controlli})  # segnalato come scansione

    def test_foto_jpg(self):
        self._verifica("jpg")


if __name__ == "__main__":
    unittest.main()
