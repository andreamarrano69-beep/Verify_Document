"""Test della verifica dei criteri assuntivi Compass (casi controllati a mano sui PDF 07/2026)."""

import glob
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from verify_document.cli import analizza_file
from verify_document.criteri_compass import archivio_regole, da_documenti
from verify_document.criteri_compass import motore as V

OGGI = date(2026, 11, 12)
CARTELLA = Path(__file__).resolve().parent.parent


def pratica(**k):
    base = dict(sesso="M", nascita=date(1975, 3, 15), assunzione=date(2010, 9, 1), netto=1800, tfr=25000, rata=360,
                durata=120, decorrenza=date(2027, 1, 1), anzianita_contributiva_mesi=300, dipendenti_azienda=200,
                oggi=OGGI)
    base.update(k)
    return V.Pratica(**base)


def esiti(p):
    return {e.compagnia: e for e in V.verifica_pratica(p)[2]}


def motivi(e, livello="KO"):
    return " / ".join(t for l, t in e.motivi if l == livello)


class TestDate(unittest.TestCase):
    def test_differenza_e_limiti(self):
        self.assertEqual(V.differenza_amg(date(1962, 6, 10), date(2028, 12, 9)), (66, 5, 29))
        self.assertEqual(V.primo_giorno_oltre(date(1962, 6, 10), (66, 5, 29)), date(2028, 12, 10))
        self.assertEqual(V.aggiungi_mesi(date(2027, 1, 31), 1), date(2027, 2, 28))
        self.assertEqual(V.mesi_tra(date(2027, 1, 1), date(2028, 12, 10)), 23)


class TestPrivati(unittest.TestCase):
    def setUp(self):
        V.CARTELLA_REGOLE = None

    def test_caso_regolare(self):
        e = esiti(pratica(valutazioni={"NET": {"esito": "Assumibile", "scoring": 6}}))
        self.assertEqual(e["NET"].livello, "OK")
        self.assertEqual(e["HDI"].livello, "OK")            # 200 dipendenti, anzianità >= 6 anni: 5 x TFR
        self.assertEqual(e["METLIFE"].livello, "KO")        # montante 43.200 > 1,5 x 25.000
        self.assertEqual(e["CARDIF"].livello, "VERIFICA")   # scoring non inserito

    def test_superamento_limiti_eta_con_tfr(self):
        e = esiti(pratica(nascita=date(1962, 6, 10), assunzione=date(2000, 3, 1), netto=1500, tfr=30000, rata=300,
                          anzianita_contributiva_mesi=480, dipendenti_azienda=300, scoring=6, rata_delega=150,
                          residuo_delega=9000))
        # Net: limite 66a 5m 29g raggiunto dopo 23 rate, residuo 97 x 300 = 29.100 coperto dal TFR 30.000
        self.assertEqual(e["NET"].livello, "OK")
        self.assertIn("29.100,00", " ".join(t for _, t in e["NET"].motivi))
        self.assertEqual(e["SOGECAP"].livello, "KO")        # superamento non ammesso
        self.assertEqual(e["CARDIF"].livello, "KO")         # superamento: coesistenze non ammesse
        self.assertEqual(e["HDI"].livello, "KO")            # dato combinato 62/41 raggiunto dopo 10 rate

    def test_requisiti_generali(self):
        e = esiti(pratica(rata=400, contratto="Apprendistato"))
        for esito in e.values():
            self.assertEqual(esito.livello, "KO")
            self.assertIn("quinto", motivi(esito))
            self.assertIn("apprendistato", motivi(esito))

    def test_azienda_non_assumibile(self):
        e = esiti(pratica(rata=200, valutazioni={"CARDIF": {"esito": "Non assumibile"}}))
        self.assertEqual(e["CARDIF"].livello, "PREACC")    # montante 24.000 entro il TFR: 1/1 in pre-accettazione
        e = esiti(pratica(valutazioni={"CARDIF": {"esito": "Non assumibile"}}))
        self.assertEqual(e["CARDIF"].livello, "KO")

    def test_coesistenze_amtrust_solo_con_altre_trattenute(self):
        p = dict(assunzione=date(2015, 1, 1), netto=1300, tfr=15000, rata=260, scoring=6, dipendenti_azienda=60,
                 rata_pignoramento=325, residuo_pignoramento=60000)
        e = esiti(pratica(**p))
        self.assertEqual(e["AMTRUST"].livello, "KO")        # 45%: la pre-accettazione vale solo con altre trattenute
        self.assertEqual(e["AXA"].livello, "PREACC")        # 45% tra 40 e 50: pre-accettazione
        self.assertEqual(e["CARDIF"].livello, "KO")         # residuo pignoramento oltre 50.000


