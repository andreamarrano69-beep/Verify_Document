"""Test del confronto tra documenti dello stesso cliente."""

import unittest
from pathlib import Path

from verify_document.cli import analizza_testo
from verify_document.confronto import confronta, confronto_testuale
from verify_document.report import Esito

CARTELLA = Path(__file__).resolve().parent.parent / "esempi" / "confronto"


def carica(modifiche=None, solo_buste=False):
    """Restituisce [(nome, testo)] della cartella di esempio, applicando le sostituzioni richieste."""
    modifiche = modifiche or {}
    out = []
    for p in sorted(CARTELLA.glob("*.txt")):
        if solo_buste and not p.name.startswith("busta"):
            continue
        testo = p.read_text(encoding="utf-8")
        for vecchio, nuovo in modifiche.get(p.name, []):
            assert vecchio in testo, f"{vecchio!r} non trovato in {p.name}"
            testo = testo.replace(vecchio, nuovo)
        out.append((p.name, testo))
    return out


def esegui(documenti):
    return confronta([(n, analizza_testo(t)) for n, t in documenti])


def controlli(c):
    return {x.nome: x for x in c.report.controlli}


class TestConfronto(unittest.TestCase):
    def test_documenti_coerenti(self):
        c = esegui(carica())
        self.assertEqual(c.report.esito_globale, Esito.OK, confronto_testuale(c))
        k = controlli(c)
        self.assertEqual(k["Progressivi annui"].esito, Esito.OK)
        self.assertEqual(k["Catena arrotondamenti"].esito, Esito.OK)
        self.assertEqual(k["Continuità mesi"].esito, Esito.OK)
        self.assertEqual(len(c.tabelle["RSSMRA80A01H501U"]), 3)

    def test_falso_coerente_scoperto_dai_progressivi(self):
        """Settembre gonfiato di 200 € ricalcolando tutto: la busta da sola è corretta."""
        sett = "busta_09_settembre_2026.txt"
        falso = carica({sett: [
            ("Superminimo                             150,00", "Superminimo                             350,00"),
            ("Imponibile previdenziale      2.150,00", "Imponibile previdenziale      2.350,00"),
            ("Contributi dipendente           197,59", "Contributi dipendente           215,97"),
            ("Imponibile fiscale            1.952,41", "Imponibile fiscale            2.134,03"),
            ("TOTALE COMPETENZE             2.150,00", "TOTALE COMPETENZE             2.350,00"),
            ("TOTALE TRATTENUTE               517,74", "TOTALE TRATTENUTE               536,12"),
            ("NETTO IN BUSTA                1.633,00", "NETTO IN BUSTA                1.814,62"),
        ]})
        singola = analizza_testo(dict(falso)[sett])
        self.assertNotEqual(singola.esito_globale, Esito.ERRORE)  # da sola sembra regolare
        k = controlli(esegui(falso))
        self.assertEqual(k["Progressivi annui"].esito, Esito.ERRORE)
        self.assertIn("Settembre 2026", k["Progressivi annui"].dettaglio)

    def test_netto_alterato(self):
        k = controlli(esegui(carica({"busta_09_settembre_2026.txt": [
            ("NETTO IN BUSTA                1.633,00", "NETTO IN BUSTA                1.933,00")]})))
        self.assertEqual(k["Andamento netto"].esito, Esito.ERRORE)

    def test_data_assunzione_diversa(self):
        k = controlli(esegui(carica({"busta_10_ottobre_2026.txt": [("01/03/2019", "01/03/2017")]})))
        self.assertEqual(k["Data assunzione"].esito, Esito.ERRORE)

    def test_azienda_diversa(self):
        k = controlli(esegui(carica({"busta_10_ottobre_2026.txt": [("12345678903", "01234567897")]})))
        self.assertEqual(k["Azienda (P.IVA)"].esito, Esito.ATTENZIONE)
        self.assertEqual(k["Data assunzione"].esito, Esito.OK)

    def test_arrotondamenti_non_riportati(self):
        k = controlli(esegui(carica({"busta_10_ottobre_2026.txt": [
            ("Arrotondamento precedente         0,88", "Arrotondamento precedente         0,50"),
            ("NETTO IN BUSTA                1.632,00", "NETTO IN BUSTA                1.632,38")]})))
        self.assertEqual(k["Catena arrotondamenti"].esito, Esito.ATTENZIONE)

    def test_mese_duplicato_con_netto_diverso(self):
        docs = carica(solo_buste=True)
        nome, testo = docs[1]
        docs.append(("copia_" + nome, testo.replace("NETTO IN BUSTA                1.633,00",
                                                     "NETTO IN BUSTA                1.733,00")))
        k = controlli(esegui(docs))
        self.assertEqual(k["Mese duplicato"].esito, Esito.ERRORE)

    def test_mese_mancante(self):
        docs = [d for d in carica(solo_buste=True) if "settembre" not in d[0]]
        k = controlli(esegui(docs))
        self.assertEqual(k["Mesi mancanti"].esito, Esito.INFO)
        self.assertIn("Settembre 2026", k["Mesi mancanti"].dettaglio)

    def test_persone_diverse(self):
        k = controlli(esegui(carica({"carta_identita_rossi.txt": [
            ("RSSMRA80A01H501U", "BNCLRA85C55F205D")]})))
        self.assertEqual(k["Codice fiscale"].esito, Esito.ATTENZIONE)

    def test_buste_vs_modello_redditi(self):
        buste = [(n, t.replace(" 2026", " 2025")) for n, t in carica(solo_buste=True)]
        redditi = """AGENZIA DELLE ENTRATE - REDDITI 2026 PERSONE FISICHE
Periodo d'imposta 2025
Codice fiscale RSSMRA80A01H501U
QUADRO RC - Redditi di lavoro dipendente e assimilati
RC1 Redditi di lavoro dipendente {importo}
QUADRO RN
RN1 Reddito complessivo {importo}
RN26 Imposta netta 4.100
"""
        ok = controlli(esegui(buste + [("redditi.txt", redditi.format(importo="25.381"))]))
        self.assertEqual(ok["Buste paga ↔ Redditi 2025"].esito, Esito.OK)
        ko = controlli(esegui(buste + [("redditi.txt", redditi.format(importo="40.000"))]))
        self.assertEqual(ko["Buste paga ↔ Redditi 2025"].esito, Esito.ATTENZIONE)

    def test_un_solo_documento(self):
        c = esegui(carica(solo_buste=True)[:1])
        self.assertEqual(c.report.esito_globale, Esito.ATTENZIONE)


if __name__ == "__main__":
    unittest.main()
