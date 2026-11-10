"""Scheda del cliente per settore (report PDF). Documenti inventati."""

import unittest
from pathlib import Path

from verify_document.cli import analizza_documento
from verify_document.confronto import confronta
from verify_document.scheda import scheda_cliente

ESEMPI = Path(__file__).resolve().parent.parent / "esempi"


def docs(cartella):
    return [(p.name, analizza_documento(p)[1]) for p in sorted((ESEMPI / cartella).glob("*.txt"))]


class TestScheda(unittest.TestCase):
    def test_privato_con_estratto(self):
        d = docs("confronto_inps")
        settore, righe = scheda_cliente(d, confronta(d))
        r = dict(righe)
        self.assertEqual(settore, "Privato")
        self.assertIn("Buste paga (1 di 3)", r["Documenti mancanti"])
        self.assertEqual(r["Datore di lavoro"], "ESEMPIO SRL")
        self.assertIn("Tempo indeterminato", r["Contratto"])
        self.assertIn("anzianità di servizio 7 anni", r["Assunzione"])
        self.assertIn("4 coerenti", r["Controlli con INPS / Agenzia"])
        self.assertTrue(r["Cessione del quinto"].startswith("possibile"))

    def test_pensionato_usa_il_cedolino(self):
        d = docs("pensionato")
        settore, righe = scheda_cliente(d, confronta(d))
        r = dict(righe)
        self.assertEqual(settore, "Pensionato")
        self.assertIn("01/05/2019", r["Decorrenza"])
        self.assertIn("146,60", r["Cessione del quinto"])  # cedolino con cessione in corso, non l'ObisM
        self.assertIn("manca l'estratto", r["Controlli con INPS"])

    def test_settore_scelto_e_autonomo(self):
        d = [("unico", analizza_documento(ESEMPI / "modello_redditi_forfettario.txt")[1])]
        settore, righe = scheda_cliente(d, None, "Autonomo")
        r = dict(righe)
        self.assertEqual(r["Settore"], "Autonomo")
        self.assertEqual(r["Regime fiscale"], "Forfettario")
        self.assertIn("26092212345678901", r["Presentazione telematica"])

    def test_pdf_contiene_la_scheda(self):
        import tempfile

        import pdfplumber

        from verify_document.report_pdf import genera_report_pdf

        d = docs("confronto_inps")
        with tempfile.TemporaryDirectory() as tmp:
            out = genera_report_pdf(Path(tmp) / "r.pdf", d, confronta(d), {})
            with pdfplumber.open(out) as pdf:
                testo = "\n".join(p.extract_text() or "" for p in pdf.pages)
        self.assertIn("Scheda del cliente - Privato", testo)
        self.assertIn("Cessione del quinto", testo)
        self.assertNotIn("<b>", testo)
        self.assertNotIn("RSSMRA80A01H501U", testo)  # dati oscurati


if __name__ == "__main__":
    unittest.main()