class TestAltriSettori(unittest.TestCase):
    def setUp(self):
        V.CARTELLA_REGOLE = None

    def test_parapubblici_esenzione_tfr(self):
        e = esiti(pratica(prodotto="CQS", settore="Parapubblico", nascita=date(1981, 3, 10),
                          assunzione=date(2015, 2, 1), netto=2000, tfr=10000, rata=300, anzianita_contributiva_mesi=None))
        self.assertEqual(e["CARDIF"].livello, "VERIFICA")   # categoria A/B non inserita
        e = esiti(pratica(prodotto="CQS", settore="Parapubblico", nascita=date(1981, 3, 10),
                          assunzione=date(2015, 2, 1), netto=2000, tfr=10000, rata=300, anzianita_contributiva_mesi=None,
                          valutazioni={"CARDIF": {"esito": "Assumibile", "codice": "B"}}))
        self.assertEqual(e["CARDIF"].livello, "OK")         # categoria B: oltre 30.000 serve 1/4 -> 40.000
        self.assertEqual(e["NET"].livello, "KO")            # oltre 30.000 serve 1/3 -> 30.000 < 36.000
        e = esiti(pratica(prodotto="CQS", settore="Parapubblico", nascita=date(1981, 3, 10), tfr=10000, rata=200,
                          valutazioni={"CARDIF": {"esito": "Assumibile", "codice": "A"}}))
        self.assertIn("non richiesto", " ".join(t for _, t in e["CARDIF"].motivi))  # 24.000 <= 40.000 (cat. A)

    def test_statali_quinto_ridotto(self):
        base = dict(prodotto="CQS", settore="Statale / pubblico", nascita=date(1960, 5, 1), assunzione=date(1990, 1, 1),
                    netto=2500, durata=96, anzianita_contributiva_mesi=480, tfr=0)
        e = esiti(pratica(rata=500, **base))
        self.assertEqual(e["SOGECAP"].livello, "KO")        # età a scadenza > 72a 11m 29g: V° dell'80% = 400
        self.assertEqual(e["NET"].livello, "KO")            # limiti pensionistici già raggiunti alla decorrenza
        self.assertEqual(e["HDI"].livello, "OK")
        e = esiti(pratica(rata=400, **base))
        self.assertEqual(e["SOGECAP"].livello, "OK")
        self.assertEqual(e["AMTRUST"].livello, "OK")

    def test_medici_quota_ridotta(self):
        e = esiti(pratica(prodotto="CQS", settore="Medico convenzionato", nascita=date(1981, 3, 10), netto=2000,
                          rata=300, tfr=0))
        self.assertIn("del 70%", motivi(e["AXA"]))         # AXA: quinto del 70% = 280
        self.assertEqual(e["HDI"].livello, "PREACC")        # sempre pre-accettazione

    def test_no_tfr_young(self):
        e = esiti(pratica(prodotto="CQS", settore="Privato NO TFR", nascita=date(1996, 1, 1), assunzione=date(2024, 1, 1),
                          rata=100, durata=48, tfr=0, anzianita_contributiva_mesi=None,
                          valutazioni={"NET": {"esito": "Assumibile", "scoring": 3, "codice": "Altro"},
                                       "CARDIF": {"esito": "Assumibile", "codice": "YOUNG"}}))
        self.assertEqual(e["CARDIF_YOUNG"].livello, "OK")
        self.assertEqual(e["NET"].livello, "KO")            # codice «Altro» non ammesso
        self.assertEqual(e["NET_YOUNG"].livello, "KO")      # scoring 3 < 4

    def test_deleghe(self):
        base = dict(prodotto="Delega", netto=1600, tfr=30000, dipendenti_azienda=50, cqs_rata=300, cqs_residuo=20000)
        e = esiti(pratica(cqs_compagnia="NET", rata=150, durata=60, **base))
        self.assertEqual(e["AMTRUST"].livello, "KO")        # serve la CQS con la stessa compagnia
        self.assertNotIn("NET_PLUS", e)
        e = esiti(pratica(cqs_compagnia="CARDIF", rata=150, durata=60,
                          valutazioni={"NET": {"esito": "Assumibile", "scoring": 6, "codice": "PRIME"},
                                       "CARDIF": {"esito": "Assumibile", "scoring": 2}}, **base))
        self.assertEqual(e["NET_PLUS"].livello, "OK")       # Delega Plus: 60 mesi, 9.000 €, PRIME
        self.assertNotIn("NET", e)
        self.assertEqual(e["CARDIF"].livello, "KO")         # scoring 2 < 3
        e = esiti(pratica(prodotto="Delega", settore="Parapubblico", dipendenti_azienda=50))
        self.assertTrue(all("assenza di CQS" in motivi(x) for x in e.values()))

    def test_pensionati(self):
        r = V.verifica_pensionato(V.PraticaPensionato(nascita=date(1948, 4, 3), pensione_netta=2100, quota_cedibile=500,
                                                      rata=500, durata=120, decorrenza=date(2027, 1, 1), oggi=OGGI))
        e = {x.compagnia: x for x in r[2]}
        self.assertTrue(all(x.livello == "KO" for x in e.values()))  # 88a 8m a scadenza: oltre tutti i limiti
        self.assertIn("105 mesi", motivi(e["NET"]))         # durata massima suggerita
        r = V.verifica_pensionato(V.PraticaPensionato(nascita=date(1948, 4, 3), pensione_netta=2100, quota_cedibile=500,
                                                      rata=500, durata=105, decorrenza=date(2027, 1, 1), oggi=OGGI))
        e = {x.compagnia: x for x in r[2]}
        self.assertEqual(e["NET"].livello, "OK")
        self.assertEqual(e["SOGECAP"].livello, "OK")
        self.assertEqual(e["AXA"].livello, "KO")            # AXA: 86 anni non compiuti


