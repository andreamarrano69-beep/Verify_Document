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
        self.assertEqual(r.dati["nominativo"], "ROSSI MARIO", letto)  # nome sotto l'etichetta
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


class TestCuACaselle(unittest.TestCase):
    """CU con caselle numerate, descrizioni su due righe e importi sotto."""

    @classmethod
    def setUpClass(cls):
        from buste_realistiche import cu_a_caselle

        cls.tmp = tempfile.TemporaryDirectory()
        cls.cu = cu_a_caselle(Path(cls.tmp.name) / "cu.pdf")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_pdf_nativo_tutti_i_punti(self):
        from buste_realistiche import CU_ATTESI

        testo, r = analizza_documento(self.cu, autenticita=False)
        self.assertEqual(r.tipo_documento, "Certificazione Unica (CU)")
        for chiave, atteso in CU_ATTESI.items():
            atteso = atteso if isinstance(atteso, int) else Decimal(atteso)
            self.assertEqual(r.dati.get(chiave), atteso, f"{chiave}\n{testo}")
        self.assertIsNone(r.dati.get("giorni_pensione"))  # "8" è il numero della casella accanto
        k = {c.nome: c.esito for c in r.controlli}
        for controllo in ("Imposta lorda", "Imposta netta = ritenute", "Addizionale regionale",
                          "Addizionale comunale", "Contributi INPS"):
            self.assertEqual(k[controllo], Esito.OK, controllo)

    def test_imposta_lorda_alterata(self):
        from buste_realistiche import cu_a_caselle

        alterata = cu_a_caselle(Path(self.tmp.name) / "alterata.pdf", {"5.837,71": "4.900,00"})
        _, r = analizza_documento(alterata, autenticita=False)
        k = {c.nome: c.esito for c in r.controlli}
        self.assertEqual(k["Imposta lorda"], Esito.ERRORE)
        self.assertEqual(k["Imposta netta = ritenute"], Esito.ATTENZIONE)

    @unittest.skipUnless(ocr_disponibile(), "Tesseract non installato")
    def test_scansione_punti_principali(self):
        testo, r = analizza_documento(scansione(self.cu, Path(self.tmp.name) / "cu_scan.pdf"), autenticita=False)
        letto = f"\n--- testo letto ---\n{testo}"
        self.assertEqual(r.tipo_documento, "Certificazione Unica (CU)", letto)
        self.assertEqual(r.dati["codice_fiscale_dipendente"], "RSSMRA80A01H501U", letto)
        self.assertEqual(r.dati["reddito_totale"], Decimal("25381.33"), letto)
        self.assertEqual(r.dati["ritenute_irpef"], Decimal("4161.95"), letto)
        self.assertNotEqual(r.esito_globale, Esito.ERRORE, letto)


def parole_da_testo_a_colonne(testo: str, larghezza_carattere: float = 4.0, interlinea: float = 12.0):
    """Ricostruisce le parole con posizione da un testo letto dall'OCR (colonne = spazi)."""
    import re

    parole = []
    for n, riga in enumerate(testo.splitlines()):
        for m in re.finditer(r"\S+", riga):
            parole.append(Parola(m.group(0), m.start() * larghezza_carattere, m.end() * larghezza_carattere,
                                 n * interlinea, n * interlinea + 8, ocr=True))
    return parole


class TestTestiOcrReali(unittest.TestCase):
    """Testi letti dal Tesseract di Windows (versione diversa da quella di sviluppo): restano come prove fisse."""

    def test_cu_letta_su_windows(self):
        from verify_document.cli import analizza_testo
        from verify_document.layout import contesto_parole

        testo = (Path(__file__).parent / "dati" / "cu_ocr_windows.txt").read_text(encoding="utf-8")
        with contesto_parole(parole_da_testo_a_colonne(testo)):
            r = analizza_testo(testo)
        d = r.dati
        self.assertEqual(r.tipo_documento, "Certificazione Unica (CU)")
        self.assertEqual(d["codice_fiscale_dipendente"], "RSSMRA80A01H501U")  # letto "RSSMRABOAO1H501U"
        self.assertEqual(d["reddito_totale"], Decimal("25381.33"))           # "(mdeterminato)"
        self.assertIsNone(d["reddito_determinato"])                          # non contato due volte
        self.assertEqual(d["ritenute_irpef"], Decimal("4161.95"))            # "21 Ritenute" senza "Irpef"
        self.assertEqual(d["giorni_lavoro"], 365)
        self.assertEqual(d["imposta_lorda"], Decimal("5837.71"))
        self.assertEqual(d["imponibile_previdenziale"], Decimal("27950.00"))
        self.assertNotEqual(r.esito_globale, Esito.ERRORE, r.to_dict()["controlli"])


class TestBustaZucchettiMultipagina(unittest.TestCase):
    """Busta INVENTATA con l'impaginazione dei cedolini edili a più pagine (Zucchetti)."""

    @classmethod
    def setUpClass(cls):
        from buste_realistiche import busta_zucchetti_multipagina

        cls.tmp = tempfile.TemporaryDirectory()
        cls.dir = Path(cls.tmp.name)
        cls.busta = busta_zucchetti_multipagina(cls.dir / "zucchetti.pdf")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_lettura_completa(self):
        from buste_realistiche import ZUCCHETTI_ATTESI

        testo, r = analizza_documento(self.busta, autenticita=False)
        for chiave, atteso in ZUCCHETTI_ATTESI.items():
            self.assertEqual(r.dati.get(chiave), Decimal(atteso), f"{chiave}\n{testo}")
        self.assertEqual(r.dati["nominativo"], "ROSSI MARIO")   # senza etichetta: trovato con il CF
        self.assertEqual(r.dati["data_assunzione"].isoformat(), "2024-11-11")
        k = {c.nome: c for c in r.controlli}
        self.assertEqual(k["Quadratura netto"].esito, Esito.OK)
        self.assertEqual(k["Contributi INPS"].esito, Esito.OK)   # IVS sommati da 2 pagine: 9,19%
        self.assertEqual(k["Calcolo delle voci"].esito, Esito.OK)
        self.assertNotEqual(r.esito_globale, Esito.ERRORE)

    def test_voce_alterata(self):
        from buste_realistiche import busta_zucchetti_multipagina

        # retribuzione gonfiata senza rifare il calcolo tariffa × ore
        alterata = busta_zucchetti_multipagina(self.dir / "alterata.pdf", {"665,94": "865,94"})
        _, r = analizza_documento(alterata, autenticita=False)
        k = {c.nome: c for c in r.controlli}
        self.assertEqual(k["Calcolo delle voci"].esito, Esito.ERRORE)
        self.assertIn("Retribuzione edili", k["Calcolo delle voci"].dettaglio)

    def test_anonimizzazione(self):
        from verify_document.anonimizza import anonimizza

        testo, r = analizza_documento(self.busta, autenticita=False)
        a = anonimizza(testo, r)
        for dato in ("ROSSI", "MARIO", "RSSMRA80A01H501U", "01-01-1980"):
            self.assertNotIn(dato, a)
        self.assertIn("1.001,00", a)
