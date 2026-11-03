"""Test del report PDF e delle impostazioni dello studio."""

import tempfile
import unittest
from pathlib import Path

from verify_document import impostazioni
from verify_document.cli import analizza_documento, main
from verify_document.confronto import confronta

ESEMPI = Path(__file__).resolve().parent.parent / "esempi"

try:
    import pdfplumber
    import reportlab  # noqa: F401
    LIBRERIE = True
except ImportError:
    LIBRERIE = False


def testo_pdf(percorso) -> str:
    with pdfplumber.open(percorso) as pdf:
        return "\n".join(p.extract_text() or "" for p in pdf.pages)


@unittest.skipUnless(LIBRERIE, "servono reportlab e pdfplumber")
class TestReportPdf(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_pensionato_con_confronto_e_studio(self):
        from PIL import Image

        from verify_document.report_pdf import genera_report_pdf

        logo = self.dir / "logo.png"
        Image.new("RGB", (300, 100), "#1a5a96").save(logo)
        docs = [(p.name, analizza_documento(p)[1]) for p in sorted((ESEMPI / "pensionato").glob("*.txt"))]
        imp = {"studio": "Studio Prova S.r.l.", "indirizzo": "Via Roma 1", "contatti": "06 123456",
               "partita_iva": "12345678903", "operatore": "Mario Bianchi", "logo": str(logo),
               "note": "Nota personalizzata dello studio"}
        out = genera_report_pdf(self.dir / "r.pdf", docs, confronta(docs), imp)
        t = testo_pdf(out)
        for atteso in ("Studio Prova S.r.l.", "Report di verifica documenti", "BIANCHI GIUSEPPE",
                       "BNCGPP55A10H501F", "ESITO COMPLESSIVO: ATTENZIONE", "Sintesi dei redditi",
                       "Pensionato (nessuna partita IVA)", "€ 1.333,00", "Confronto tra i documenti",
                       "Pensione <-> CU 2025", "Dettaglio dei documenti", "Quinto cedibile",
                       "Nota personalizzata dello studio", "Mario Bianchi", "Pagina 1"):
            self.assertIn(atteso, t)
        for vietato in ("−", "→", "↔", "≈"):  # convertiti per i font standard del PDF
            self.assertNotIn(vietato, t)

    def test_senza_impostazioni_un_documento(self):
        from verify_document.report_pdf import genera_report_pdf

        docs = [("forfettario.txt", analizza_documento(ESEMPI / "modello_redditi_forfettario.txt")[1])]
        t = testo_pdf(genera_report_pdf(self.dir / "r.pdf", docs, None, {}))
        self.assertIn("Forfettario", t)
        self.assertIn("€ 1.828,33", t)
        self.assertIn("ESITO COMPLESSIVO: OK", t)
        self.assertNotIn("Confronto tra i documenti", t)

    def test_riga_di_comando(self):
        out = self.dir / "cli.pdf"
        import contextlib
        import io

        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            main([str(p) for p in sorted((ESEMPI / "confronto").glob("*.txt"))] + ["--pdf", str(out)])
        t = testo_pdf(out)
        self.assertIn("ROSSI MARIO", t)
        self.assertIn("Andamento mese per mese", t)


class TestImpostazioni(unittest.TestCase):
    def test_salva_e_carica(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "sotto" / "impostazioni.json"
            self.assertEqual(impostazioni.carica(f)["studio"], "")  # file assente -> predefinite
            impostazioni.salva({"studio": "Studio X", "sconosciuto": "ignorato"}, f)
            dati = impostazioni.carica(f)
            self.assertEqual(dati["studio"], "Studio X")
            self.assertNotIn("sconosciuto", dati)
            f.write_text("non json", encoding="utf-8")
            self.assertEqual(impostazioni.carica(f)["studio"], "")


if __name__ == "__main__":
    unittest.main()
