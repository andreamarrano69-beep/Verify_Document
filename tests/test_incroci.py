"""Controlli incrociati con l'estratto contributivo e la ricevuta telematica (documenti INVENTATI)."""

import unittest
from pathlib import Path

from verify_document.cli import analizza_documento, analizza_testo
from verify_document.confronto import confronta
from verify_document.incroci import stesso_nome
from verify_document.report import Esito

ESEMPI = Path(__file__).resolve().parent.parent / "esempi"
CARTELLA = ESEMPI / "confronto_inps"


def leggi(nome):
    return (CARTELLA / nome).read_text(encoding="utf-8")


def esiti(documenti):
    return {c.nome: c for c in confronta(documenti).report.controlli}


class TestIncrociEstratto(unittest.TestCase):
    def setUp(self):
        self.docs = {p.name: analizza_documento(p)[1] for p in CARTELLA.glob("*.txt")}

    def _con(self, **sostituzioni):
        docs = dict(self.docs)
        for nome, (tipo, testo) in sostituzioni.items():
            docs[nome] = analizza_testo(testo, tipo)
        return esiti(list(docs.items()))

    def test_documenti_coerenti(self):
        c = esiti(list(self.docs.items()))
        for nome in ("Assunzione ↔ estratto", "Buste paga ↔ estratto", "Datore di lavoro ↔ estratto",
                     "CU 2025 ↔ estratto"):
            self.assertEqual(c[nome].esito, Esito.OK, (nome, c[nome].dettaglio))
        self.assertEqual(c["Mesi recenti"].esito, Esito.INFO)  # ottobre dopo l'aggiornamento dell'estratto

    def test_cu_senza_contributi_nell_anno(self):
        estratto = "\n".join(r for r in leggi("estratto_rossi.txt").splitlines() if "01/01/2025" not in r)
        c = self._con(**{"estratto_rossi.txt": ("estratto", estratto)})
        self.assertEqual(c["CU 2025 ↔ estratto"].esito, Esito.ERRORE)
        self.assertIn("non ha contributi", c["CU 2025 ↔ estratto"].dettaglio)

    def test_cu_con_imponibile_gonfiato(self):
        cu = leggi("cu_rossi_2025.txt").replace("27.950,00", "39.950,00")
        c = self._con(**{"cu_rossi_2025.txt": ("cu", cu)})
        self.assertEqual(c["CU 2025 ↔ estratto"].esito, Esito.ERRORE)

    def test_busta_di_un_mese_senza_contributi(self):
        estratto = leggi("estratto_rossi.txt").replace("01/01/2026   30/09/2026", "01/01/2026   31/07/2026")
        c = self._con(**{"estratto_rossi.txt": ("estratto", estratto)})
        self.assertEqual(c["Buste paga ↔ estratto"].esito, Esito.ERRORE)
        self.assertIn("Agosto 2026", c["Buste paga ↔ estratto"].dettaglio)

    def test_assunzione_non_registrata_e_altro_datore(self):
        estratto = leggi("estratto_rossi.txt").replace("ESEMPIO SRL", "GAMMA LOGISTICA SPA").replace(
            "01/03/2019   31/12/2024   Lavoro dipendente", "01/06/2019   31/12/2024   Lavoro dipendente").replace(
            "01/09/2005   28/02/2019", "01/09/2005   31/12/2018")
        c = self._con(**{"estratto_rossi.txt": ("estratto", estratto)})
        self.assertEqual(c["Assunzione ↔ estratto"].esito, Esito.ERRORE)
        self.assertEqual(c["Datore di lavoro ↔ estratto"].esito, Esito.ATTENZIONE)

    def test_nomi_aziende(self):
        self.assertTrue(stesso_nome("ESEMPIO SRL", "Esempio S.r.l."))
        self.assertFalse(stesso_nome("ESEMPIO SRL", "GAMMA SPA"))
        self.assertIsNone(stesso_nome("SRL", "GAMMA SPA"))


class TestIncrociAutonomoEPensione(unittest.TestCase):
    CF = "VRDGPP90E10L219Y"

    def test_autonomo_senza_contributi_e_con(self):
        modello = analizza_documento(ESEMPI / "modello_redditi_forfettario.txt")[1]
        base = f"""ESTRATTO CONTO CONTRIBUTIVO
Codice fiscale {self.CF}
Aggiornato al: 30/06/2026
01/01/2024 31/12/2025 Lavoro dipendente 104 Settimane 50.000,00 ALFA SRL
"""
        c = esiti([("unico", modello), ("estratto", analizza_testo(base, "estratto"))])
        self.assertEqual(c["Redditi 2025 ↔ estratto"].esito, Esito.ATTENZIONE)
        con = base + "01/01/2025 31/12/2025 Gestione separata 12 Mesi 21.940,00 COMMITTENTI VARI\n"
        c = esiti([("unico", modello), ("estratto", analizza_testo(con, "estratto"))])
        self.assertEqual(c["Redditi 2025 ↔ estratto"].esito, Esito.OK)

    def test_ricevuta_con_altro_protocollo(self):
        modello = analizza_documento(ESEMPI / "modello_redditi_forfettario.txt")[1]
        ricevuta = (ESEMPI / "ricevuta_redditi_esempio.txt").read_text(encoding="utf-8")
        c = esiti([("unico", modello), ("ricevuta", analizza_testo(ricevuta, "redditi"))])
        self.assertEqual(c["Modello Redditi 2025 ↔ ricevuta"].esito, Esito.OK)
        altra = ricevuta.replace("26092212345678901", "26092299999999999")
        c = esiti([("unico", modello), ("ricevuta", analizza_testo(altra, "redditi"))])
        self.assertEqual(c["Modello Redditi 2025 ↔ ricevuta"].esito, Esito.ERRORE)

    def test_pensione_anticipata_con_pochi_contributi_e_lavoro_dopo(self):
        cedolino = analizza_documento(ESEMPI / "pensionato" / "cedolino_pensione_03_marzo_2025.txt")[1]
        estratto = """ESTRATTO CONTO CONTRIBUTIVO
Codice fiscale BNCGPP55A10H501F
Aggiornato al: 31/12/2024
01/01/1990 30/04/2019 Lavoro dipendente 1530 Settimane 900.000,00 ALFA SRL
01/01/2023 31/12/2024 Lavoro dipendente 104 Settimane 30.000,00 BETA SRL
"""
        c = esiti([("cedolino", cedolino), ("estratto", analizza_testo(estratto, "estratto"))])
        p = c["Pensione ↔ estratto"]
        self.assertEqual(p.esito, Esito.ATTENZIONE)  # 64 anni con circa 29 anni di contributi
        self.assertIn("canali particolari", p.dettaglio)
        self.assertIn("dopo la pensione", p.dettaglio)


if __name__ == "__main__":
    unittest.main()
