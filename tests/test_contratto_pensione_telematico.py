"""Contratto e qualifica (privati e statali), decorrenza della pensione, presentazione telematica del Modello Redditi.

Tutti i dati sono inventati.
"""

import unittest
from datetime import date
from pathlib import Path

from verify_document.cli import analizza_documento, analizza_testo, riconosci_tipo
from verify_document.contratto import descrizione, leggi
from verify_document.report import Esito, sintesi
from verify_document.settori import riepilogo, stato_documenti
from verify_document.telematico import leggi as leggi_telematico, scadenza

ESEMPI = Path(__file__).resolve().parent.parent / "esempi"


def controlli(r):
    return {c.nome: c for c in r.controlli}


class TestContratto(unittest.TestCase):
    def test_busta_privata(self):
        _, r = analizza_documento(ESEMPI / "busta_paga_esempio.txt")
        d = r.dati
        self.assertEqual((d["tipo_contratto"], d["orario"], d["qualifica"], d["livello"], d["ccnl"]),
                         ("Tempo indeterminato", "Tempo pieno", "Impiegato", "4", "Commercio"))
        self.assertEqual(d["datore_di_lavoro"], "Privato")
        self.assertEqual(controlli(r)["Tipo di contratto"].esito, Esito.OK)
        self.assertIn("Lavoro dipendente privato · Tempo indeterminato", sintesi(r).categoria)

    def test_cedolino_noipa_statale(self):
        testo = """MINISTERO DELL'ISTRUZIONE E DEL MERITO - NoiPA
CEDOLINO STIPENDIO - Mese di NOVEMBRE 2026
Partita IVA: 12345678903
Cognome e nome: VERDI LUCA     Codice fiscale: VRDLCU75C15F205E
Qualifica: COLLABORATORE SCOLASTICO   Area: AS
Rapporto: TEMPO INDETERMINATO   Tempo pieno
"""
        info = leggi(testo)
        self.assertEqual(info["qualifica"], "Collaboratore scolastico")
        self.assertEqual(info["tipo_contratto"], "Tempo indeterminato")
        self.assertTrue(info["datore_pubblico"])
        r = analizza_testo(testo, "busta")
        self.assertEqual(r.dati["datore_di_lavoro"], "Pubblico")
        self.assertIn("pubblico", sintesi(r).categoria)

    def test_supplenza_docente(self):
        info = leggi("NoiPA - Ufficio scolastico\nQualifica: DOCENTE\nSupplenza annuale - data fine contratto: "
                     "30/06/2027\nPart-time verticale 50%")
        self.assertEqual(info["qualifica"], "Docente")
        self.assertTrue(info["tipo_contratto"].startswith("Tempo determinato"))
        self.assertEqual(info["data_fine_contratto"], date(2027, 6, 30))
        self.assertEqual(info["orario"], "Part-time verticale 50%")

    def test_determinato_scaduto(self):
        testo = (ESEMPI / "busta_paga_esempio.txt").read_text(encoding="utf-8").replace(
            "Contratto: Tempo indeterminato", "Contratto: Tempo determinato   Data fine contratto: 31/08/2026")
        r = analizza_testo(testo, "busta")  # busta di ottobre 2026
        c = controlli(r)["Tipo di contratto"]
        self.assertEqual(c.esito, Esito.ERRORE)
        self.assertIn("già scaduto", c.dettaglio)

    def test_apprendistato_e_descrizione(self):
        info = leggi("Qualifica: APPRENDISTA impiegato   Livello: 3\nContratto di apprendistato professionalizzante")
        self.assertEqual(info["tipo_contratto"], "Apprendistato")
        self.assertEqual(descrizione({"tipo_contratto": "Tempo indeterminato", "orario": "Part-time orizzontale 60%",
                                      "qualifica": "Operaio", "livello": "3"}),
                         "Tempo indeterminato · part-time orizzontale 60% · Operaio liv. 3")


