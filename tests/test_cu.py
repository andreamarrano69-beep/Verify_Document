"""Test della Certificazione Unica e dei confronti con buste paga e Modello Redditi."""

import unittest
from decimal import Decimal
from pathlib import Path

from verify_document import cu
from verify_document.cli import analizza_testo, riconosci_tipo
from verify_document.confronto import confronta, confronto_testuale
from verify_document.report import Esito

ESEMPI = Path(__file__).resolve().parent.parent / "esempi"
CU = (ESEMPI / "cu_esempio.txt").read_text(encoding="utf-8")


def esiti(report):
    return {c.nome: c for c in report.controlli}


def buste_2025(modifiche=None):
    """Le buste paga di esempio (agosto-ottobre) spostate al 2025, l'anno della CU."""
    out = []
    for p in sorted((ESEMPI / "confronto").glob("busta*.txt")):
        t = p.read_text(encoding="utf-8").replace(" 2026", " 2025")
        for a, b in (modifiche or {}).get(p.name, []):
            assert a in t, a
            t = t.replace(a, b)
        out.append((p.name, t))
    return out


def dicembre_2025(progressivo="25.381,33", irpef="4.161,95", assunzione="01/03/2019"):
    """Busta di dicembre (con tredicesima già nei progressivi) costruita da quella di ottobre."""
    t = (ESEMPI / "confronto" / "busta_10_ottobre_2026.txt").read_text(encoding="utf-8")
    t = (t.replace("OTTOBRE 2026", "DICEMBRE 2025")
          .replace("Progressivo imponibile fiscale    19.524,10", f"Progressivo imponibile fiscale    {progressivo}")
          .replace("Progressivo IRPEF                  3.201,50", f"Progressivo IRPEF                  {irpef}")
          .replace("01/03/2019", assunzione))
    return ("busta_12_dicembre_2025.txt", t)


def confronto(docs):
    c = confronta([(n, analizza_testo(t)) for n, t in docs])
    return esiti(c.report), c


class TestCU(unittest.TestCase):
    def test_riconoscimento(self):
        self.assertEqual(riconosci_tipo(CU), "cu")

    def test_esempio(self):
        r = cu.analizza(CU)
        self.assertEqual(r.esito_globale, Esito.OK, r.to_dict())
        d = r.dati
        self.assertEqual(d["periodo_imposta"], 2025)
        self.assertEqual(d["sostituto_imposta"], "12345678903")
        self.assertEqual(d["codice_fiscale_dipendente"], "RSSMRA80A01H501U")
        self.assertEqual(d["reddito_totale"], Decimal("25381.33"))
        self.assertIsNone(d["reddito_determinato"])  # riga vuota: non deve prendere il "6" sotto
        self.assertEqual(d["giorni_lavoro"], 365)
        self.assertEqual(d["reddito_mensile_lordo"], Decimal("2115.11"))
        self.assertEqual(d["reddito_mensile_netto"], Decimal("1724.12"))

    def test_anno_dalla_intestazione(self):
        r = cu.analizza(CU.replace("Periodo d'imposta 2025\n", ""))
        self.assertEqual(r.dati["periodo_imposta"], 2025)  # "CU 2026" -> redditi 2025

    def test_ritenute_impossibili(self):
        r = cu.analizza(CU.replace("4.161,95", "7.500,00"))
        self.assertEqual(esiti(r)["Ritenute IRPEF"].esito, Esito.ERRORE)

    def test_giorni_oltre_anno(self):
        r = cu.analizza(CU.replace("dipendente                                  365",
                                   "dipendente                                  380"))
        self.assertEqual(esiti(r)["Giorni lavorati"].esito, Esito.ERRORE)

    def test_part_year(self):
        r = cu.analizza(CU.replace("dipendente                                  365",
                                   "dipendente                                  182"))
        self.assertEqual(r.dati["mesi_lavorati"], "6,0")

    def test_sostituto_non_valido(self):
        r = cu.analizza(CU.replace("12345678903", "12345678901"))
        self.assertEqual(esiti(r)["Sostituto d'imposta"].esito, Esito.ERRORE)

    def test_scaglioni_irpef(self):
        self.assertEqual(cu.irpef_lorda(Decimal("20000"), 2025), Decimal("4600.00"))
        self.assertEqual(cu.irpef_lorda(Decimal("40000"), 2025), Decimal("10640.00"))  # 6440 + 12000*35%
        self.assertEqual(cu.irpef_lorda(Decimal("40000"), 2026), Decimal("10400.00"))  # 2° scaglione al 33%
        self.assertEqual(cu.irpef_lorda(Decimal("60000"), 2025), Decimal("18440.00"))  # 6440 + 7700 + 4300
        self.assertEqual(cu.irpef_lorda(Decimal("20000"), 2023), Decimal("4700.00"))  # 15000*23% + 5000*25%
        self.assertIsNone(cu.irpef_lorda(Decimal("20000"), 1999))


