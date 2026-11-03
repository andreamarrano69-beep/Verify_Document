import tempfile
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

from verify_document import anagrafica, busta_paga, modello_redditi
from verify_document.cli import analizza_file, analizza_testo, riconosci_tipo
from verify_document.report import Esito
from verify_document.validators import (
    codice_cognome,
    codice_nome,
    decodifica_codice_fiscale,
    parse_importo,
    valida_codice_fiscale,
    valida_partita_iva,
)

ESEMPI = Path(__file__).resolve().parent.parent / "esempi"


def leggi(nome):
    return (ESEMPI / nome).read_text(encoding="utf-8")


def esiti(report):
    return {c.nome: c.esito for c in report.controlli}


class TestValidatori(unittest.TestCase):
    def test_codice_fiscale(self):
        self.assertTrue(valida_codice_fiscale("RSSMRA80A01H501U"))
        self.assertFalse(valida_codice_fiscale("RSSMRA80A01H501X"))
        self.assertFalse(valida_codice_fiscale("RSSMRA80A01H50"))

    def test_omocodia(self):
        # H501 -> H5L1 (0 sostituito da L); il carattere di controllo cambia
        from verify_document.validators import carattere_controllo_cf
        base = "RSSMRA80A01H5L1"
        cf = base + carattere_controllo_cf(base)
        info = decodifica_codice_fiscale(cf)
        self.assertTrue(info.valido)
        self.assertEqual(info.codice_comune, "H501")

    def test_decodifica(self):
        info = decodifica_codice_fiscale("BNCLRA85C55F205D")
        self.assertEqual(info.sesso, "F")
        self.assertEqual(info.data_nascita, date(1985, 3, 15))

    def test_codici_nome_cognome(self):
        self.assertEqual(codice_cognome("Rossi"), "RSS")
        self.assertEqual(codice_nome("Mario"), "MRA")
        self.assertEqual(codice_nome("Gianfranco"), "GFR")  # >=4 consonanti: 1a,3a,4a
        self.assertEqual(codice_cognome("Fo"), "FOX")

    def test_partita_iva(self):
        self.assertTrue(valida_partita_iva("12345678903"))
        self.assertTrue(valida_partita_iva("IT12345678903"))
        self.assertFalse(valida_partita_iva("12345678901"))
        self.assertFalse(valida_partita_iva("00000000000"))

    def test_importi(self):
        self.assertEqual(parse_importo("1.234,56"), Decimal("1234.56"))
        self.assertEqual(parse_importo("1234,56"), Decimal("1234.56"))
        self.assertEqual(parse_importo("1,234.56"), Decimal("1234.56"))
        self.assertEqual(parse_importo("42.000"), Decimal("42000"))
        self.assertEqual(parse_importo("€ 12,00-"), Decimal("-12.00"))


class TestBustaPaga(unittest.TestCase):
    def test_esempio_corretto(self):
        r = busta_paga.analizza(leggi("busta_paga_esempio.txt"))
        self.assertEqual(r.esito_globale, Esito.OK, r.to_dict())
        self.assertEqual(r.dati["netto"], Decimal("1632.00"))
        self.assertEqual(r.dati["partita_iva_azienda"], "12345678903")
        self.assertEqual(r.dati["codice_fiscale_dipendente"], "RSSMRA80A01H501U")
        self.assertEqual(r.dati["data_assunzione"], date(2019, 3, 1))

    def test_netto_sbagliato(self):
        testo = leggi("busta_paga_esempio.txt").replace("1.632,00", "1.700,00")
        r = busta_paga.analizza(testo)
        self.assertEqual(esiti(r)["Quadratura netto"], Esito.ERRORE)

    def test_piva_e_cf_errati(self):
        testo = (leggi("busta_paga_esempio.txt")
                 .replace("12345678903", "12345678901")
                 .replace("RSSMRA80A01H501U", "RSSMRA80A01H501Z"))
        r = busta_paga.analizza(testo)
        self.assertEqual(esiti(r)["P.IVA azienda"], Esito.ERRORE)
        self.assertEqual(esiti(r)["Codice fiscale dipendente"], Esito.ERRORE)

    def test_assunzione_dopo_periodo(self):
        testo = leggi("busta_paga_esempio.txt").replace("01/03/2019", "01/12/2026")
        r = busta_paga.analizza(testo)
        self.assertEqual(esiti(r)["Data assunzione"], Esito.ERRORE)

    def test_contributi_anomali(self):
        testo = leggi("busta_paga_esempio.txt").replace("Contributi dipendente           197,59",
                                                        "Contributi dipendente           300,00")
        r = busta_paga.analizza(testo)
        self.assertEqual(esiti(r)["Contributi INPS"], Esito.ATTENZIONE)


