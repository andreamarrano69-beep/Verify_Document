"""Affidabilità dei documenti nell'esito Compass e clienti autonomi (documenti INVENTATI)."""

import unittest
from pathlib import Path

from verify_document.cli import analizza_documento, analizza_testo
from verify_document.confronto import confronta
from verify_document.criteri_compass.affidabilita import (AFFIDABILI, DA_VERIFICARE, NON_COERENTI, NON_VALUTATA,
                                                          esito_finale, valuta)
from verify_document.criteri_compass.autonomi import URL_VERIFICA_PIVA, riepilogo

ESEMPI = Path(__file__).resolve().parent.parent / "esempi"


def documenti(cartella):
    return [(p.name, analizza_documento(p)[1]) for p in sorted((ESEMPI / cartella).glob("*.txt"))]


class TestAffidabilita(unittest.TestCase):
    def test_privato_coerente_con_inps(self):
        d = documenti("confronto_inps")
        a = valuta([r for _, r in d], confronta(d))
        self.assertEqual(a.livello, AFFIDABILI)
        self.assertIn("4 coerenti", a.testo())
        tag, testo = esito_finale(a, ["NET", "CARDIF"], [])
        self.assertEqual(tag, "ok")
        self.assertIn("DOCUMENTI AFFIDABILI · Criteri: assumibile con NET, CARDIF", testo)
        tag, testo = esito_finale(a, [], [], ["NET", "CARDIF"])  # es. TFR non inserito
        self.assertEqual(tag, "pre")
        self.assertIn("da completare (dati mancanti) per 2 compagnie", testo)
        self.assertEqual(esito_finale(a, [], [])[0], "ko")

    def test_cessione_in_corso_non_e_un_dubbio(self):
        d = documenti("pensionato")
        a = valuta([r for _, r in d], confronta(d))
        self.assertEqual(a.livello, AFFIDABILI, a.testo())
        self.assertIn("estratto contributivo", a.testo())  # consigliato

    def test_busta_alterata(self):
        testo = (ESEMPI / "busta_paga_esempio.txt").read_text(encoding="utf-8").replace("1.632,00", "1.932,00")
        a = valuta([analizza_testo(testo, "busta")])
        self.assertEqual(a.livello, NON_COERENTI)
        self.assertIn("Quadratura netto", a.testo())
        tag, finale = esito_finale(a, ["NET"], [])
        self.assertEqual(tag, "ko")
        self.assertIn("valido solo se i documenti sono veri", finale)

    def test_cu_non_coerente_con_inps(self):
        d = dict(documenti("confronto_inps"))
        cu = (ESEMPI / "confronto_inps" / "cu_rossi_2025.txt").read_text(encoding="utf-8").replace("27.950,00",
                                                                                                    "39.950,00")
        d["cu_rossi_2025.txt"] = analizza_testo(cu, "cu")
        coppie = list(d.items())
        a = valuta([r for _, r in coppie], confronta(coppie))
        self.assertEqual(a.livello, NON_COERENTI)
        self.assertIn("CU 2025 ↔ estratto", a.testo())

    def test_rischio_pdf_e_attenzioni(self):
        _, r = analizza_documento(ESEMPI / "busta_paga_esempio.txt")
        r.dati["rischio_alterazione"] = "MEDIO (2 punti)"
        self.assertEqual(valuta([r]).livello, DA_VERIFICARE)
        r.dati["rischio_alterazione"] = "ALTO (5 punti)"
        self.assertEqual(valuta([r]).livello, NON_COERENTI)

    def test_niente_dati_personali_nel_testo(self):
        d = documenti("confronto_inps")
        testo = valuta([r for _, r in d], confronta(d)).testo()
        for vietato in ("RSSMRA80A01H501U", "ROSSI", ".txt"):
            self.assertNotIn(vietato, testo)

    def test_nessun_documento(self):
        self.assertEqual(valuta([]).livello, NON_VALUTATA)


class TestAutonomi(unittest.TestCase):
    def test_riepilogo_e_partita_iva(self):
        modello = analizza_documento(ESEMPI / "modello_redditi_forfettario.txt")[1]
        self.assertEqual(modello.dati["partita_iva"], "07654321087")
        righe, partite_iva = riepilogo([modello])
        self.assertEqual(partite_iva, ["07654321087"])
        testo = "\n".join(t for _, t in righe)
        self.assertIn("Forfettario", testo)
        self.assertIn("protocollo 26092212345678901-000001", testo)

    def test_senza_modello(self):
        righe, partite_iva = riepilogo([])
        self.assertEqual(partite_iva, [])
        self.assertEqual(righe[0][0], "ko")

    def test_partita_iva_non_valida(self):
        testo = (ESEMPI / "modello_redditi_forfettario.txt").read_text(encoding="utf-8").replace("07654321087",
                                                                                                "07654321088")
        r = analizza_testo(testo, "redditi")
        self.assertTrue(any(c.nome == "Partita IVA" for c in r.controlli))

    def test_link_ufficiale(self):
        self.assertTrue(URL_VERIFICA_PIVA.startswith("https://telematici.agenziaentrate.gov.it/"))


if __name__ == "__main__":
    unittest.main()