class TestConfrontoCU(unittest.TestCase):
    def test_buste_stimate(self):
        k, c = confronto(buste_2025() + [("cu.txt", CU)])
        self.assertEqual(k["Buste paga ↔ CU 2025"].esito, Esito.OK, confronto_testuale(c))
        self.assertEqual(k["Data assunzione ↔ CU 2025"].esito, Esito.OK)

    def test_dicembre_esatto(self):
        k, c = confronto(buste_2025() + [dicembre_2025(), ("cu.txt", CU)])
        self.assertEqual(k["Buste paga ↔ CU 2025"].esito, Esito.OK, confronto_testuale(c))
        self.assertIn("progressivo di dicembre", k["Buste paga ↔ CU 2025"].dettaglio)
        self.assertEqual(k["IRPEF buste paga ↔ CU 2025"].esito, Esito.OK)

    def test_cu_gonfiata(self):
        k, _ = confronto(buste_2025() + [dicembre_2025(),
                                         ("cu.txt", CU.replace("25.381,33", "31.500,00"))])
        self.assertEqual(k["Buste paga ↔ CU 2025"].esito, Esito.ERRORE)

    def test_irpef_diversa(self):
        k, _ = confronto(buste_2025() + [dicembre_2025(irpef="3.100,00"), ("cu.txt", CU)])
        self.assertEqual(k["IRPEF buste paga ↔ CU 2025"].esito, Esito.ERRORE)

    def test_assunzione_diversa(self):
        k, _ = confronto(buste_2025() + [("cu.txt", CU.replace("01/03/2019", "01/03/2021"))])
        self.assertEqual(k["Data assunzione ↔ CU 2025"].esito, Esito.ERRORE)

    def test_altro_datore(self):
        k, _ = confronto(buste_2025() + [("cu.txt", CU.replace("12345678903", "01234567897"))])
        self.assertEqual(k["Datore di lavoro 2025"].esito, Esito.ATTENZIONE)

    def test_cu_vs_modello_redditi(self):
        redditi = """AGENZIA DELLE ENTRATE - REDDITI 2026 PERSONE FISICHE
Periodo d'imposta 2025
Codice fiscale RSSMRA80A01H501U
QUADRO RC - Redditi di lavoro dipendente e assimilati
RC1 Redditi di lavoro dipendente {importo}
RN1 Reddito complessivo {importo}
RN26 Imposta netta 4.100
"""
        k, _ = confronto([("cu.txt", CU), ("redditi.txt", redditi.format(importo="25.381"))])
        self.assertEqual(k["CU ↔ Redditi 2025"].esito, Esito.OK)
        k, _ = confronto([("cu.txt", CU), ("redditi.txt", redditi.format(importo="38.000"))])
        self.assertEqual(k["CU ↔ Redditi 2025"].esito, Esito.ATTENZIONE)
        self.assertIn("gonfiato", k["CU ↔ Redditi 2025"].dettaglio)


if __name__ == "__main__":
    unittest.main()