class TestModelloRedditi(unittest.TestCase):
    def test_forfettario(self):
        r = modello_redditi.analizza(leggi("modello_redditi_forfettario.txt"))
        self.assertEqual(r.dati["regime_fiscale"], "Forfettario")
        self.assertEqual(r.dati["periodo_imposta"], 2025)
        self.assertEqual(r.dati["reddito_mensile_lordo"], Decimal("1828.33"))
        self.assertEqual(r.dati["aliquota_sostitutiva_%"], Decimal("15.0"))
        self.assertEqual(r.esito_globale, Esito.OK, r.to_dict())

    def test_forfettario_coefficiente_errato(self):
        testo = leggi("modello_redditi_forfettario.txt").replace("Reddito lordo 28.140", "Reddito lordo 20.000")
        r = modello_redditi.analizza(testo)
        self.assertEqual(esiti(r)["Coefficiente di redditività"], Esito.ERRORE)

    def test_forfettario_oltre_soglia(self):
        testo = leggi("modello_redditi_forfettario.txt").replace("Componenti positivi 42.000",
                                                                 "Componenti positivi 90.000")
        r = modello_redditi.analizza(testo)
        self.assertEqual(esiti(r)["Soglia ricavi"], Esito.ATTENZIONE)

    def test_ordinario(self):
        r = modello_redditi.analizza(leggi("modello_redditi_ordinario.txt"))
        self.assertIn("Lavoro autonomo", r.dati["regime_fiscale"])
        # reddito complessivo 41.500 + affitti a cedolare secca 9.600
        self.assertEqual(r.dati["reddito_annuo"], Decimal("51100"))
        self.assertEqual(r.dati["reddito_mensile_lordo"], Decimal("4258.33"))
        # imposte: IRPEF netta 10.300 + cedolare 2.016 + addizionali 692 + 320
        self.assertEqual(r.dati["reddito_mensile_netto"], Decimal("3147.67"))
        self.assertEqual(r.esito_globale, Esito.OK, r.to_dict())


class TestAnagrafica(unittest.TestCase):
    def test_carta_identita(self):
        r = anagrafica.analizza(leggi("carta_identita_esempio.txt"), riferimento=date(2026, 11, 3))
        self.assertEqual(r.tipo_documento, "Carta d'identità elettronica")
        self.assertEqual(r.esito_globale, Esito.OK, r.to_dict())
        self.assertEqual(r.dati["cognome"], "BIANCHI")
        self.assertEqual(r.dati["nome"], "LAURA")

    def test_scaduta(self):
        r = anagrafica.analizza(leggi("carta_identita_esempio.txt"), riferimento=date(2034, 1, 1))
        self.assertEqual(esiti(r)["Scadenza documento"], Esito.ERRORE)

    def test_cf_incoerente(self):
        testo = leggi("carta_identita_esempio.txt").replace("15/03/1985", "16/03/1985")
        r = anagrafica.analizza(testo, riferimento=date(2026, 11, 3))
        self.assertEqual(esiti(r)["Coerenza CF / dati anagrafici"], Esito.ERRORE)


class TestRiconoscimento(unittest.TestCase):
    def test_tipo_automatico(self):
        self.assertEqual(riconosci_tipo(leggi("busta_paga_esempio.txt")), "busta")
        self.assertEqual(riconosci_tipo(leggi("modello_redditi_forfettario.txt")), "redditi")
        self.assertEqual(riconosci_tipo(leggi("modello_redditi_ordinario.txt")), "redditi")
        self.assertEqual(riconosci_tipo(leggi("carta_identita_esempio.txt")), "anagrafica")

    def test_pdf(self):
        """Genera un PDF reale dalla busta paga di esempio e lo analizza."""
        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.pdfgen import canvas
        except ImportError:
            self.skipTest("reportlab non installato")
        with tempfile.TemporaryDirectory() as tmp:
            pdf = Path(tmp) / "busta.pdf"
            c = canvas.Canvas(str(pdf), pagesize=A4)
            c.setFont("Courier", 9)
            y = 800
            for riga in leggi("busta_paga_esempio.txt").splitlines():
                c.drawString(30, y, riga)
                y -= 12
            c.save()
            r = analizza_file(pdf, usa_ocr=False)
            self.assertEqual(r.tipo_documento, "Busta paga")
            self.assertEqual(r.esito_globale, Esito.OK, r.to_dict())


class TestReport(unittest.TestCase):
    def test_formattazione(self):
        from verify_document.report import etichetta_campo, formatta_valore, report_testuale
        self.assertEqual(formatta_valore("netto", Decimal("1632")), "€ 1.632,00")
        self.assertEqual(formatta_valore("aliquota_%", Decimal("9.19")), "9,19%")
        self.assertEqual(formatta_valore("data", date(2019, 3, 1)), "01/03/2019")
        self.assertEqual(etichetta_campo("partita_iva_azienda"), "Partita IVA azienda")
        r = busta_paga.analizza(leggi("busta_paga_esempio.txt"))
        self.assertIn("ESITO COMPLESSIVO: ✔ OK", report_testuale("x", r))


class TestGui(unittest.TestCase):
    def test_import(self):
        try:
            import tkinter  # noqa: F401
        except ImportError:
            self.skipTest("tkinter non disponibile")
        from verify_document import gui
        self.assertIn("Busta", gui.RIEPILOGO)


if __name__ == "__main__":
    unittest.main()
