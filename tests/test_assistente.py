"""Test dell'assistente AI (con un Ollama finto), dello scaricatore e delle impostazioni dell'ufficio."""

import hashlib
import json
import shutil
import tempfile
import threading
import time
import unittest
from functools import partial
from http.server import BaseHTTPRequestHandler, HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from unittest import mock

from verify_document import archivio, impostazioni
from verify_document.assistente import ollama_http, rag, scarica


class _OllamaFinto(BaseHTTPRequestHandler):
    vettori_calcolati = 0

    def log_message(self, *a):
        pass

    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(json.dumps({"models": [{"name": "qwen2.5:1.5b"},
                                                {"name": "nomic-embed-text:latest"}]}).encode())

    def do_POST(self):
        dati = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.send_response(200)
        self.end_headers()
        if self.path == "/api/embed":
            _OllamaFinto.vettori_calcolati += len(dati["input"])
            out = []
            for t in dati["input"]:
                v = [0.0] * 64
                for w in t.lower().split():
                    v[int(hashlib.md5(w.encode()).hexdigest(), 16) % 64] += 1
                out.append(v)
            self.wfile.write(json.dumps({"embeddings": out}).encode())
        else:
            for pezzo in ("Venti", " ore", " annue."):
                self.wfile.write((json.dumps({"message": {"content": pezzo}, "done": False}) + "\n").encode())
            self.wfile.write((json.dumps({"done": True}) + "\n").encode())


