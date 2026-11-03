"""Cessione del quinto, delegazione di pagamento e pignoramento su buste paga e pensioni."""

import re
import unittest
from decimal import Decimal
from pathlib import Path

from verify_document import busta_paga
from verify_document.cli import analizza_testo
from verify_document.confronto import confronta
from verify_document.report import Esito

ESEMPI = Path(__file__).resolve().parent.parent / "esempi"
BUSTA = (ESEMPI / "busta_paga_esempio.txt").read_text(encoding="utf-8")


def euro(v: Decimal) -> str:
    return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def con_trattenute(testo: str, **voci: str) -> str:
    """Aggiunge voci di trattenuta (es. cessione_quinto="250,00") ricalcolando totale trattenute e netto."""
    nomi = {"cessione_quinto": "Cessione del quinto", "delegazione_pagamento": "Delegazione di pagamento",
            "pignoramento": "Pignoramento presso terzi"}
    righe, totale = [], Decimal(0)
    for i, (k, v) in enumerate(voci.items()):
        righe.append(f"{3000 + i:04d} {nomi[k]:<35}{'':>14}{v:>14}")
        totale += Decimal(v.replace(".", "").replace(",", "."))
    testo = re.sub(r"(2000 Ritenute IRPEF[^\n]*\n)", lambda m: m.group(1) + "\n".join(righe) + "\n", testo)

    def aggiorna(etichetta, segno):
        nonlocal testo
        m = re.search(etichetta + r"(\s+)([\d.]+,\d{2})", testo)
        nuovo = Decimal(m.group(2).replace(".", "").replace(",", ".")) + segno * totale
        testo = testo.replace(m.group(0), f"{etichetta}{m.group(1)}{euro(nuovo)}")

    aggiorna("TOTALE TRATTENUTE", 1)
    aggiorna("NETTO IN BUSTA", -1)
    return testo


def esiti(r):
    return {c.nome: c for c in r.controlli}


class TestBustaPaga(unittest.TestCase):
    def test_senza_cessione(self):
        r = busta_paga.analizza(BUSTA)
        self.assertEqual(r.dati["quinto_cedibile"], Decimal("326.45"))  # (2150 − 197,59 − 320,15) / 5
        self.assertEqual(esiti(r)["Quinto cedibile"].esito, Esito.OK)
        self.assertNotIn("Cessione del quinto / prestiti", esiti(r))

    def test_cessione_in_corso(self):
        r = busta_paga.analizza(con_trattenute(BUSTA, cessione_quinto="250,00"))
        k = esiti(r)
        self.assertEqual(k["Quadratura netto"].esito, Esito.OK)
        self.assertEqual(r.dati["cessione_quinto"], Decimal("250.00"))
        self.assertEqual(r.dati["cessione_disponibile"], Decimal("76.45"))
        self.assertEqual(k["Cessione del quinto / prestiti"].esito, Esito.ATTENZIONE)
        self.assertEqual(k["Quinto cedibile"].esito, Esito.INFO)

    def test_cessione_oltre_il_quinto(self):
        k = esiti(busta_paga.analizza(con_trattenute(BUSTA, cessione_quinto="400,00")))
        self.assertEqual(k["Quinto cedibile"].esito, Esito.ERRORE)

    def test_cessione_e_delega_oltre_due_quinti(self):
        k = esiti(busta_paga.analizza(con_trattenute(BUSTA, cessione_quinto="320,00",
                                                     delegazione_pagamento="380,00")))
        self.assertEqual(k["Quinto cedibile"].esito, Esito.ERRORE)
        self.assertIn("2/5", k["Quinto cedibile"].dettaglio)

    def test_cessione_e_delega_nei_limiti(self):
        r = busta_paga.analizza(con_trattenute(BUSTA, cessione_quinto="300,00", delegazione_pagamento="300,00"))
        self.assertEqual(esiti(r)["Quinto cedibile"].esito, Esito.INFO)
        self.assertEqual(r.dati["delegazione_disponibile"], Decimal("26.45"))

    def test_pignoramento_oltre_meta(self):
        k = esiti(busta_paga.analizza(con_trattenute(BUSTA, cessione_quinto="300,00", pignoramento="600,00")))
        self.assertEqual(k["Pignoramento"].esito, Esito.ATTENZIONE)
        self.assertEqual(k["Quinto cedibile"].esito, Esito.ERRORE)

    def test_base_stimata_senza_contributi(self):
        testo = (con_trattenute(BUSTA, cessione_quinto="250,00")
                 .replace("Contributi dipendente", "Altro").replace("Contributo IVS", "Altra voce"))
        r = busta_paga.analizza(testo)
        self.assertIn("stima", esiti(r)["Quinto cedibile"].dettaglio)
        self.assertEqual(r.dati["base_netta_quinto"], Decimal("1632.00"))  # netto 1.382 + rata 250


class TestConfronto(unittest.TestCase):
    def _buste(self, rate):
        out = []
        for p, rata in zip(sorted((ESEMPI / "confronto").glob("busta*.txt")), rate):
            t = p.read_text(encoding="utf-8")
            out.append((p.name, analizza_testo(con_trattenute(t, cessione_quinto=rata) if rata else t)))
        return {c.nome: c for c in confronta(out).report.controlli}

    def test_rata_costante(self):
        k = self._buste(["250,00", "250,00", "250,00"])
        self.assertEqual(k["Cessione del quinto"].esito, Esito.INFO)
        self.assertIn("costante", k["Cessione del quinto"].dettaglio)

    def test_rata_diversa(self):
        k = self._buste(["250,00", "250,00", "300,00"])
        self.assertEqual(k["Cessione del quinto"].esito, Esito.ATTENZIONE)

    def test_cessione_iniziata(self):
        k = self._buste([None, "250,00", "250,00"])
        self.assertIn("Agosto 2026", k["Cessione del quinto: variazioni"].dettaglio)


if __name__ == "__main__":
    unittest.main()
