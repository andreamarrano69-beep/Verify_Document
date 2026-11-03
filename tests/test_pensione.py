"""Test dei documenti dei pensionati e della sintesi (regime / importo mensile)."""

import unittest
from decimal import Decimal
from pathlib import Path

from verify_document import modello_redditi, pensione
from verify_document.cli import analizza_testo, riconosci_tipo
from verify_document.confronto import confronta, confronto_testuale
from verify_document.report import Esito, report_testuale, sintesi

CARTELLA = Path(__file__).resolve().parent.parent / "esempi" / "pensionato"
MARZO = (CARTELLA / "cedolino_pensione_03_marzo_2025.txt").read_text(encoding="utf-8")
OBISM = (CARTELLA / "obism_2025.txt").read_text(encoding="utf-8")


def esiti(r):
    return {c.nome: c for c in r.controlli}


def documenti(modifiche=None):
    out = []
    for p in sorted(CARTELLA.glob("*.txt")):
        t = p.read_text(encoding="utf-8")
        for a, b in (modifiche or {}).get(p.name, []):
            assert a in t, a
            t = t.replace(a, b)
        out.append((p.name, analizza_testo(t)))
    return out


class TestCedolinoPensione(unittest.TestCase):
    def test_riconoscimento(self):
        for p in CARTELLA.glob("*.txt"):
            atteso = "cu" if p.name.startswith("cu_") else "redditi" if p.name.startswith("modello") else "pensione"
            self.assertEqual(riconosci_tipo(p.read_text(encoding="utf-8")), atteso, p.name)

    def test_cedolino(self):
        r = pensione.analizza(MARZO)
        d = r.dati
        self.assertEqual(r.tipo_documento, "Cedolino pensione")
        self.assertEqual(d["periodo"], "Marzo 2025")
        self.assertEqual(d["ente"], "INPS")
        self.assertEqual(d["categoria"], "VO")
        self.assertEqual(d["numero_pensione"], "12345678")
        self.assertEqual(d["importo_lordo"], Decimal("1850.00"))
        self.assertEqual(d["importo_netto"], Decimal("1333.00"))
        self.assertEqual(d["reddito_annuo"], Decimal("24050.00"))
        k = esiti(r)
        self.assertEqual(k["Quadratura netto"].esito, Esito.OK)
        self.assertEqual(k["Ritenuta IRPEF"].esito, Esito.OK)
        self.assertEqual(k["Cessione del quinto / prestiti"].esito, Esito.ATTENZIONE)
        self.assertIsNone(d["tredicesima"])

    def test_netto_alterato(self):
        r = pensione.analizza(MARZO.replace("Importo netto                                       1.333,00",
                                            "Importo netto                                       1.633,00"))
        self.assertEqual(esiti(r)["Quadratura netto"].esito, Esito.ERRORE)

    def test_irpef_impossibile(self):
        r = pensione.analizza(MARZO.replace("Ritenute IRPEF                                        330,00",
                                            "Ritenute IRPEF                                        630,00"))
        self.assertEqual(esiti(r)["Ritenuta IRPEF"].esito, Esito.ERRORE)

    def test_pignoramento(self):
        r = pensione.analizza(MARZO.replace("Cessione del quinto ", "Pignoramento        "))
        self.assertEqual(esiti(r)["Pignoramento"].esito, Esito.ATTENZIONE)

    def test_assegno_sociale(self):
        r = pensione.analizza(MARZO.replace("Categoria pensione: VO", "Categoria pensione: AS"))
        self.assertEqual(esiti(r)["Tipo di pensione"].esito, Esito.ATTENZIONE)
        self.assertIn("assistenziale", esiti(r)["Tipo di pensione"].dettaglio)

    def test_tredicesima(self):
        testo = MARZO.replace("Rata di MARZO", "Rata di DICEMBRE").replace(
            "Importo lordo                                       1.850,00",
            "Importo lordo                                       3.700,00\nTredicesima mensilità                               1.850,00")
        r = pensione.analizza(testo)
        self.assertTrue(r.dati["tredicesima"])
        self.assertIsNone(r.dati.get("reddito_mensile_lordo"))
        self.assertEqual(esiti(r)["Importo mensile"].esito, Esito.ATTENZIONE)

    def test_obism(self):
        r = pensione.analizza(OBISM)
        self.assertEqual(r.tipo_documento, "Certificato di pensione (ObisM)")
        self.assertEqual(r.dati["anno"], 2025)
        self.assertIsNone(r.dati["tredicesima"])  # "tredicesima a dicembre" non è una rata di tredicesima
        self.assertEqual(r.esito_globale, Esito.OK, r.to_dict())