class TestAssistente(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), _OllamaFinto)
        cls.host = f"http://127.0.0.1:{cls.server.server_port}"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def test_indice_aree_e_risposta(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "documenti_ai"
            (base / "OAM").mkdir(parents=True)
            (base / "Compass").mkdir()
            (base / "Generale").mkdir()
            (base / "OAM" / "formazione.txt").write_text("Aggiornamento professionale dei collaboratori: venti ore "
                                                          "annue dal 2027. " * 10, encoding="utf-8")
            (base / "Compass" / "criteri.md").write_text("Statali: età massima a scadenza settantacinque anni. " * 10,
                                                         encoding="utf-8")
            (base / "Generale" / "orari.txt").write_text("L'ufficio apre alle nove. " * 10, encoding="utf-8")
            cfg = rag.configurazione({"cartella_condivisa": tmp, "ollama_host": self.host})
            cfg.indice_locale = Path(tmp) / "locale.npz"

            # si prepara solo l'area scelta
            prima = _OllamaFinto.vettori_calcolati
            oam = rag.carica_indice(cfg, area="OAM")
            n_oam = _OllamaFinto.vettori_calcolati - prima
            self.assertEqual({p["fonte"] for p in oam.pezzi}, {"OAM/formazione.txt"})
            self.assertEqual(n_oam, len(oam.pezzi))
            self.assertTrue((base / ".indice_ai_oam.npz").is_file())        # indice condiviso per gli altri PC
            self.assertFalse((base / ".indice_ai_compass.npz").exists())    # Compass non ancora preparato
            trovati = rag.cerca(cfg, oam, "ore di aggiornamento dei collaboratori", "OAM")
            self.assertEqual({p["fonte"] for p in trovati}, {"OAM/formazione.txt"})
            self.assertEqual("".join(rag.rispondi(cfg, "quante ore?", trovati, "OAM")), "Venti ore annue.")

            tutti = rag.carica_indice(cfg, area="Tutti")
            self.assertEqual([tutti.documenti(a) for a in ("OAM", "Compass", "Generale", "Tutti")], [1, 1, 1, 3])

            prima = _OllamaFinto.vettori_calcolati
            rag.carica_indice(cfg, area="Tutti")
            self.assertEqual(_OllamaFinto.vettori_calcolati, prima)        # niente ricalcolo
            time.sleep(0.15)
            (base / "OAM" / "nuova.txt").write_text("Nuova circolare sul registro dei collaboratori. " * 5, encoding="utf-8")
            rag.carica_indice(cfg, area="Compass")
            self.assertEqual(_OllamaFinto.vettori_calcolati, prima)        # il file OAM nuovo non tocca Compass
            rag.carica_indice(cfg, area="OAM")
            self.assertEqual(_OllamaFinto.vettori_calcolati - prima, 1)    # solo il file nuovo
            with self.assertRaises(FileNotFoundError):
                shutil.rmtree(base / "Generale")
                rag.carica_indice(cfg, area="Generale")

    def test_riusa_vecchio_indice_e_riprende_dopo_interruzione(self):
        import json
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "documenti_ai"
            (base / "OAM").mkdir(parents=True)
            for n in range(3):
                (base / "OAM" / f"doc{n}.txt").write_text(f"Documento numero {n} sul registro. " * 30, encoding="utf-8")
            cfg = rag.configurazione({"cartella_condivisa": tmp, "ollama_host": self.host})
            cfg.indice_locale = Path(tmp) / "locale.npz"
            firma = rag._firma(cfg)
            # vecchio indice unico JSON (versione 0.13.0) con un solo file già calcolato
            testi = rag.dividi_in_pezzi(rag.leggi_file(base / "OAM" / "doc0.txt"))
            vecchio = {"firma": {"versione": 1, "modello": cfg.modello_embedding, "file": firma["file"]},
                       "pezzi": [{"fonte": "OAM/doc0.txt", "testo": t} for t in testi],
                       "vettori": [[0.1] * 64 for _ in testi]}
            (base / rag.NOME_INDICE_VECCHIO).write_text(json.dumps(vecchio), encoding="utf-8")
            prima = _OllamaFinto.vettori_calcolati
            indice = rag.carica_indice(cfg, area="OAM")
            self.assertEqual(indice.documenti("OAM"), 3)
            self.assertEqual(_OllamaFinto.vettori_calcolati - prima, 2 * len(testi))   # doc0 riusato
            self.assertFalse((base / rag.NOME_INDICE_VECCHIO).exists())   # tutti i gruppi pronti: vecchio cancellato
            indice_oam = base / ".indice_ai_oam.npz"
            self.assertTrue(indice_oam.is_file())

            # salvataggio parziale (programma chiuso a metà): si riprende senza ricalcolare i file pronti
            dati = rag._leggi_indice(indice_oam)
            solo_doc1 = [i for i, p in enumerate(dati["pezzi"]) if p["fonte"] == "OAM/doc1.txt"]
            parziale = {"firma": {**dati["firma"], "file": {"OAM/doc1.txt": firma["file"]["OAM/doc1.txt"]}},
                        "pezzi": [dati["pezzi"][i] for i in solo_doc1],
                        "vettori": [dati["vettori"][i] for i in solo_doc1]}
            for p in rag._file_indice(cfg, "OAM"):
                rag._scrivi_indice(p, parziale)
            prima = _OllamaFinto.vettori_calcolati
            self.assertEqual(rag.carica_indice(cfg, area="OAM").documenti("OAM"), 3)
            self.assertEqual(_OllamaFinto.vettori_calcolati - prima, 2 * len(testi))   # solo doc0 e doc2

    def test_senza_ollama(self):
        self.assertFalse(ollama_http.disponibile("http://127.0.0.1:1"))
        with self.assertRaises(ollama_http.ErroreOllama) as e:
            ollama_http.modelli("http://127.0.0.1:1")
        self.assertIn("Ollama", str(e.exception))
        self.assertTrue(ollama_http.ha_modello(["nomic-embed-text:latest"], "nomic-embed-text"))

    def test_cartella_vuota(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = rag.configurazione({"cartella_condivisa": tmp, "ollama_host": self.host})
            with self.assertRaises(FileNotFoundError):
                rag.carica_indice(cfg)


class TestScarica(unittest.TestCase):
    def test_scarica_esclude_e_aggiorna(self):
        with tempfile.TemporaryDirectory() as tmp:
            sito = Path(tmp) / "sito"
            (sito / "share" / "pdfs").mkdir(parents=True)
            for nome in ("CQ002", "s05T", "COM085"):
                (sito / "share" / "pdfs" / f"{nome}.pdf").write_bytes(b"%PDF-1.4 prova")
            (sito / "trasparenza.html").write_text(
                "<html><body><nav>MENU</nav><main><h1>Trasparenza</h1><p>" + "Testo della pagina. " * 15 + "</p>"
                "<h4>Cessione del quinto dello stipendio / pensione</h4>"
                "<a href='/share/pdfs/CQ002.pdf'>Copia idonea per la stipula</a>"
                "<a href='/share/pdfs/s05T.pdf'>Set Daily – non disponibile per la vendita</a>"
                "<h4>Rilevazione trimestrale TEGM</h4><a href='/share/pdfs/COM085.pdf'>Tabella</a>"
                "</main></body></html>", encoding="utf-8")
            server = HTTPServer(("127.0.0.1", 0), partial(_SitoMuto, directory=str(sito)))
            threading.Thread(target=server.serve_forever, daemon=True).start()
            indirizzo = f"127.0.0.1:{server.server_port}"
            fonti = {"compass": dict(scarica.FONTI["compass"], domini=[indirizzo],
                                     pagine=[("trasparenza", f"http://{indirizzo}/trasparenza.html")])}
            try:
                with mock.patch.object(scarica, "FONTI", fonti), mock.patch.object(scarica, "FORZA_HTTPS", False):
                    r = scarica.aggiorna(Path(tmp) / "out", pausa=0, avanzamento=lambda _t: None)
                    self.assertEqual(sorted(r["nuovi"]), [
                        "Cessione del quinto dello stipendio pensione - Copia idonea per la stipula (CQ002).pdf",
                        "Rilevazione trimestrale TEGM - Tabella (COM085).pdf"])
                    self.assertEqual(r["esclusi"], 1)
                    (sito / "share" / "pdfs" / "COM085.pdf").write_bytes(b"%PDF-1.4 nuovo trimestre")
                    r = scarica.aggiorna(Path(tmp) / "out", pausa=0, avanzamento=lambda _t: None)
                    self.assertEqual(r["aggiornati"], ["Rilevazione trimestrale TEGM - Tabella (COM085).pdf"])
                    self.assertEqual(r["invariati"], 1)
            finally:
                server.shutdown()
                server.server_close()


class _SitoMuto(SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


class TestImpostazioniUfficio(unittest.TestCase):
    def test_valori_ufficio_e_archivio_condiviso(self):
        with tempfile.TemporaryDirectory() as tmp:
            ufficio = Path(tmp) / "config_ufficio.json"
            ufficio.write_text(json.dumps({"cartella_condivisa": r"\\SERVER\Condivisa\VD", "modello_ai": "qwen2.5:3b"}),
                               encoding="utf-8")
            utente = Path(tmp) / "utente" / "impostazioni.json"
            with mock.patch.object(impostazioni, "file_ufficio", return_value=ufficio), \
                    mock.patch.object(impostazioni, "FILE", utente):
                self.assertEqual(impostazioni.carica()["cartella_condivisa"], r"\\SERVER\Condivisa\VD")
                impostazioni.salva({"studio": "Agenzia", "cartella_condivisa": ""})
                dati = impostazioni.carica()
                self.assertEqual(dati["cartella_condivisa"], r"\\SERVER\Condivisa\VD")  # il vuoto non cancella
                self.assertEqual(dati["studio"], "Agenzia")
                self.assertNotIn("ollama_host", json.loads(utente.read_text(encoding="utf-8")))  # solo scelte utente
                self.assertEqual(archivio.cartella_archivio(dati), Path(r"\\SERVER\Condivisa\VD") / "archivio")
                impostazioni.salva({"modello_ai": "qwen2.5:0.5b"})
                self.assertEqual(impostazioni.carica()["modello_ai"], "qwen2.5:0.5b")


if __name__ == "__main__":
    unittest.main()