class TestDecorrenzaPensione(unittest.TestCase):
    def test_cedolino(self):
        _, r = analizza_documento(ESEMPI / "pensionato" / "cedolino_pensione_03_marzo_2025.txt")
        d = r.dati
        self.assertEqual(d["decorrenza_pensione"], date(2019, 5, 1))
        self.assertEqual(d["in_pensione_da"], "5 anni e 10 mesi")  # alla rata di marzo 2025
        self.assertEqual(d["eta_al_pensionamento"], 64)
        self.assertIn("in pensione da 5 anni e 10 mesi", sintesi(r).nota)
        self.assertEqual(controlli(r)["Tipo di pensione"].gruppo, "Pensione")

    def test_decorrenza_dopo_il_documento(self):
        testo = (ESEMPI / "pensionato" / "cedolino_pensione_03_marzo_2025.txt").read_text(encoding="utf-8")
        r = analizza_testo(testo.replace("01/05/2019", "01/06/2025"), "pensione")
        self.assertEqual(controlli(r)["Decorrenza della pensione"].esito, Esito.ERRORE)

    def test_senza_decorrenza(self):
        testo = (ESEMPI / "pensionato" / "cedolino_pensione_03_marzo_2025.txt").read_text(encoding="utf-8")
        r = analizza_testo(testo.replace("Decorrenza pensione: 01/05/2019\n", ""), "pensione")
        self.assertEqual(controlli(r)["Decorrenza della pensione"].esito, Esito.INFO)
        self.assertIsNone(r.dati.get("in_pensione_da"))


class TestPresentazioneTelematica(unittest.TestCase):
    def test_modello_con_protocollo(self):
        _, r = analizza_documento(ESEMPI / "modello_redditi_forfettario.txt")
        self.assertEqual(r.dati["protocollo_telematico"], "26092212345678901-000001")
        self.assertEqual(controlli(r)["Data di presentazione"].esito, Esito.OK)

    def test_ricevuta_da_sola(self):
        testo = (ESEMPI / "ricevuta_redditi_esempio.txt").read_text(encoding="utf-8")
        self.assertEqual(riconosci_tipo(testo), "redditi")
        _, r = analizza_documento(ESEMPI / "ricevuta_redditi_esempio.txt")
        self.assertEqual(r.tipo_documento, "Ricevuta telematica Modello Redditi")
        self.assertEqual(r.dati["periodo_imposta"], 2025)
        self.assertEqual(r.dati["intermediario"], "12345678903")
        self.assertEqual(r.esito_globale, Esito.OK, r.to_dict()["controlli"])

    def test_senza_protocollo_e_bozza(self):
        testo = (ESEMPI / "modello_redditi_ordinario.txt").read_text(encoding="utf-8")
        r = analizza_testo("\n".join(l for l in testo.splitlines() if "Protocollo" not in l), "redditi")
        self.assertEqual(controlli(r)["Protocollo telematico"].esito, Esito.ATTENZIONE)
        self.assertIn("bozza", controlli(r)["Protocollo telematico"].dettaglio)

    def test_scartata_tardiva_omessa(self):
        base = (ESEMPI / "ricevuta_redditi_esempio.txt").read_text(encoding="utf-8")
        r = analizza_testo(base.replace("Esito: accolta", "Esito: scartata"), "redditi")
        self.assertEqual(controlli(r)["Esito della trasmissione"].esito, Esito.ERRORE)
        tardiva = base.replace("26092212345678901", "26121512345678901").replace("22/09/2026", "15/12/2026")
        self.assertIn("TARDIVA", controlli(analizza_testo(tardiva, "redditi"))["Data di presentazione"].dettaglio)
        omessa = base.replace("26092212345678901", "27030112345678901").replace("22/09/2026", "01/03/2027")
        self.assertIn("OMESSA", controlli(analizza_testo(omessa, "redditi"))["Data di presentazione"].dettaglio)

    def test_data_protocollo_diversa(self):
        info = leggi_telematico("Protocollo telematico 26092212345678901-000001 Data di presentazione: 10/10/2026")
        self.assertEqual(info["data_protocollo"], date(2026, 9, 22))
        r = analizza_testo((ESEMPI / "ricevuta_redditi_esempio.txt").read_text(encoding="utf-8")
                           .replace("22/09/2026", "10/10/2026"), "redditi")
        self.assertEqual(controlli(r)["Data nel protocollo"].esito, Esito.ATTENZIONE)

    def test_scadenze(self):
        self.assertEqual(scadenza(2022), date(2023, 11, 30))
        self.assertEqual(scadenza(2025), date(2026, 10, 31))

    def test_autonomo_ricevuta_nel_modello(self):
        _, modello = analizza_documento(ESEMPI / "modello_redditi_forfettario.txt")
        stati = {s.voce.chiave: s.stato for s in stato_documenti("Autonomo", [modello])}
        self.assertEqual(stati["ricevuta"], "completo")  # il protocollo è nel modello
        self.assertEqual(stati["redditi"], "parziale")   # ne servono 2 anni
        modello.dati["protocollo_telematico"] = None
        self.assertIn("Ricevuta telematica", riepilogo(stato_documenti("Autonomo", [modello])))


if __name__ == "__main__":
    unittest.main()