class TestConfrontoPensionato(unittest.TestCase):
    def test_documenti_coerenti(self):
        c = confronta(documenti())
        k = esiti(c.report)
        self.assertEqual(k["Pensione: importo lordo 2025"].esito, Esito.OK, confronto_testuale(c))
        self.assertEqual(k["Pensione ↔ CU 2025"].esito, Esito.OK)
        self.assertEqual(k["CU ↔ Redditi 2025"].esito, Esito.OK)
        self.assertEqual(c.report.esito_globale, Esito.OK)

    def test_lordo_diverso_nell_anno(self):
        k = esiti(confronta(documenti({"cedolino_pensione_04_aprile_2025.txt": [
            ("Importo lordo                                       1.850,00",
             "Importo lordo                                       2.150,00"),
            ("Importo netto                                       1.333,00",
             "Importo netto                                       1.633,00")]})).report)
        self.assertEqual(k["Pensione: importo lordo 2025"].esito, Esito.ATTENZIONE)
        self.assertEqual(k["Pensione: importo netto"].esito, Esito.ATTENZIONE)

    def test_cu_non_compatibile(self):
        k = esiti(confronta(documenti({"cu_pensione_2025.txt": [("24.050,00", "31.000,00")]})).report)
        self.assertEqual(k["Pensione ↔ CU 2025"].esito, Esito.ERRORE)


class TestRegimeESintesi(unittest.TestCase):
    def test_regime_pensionato(self):
        r = modello_redditi.analizza((CARTELLA / "modello_redditi_pensionato_2025.txt").read_text(encoding="utf-8"))
        self.assertEqual(r.dati["regime_fiscale"], "Pensionato (nessuna partita IVA)")
        self.assertEqual(r.esito_globale, Esito.OK, r.to_dict())

    def test_regime_misto(self):
        testo = (CARTELLA / "modello_redditi_pensionato_2025.txt").read_text(encoding="utf-8").replace(
            "RC1 Redditi di pensione 24.050", "RC1 Redditi di pensione 14.050\nRC2 Redditi di lavoro dipendente 10.000")
        self.assertEqual(modello_redditi.analizza(testo).dati["regime_fiscale"],
                         "Lavoratore dipendente e pensionato (nessuna partita IVA)")

    def test_sintesi(self):
        s = sintesi(analizza_testo((CARTELLA.parent / "modello_redditi_forfettario.txt").read_text(encoding="utf-8")))
        self.assertEqual((s.etichetta, s.categoria), ("Regime fiscale", "Forfettario"))
        self.assertEqual((s.mensile_lordo, s.mensile_netto), (Decimal("1828.33"), Decimal("1554.08")))
        s = sintesi(pensione.analizza(MARZO))
        self.assertEqual(s.categoria, "Vecchiaia o anticipata (ex anzianità)")
        self.assertEqual(s.mensile_netto, Decimal("1333.00"))
        self.assertIn("Importo mensile netto:   € 1.333,00", report_testuale("x", pensione.analizza(MARZO)))
        self.assertIsNone(sintesi(analizza_testo((CARTELLA.parent / "carta_identita_esempio.txt")
                                                 .read_text(encoding="utf-8"))))


if __name__ == "__main__":
    unittest.main()