class TestRegoleCondivise(unittest.TestCase):
    def tearDown(self):
        V.CARTELLA_REGOLE = None

    def test_esporta_modifica_ricarica(self):
        with tempfile.TemporaryDirectory() as tmp:
            nomi = [v["regole"] for v in V.SETTORI.values()]
            self.assertEqual(len(archivio_regole.esporta(tmp, nomi)), len(nomi))
            self.assertEqual(archivio_regole.esporta(tmp, nomi), [])        # già presenti: non sovrascrive
            f = Path(tmp, "regole", "regole_cqs_privati.json")
            dati = json.loads(f.read_text(encoding="utf-8"))
            dati["COMPAGNIE"]["NET"]["montante_massimo"] = 40000
            f.write_text(json.dumps(dati), encoding="utf-8")
            V.CARTELLA_REGOLE = tmp
            e = esiti(pratica(valutazioni={"NET": {"esito": "Assumibile", "scoring": 6}}))
            self.assertIn("40.000,00", motivi(e["NET"]))
            # tutti i settori funzionano anche con le regole lette dal JSON (liste -> tuple)
            for (prodotto, settore) in V.SETTORI:
                if settore != "Pensionato":
                    V.verifica_pratica(pratica(prodotto=prodotto, settore=settore))
            f.write_text("{rotto", encoding="utf-8")
            V.carica_regole("CQS", "Dipendente privato")
            self.assertIn("regole_cqs_privati", archivio_regole.ultimo_errore)


class TestDaDocumenti(unittest.TestCase):
    def test_busta_ed_estratto(self):
        reports = [analizza_file(f) for f in sorted(glob.glob(str(CARTELLA / "esempi/confronto_inps/*.txt")))]
        campi, note = da_documenti.da_reports(reports)
        self.assertEqual(campi["_settore"], "Dipendente privato")
        self.assertEqual(campi["nascita"], "01/01/1980")
        self.assertEqual(campi["assunzione"], "01/03/2019")
        self.assertEqual((campi["anz_anni"], campi["anz_mesi"]), ("21", "1"))
        self.assertEqual(campi["netto"], "1632,26")

    def test_pensionato_preferisce_cedolino(self):
        reports = [analizza_file(f) for f in sorted(glob.glob(str(CARTELLA / "esempi/pensionato/*.txt")))]
        campi, note = da_documenti.da_reports(reports)
        self.assertEqual(campi["_settore"], "Pensionato")
        self.assertEqual(campi["quota_cedibile"], "146,60")  # quinto 296,60 meno la cessione in corso 150


if __name__ == "__main__":
    unittest.main()
