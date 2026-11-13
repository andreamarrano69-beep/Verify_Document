"""Finestra «Assistente AI»: domande sui documenti OAM / Compass / note dell'ufficio.

Pulsanti: OAM, Compass, Generale (dove cercare) · + Documento · + Nota · Aggiorna · Scarica dai siti ·
Apri cartella · Chiudi. Funziona solo se Ollama è raggiungibile (su questo PC o su un altro PC dell'ufficio).
"""

from __future__ import annotations

import queue
import re
import shutil
import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from . import ollama_http, rag, scarica

BLU_SCURO = "#1f3a5f"
BLU = "#2e6da4"
BLU_CHIARO = "#e8f0f8"
GRIGIO = "#6b7280"
SFONDO = "#f5f7fa"
BIANCO = "#ffffff"
VERDE = "#2e7d32"
ROSSO = "#c62828"
COLORE_AREA = {"OAM": "#7b3fa0", "Compass": "#d35400", "Generale": BLU}
CARTELLA_NOTE = {"OAM": Path("OAM") / "note", "Compass": Path("Compass") / "note", "Generale": Path("Note")}
CARTELLA_AGGIUNTI = {"OAM": Path("OAM") / "aggiunti_a_mano", "Compass": Path("Compass") / "aggiunti_a_mano",
                     "Generale": Path("Generale")}


def _px(n):
    try:
        from ..gui import px
        return px(n)
    except Exception:
        return int(n)


class FinestraAssistente(tk.Toplevel):
    def __init__(self, genitore, impostazioni: dict, area: str = "Generale"):
        super().__init__(genitore)
        area_iniziale = area if area in rag.AREE else "Generale"
        self.cfg = rag.configurazione(impostazioni)
        self.title("Assistente AI · documenti OAM e Compass")
        try:
            from ..gui import adatta_finestra
            adatta_finestra(self, 1000, 720)
        except Exception:
            self.geometry("1000x720")
        self.configure(bg=SFONDO)
        self.coda: queue.Queue = queue.Queue()
        self.indice: rag.Indice | None = None
        self.area = "Generale"
        self.occupato = False
        self._crea()
        self.protocol("WM_DELETE_WINDOW", self.chiudi)
        self.after(100, self._leggi_coda)
        self.after(300, self.prepara)

    # ================= INTERFACCIA =================
    def _crea(self):
        alto = tk.Frame(self, bg=BLU_SCURO)
        alto.pack(fill="x")
        tk.Label(alto, text="Assistente AI", bg=BLU_SCURO, fg=BIANCO, font=("Segoe UI", 16, "bold")).pack(
            side="left", padx=16, pady=10)
        tk.Label(alto, text="risposte solo dai documenti dell'ufficio · tutto in locale", bg=BLU_SCURO, fg="#c9d6e6",
                 font=("Segoe UI", 9)).pack(side="left")
        self._pulsante(alto, "Chiudi", self.chiudi, ROSSO, BIANCO).pack(side="right", padx=(6, 12), pady=8)
        for testo, comando in [("Apri cartella", self.apri_cartella), ("Scarica dai siti", self.scarica_dai_siti),
                               ("Aggiorna", self.prepara), ("+ Nota", self.aggiungi_nota),
                               ("+ Documento", self.aggiungi_documento)]:
            self._pulsante(alto, testo, comando, BLU_SCURO, BIANCO).pack(side="right", padx=2, pady=8)

        barra = tk.Frame(self, bg=SFONDO)
        barra.pack(fill="x", padx=14, pady=(10, 4))
        tk.Label(barra, text="Cerca in:", bg=SFONDO, fg=GRIGIO, font=("Segoe UI", 10)).pack(side="left", padx=(0, 8))
        self.pulsanti_area = {}
        for nome in rag.AREE:
            p = self._pulsante(barra, nome, lambda n=nome: self.scegli_area(n), BIANCO, COLORE_AREA[nome])
            p.configure(width=11)
            p.pack(side="left", padx=3)
            self.pulsanti_area[nome] = p
        self.lbl_conteggio = tk.Label(barra, text="", bg=SFONDO, fg=GRIGIO, font=("Segoe UI", 9))
        self.lbl_conteggio.pack(side="left", padx=10)

        riquadro = tk.Frame(self, bg=BIANCO, highlightbackground="#d5dce5", highlightthickness=1)
        riquadro.pack(fill="both", expand=True, padx=14, pady=4)
        self.chat = tk.Text(riquadro, wrap="word", width=1, height=1, bg=BIANCO, relief="flat", padx=14, pady=10,
                            font=("Segoe UI", 11), state="disabled", cursor="arrow")
        sb = ttk.Scrollbar(riquadro, command=self.chat.yview)
        self.chat.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.chat.pack(side="left", fill="both", expand=True)
        for tag, opz in {"domanda_titolo": {"foreground": BLU_SCURO, "font": ("Segoe UI", 9, "bold"), "spacing1": 12},
                         "domanda": {"foreground": "#111827", "font": ("Segoe UI", 11, "bold"), "spacing3": 4},
                         "risposta_titolo": {"foreground": VERDE, "font": ("Segoe UI", 9, "bold")},
                         "risposta": {"foreground": "#1f2937", "lmargin1": 12, "lmargin2": 12},
                         "fonti": {"foreground": GRIGIO, "font": ("Segoe UI", 9), "lmargin1": 12, "lmargin2": 24},
                         "info": {"foreground": GRIGIO, "font": ("Segoe UI", 10, "italic")},
                         "errore": {"foreground": ROSSO, "font": ("Segoe UI", 10, "bold")}}.items():
            self.chat.tag_configure(tag, **opz)

        basso = tk.Frame(self, bg=SFONDO)
        basso.pack(fill="x", padx=14, pady=(4, 2))
        self.domanda = tk.Text(basso, height=3, width=1, wrap="word", font=("Segoe UI", 11), relief="flat",
                               highlightbackground="#c3ccd8", highlightcolor=BLU, highlightthickness=1, padx=8, pady=6)
        self.domanda.pack(side="left", fill="x", expand=True)
        self.domanda.bind("<Return>", self._invio)
        self.pulsante_chiedi = self._pulsante(basso, "Chiedi", self.chiedi, BLU, BIANCO)
        self.pulsante_chiedi.configure(width=9)
        self.pulsante_chiedi.pack(side="left", padx=(8, 0), fill="y")

        self.stato = tk.Label(self, text="", bg=SFONDO, fg=GRIGIO, anchor="w", font=("Segoe UI", 9))
        self.stato.pack(fill="x", padx=16, pady=(0, 8))
        self.scegli_area(area_iniziale)
        self._scrivi(f"Documenti in: {self.cfg.cartella}\nScegli dove cercare, scrivi la domanda e premi Invio "
                     "(Maiusc+Invio per andare a capo).\n", "info")

    def _pulsante(self, genitore, testo, comando, sfondo, colore):
        return tk.Button(genitore, text=testo, command=comando, bg=sfondo, fg=colore, activebackground=colore,
                         activeforeground=sfondo, relief="flat", font=("Segoe UI", 10, "bold"), cursor="hand2",
                         padx=10, pady=5, bd=0, highlightthickness=1, highlightbackground=colore)

    def _scrivi(self, testo, tag=None):
        self.chat.configure(state="normal")
        self.chat.insert("end", testo, tag)
        self.chat.configure(state="disabled")
        self.chat.see("end")

    def _occupa(self, stato, messaggio=""):
        self.occupato = stato
        self.pulsante_chiedi.configure(state="disabled" if stato else "normal", text="Attendi…" if stato else "Chiedi")
        if messaggio:
            self.stato.configure(text=messaggio, fg=GRIGIO)

    def scegli_area(self, nome):
        self.area = nome
        for n, p in self.pulsanti_area.items():
            p.configure(bg=COLORE_AREA[n] if n == nome else BIANCO, fg=BIANCO if n == nome else COLORE_AREA[n])
        self.pulsante_chiedi.configure(bg=COLORE_AREA[nome])
        if self.indice is not None:
            self.lbl_conteggio.configure(text=f"{self.indice.documenti(nome)} documenti")

    # ================= LAVORI IN SECONDO PIANO =================
    def _in_background(self, lavoro, messaggio):
        if self.occupato:
            return
        self._occupa(True, messaggio)

        def esegui():
            try:
                lavoro()
            except ollama_http.ErroreOllama as e:
                self.coda.put(("errore", str(e)))
            except Exception as e:  # mostra l'errore nella finestra invece di chiudere il programma
                self.coda.put(("errore", f"Errore: {e}"))
            finally:
                self.coda.put(("fine", None))
        threading.Thread(target=esegui, daemon=True).start()

    def prepara(self):
        def lavoro():
            installati = ollama_http.modelli(self.cfg.host)
            mancanti = [m for m in (self.cfg.modello, self.cfg.modello_embedding)
                        if not ollama_http.ha_modello(installati, m)]
            if mancanti:
                self.coda.put(("mancano", mancanti))
                return
            indice = rag.carica_indice(self.cfg, lambda t: self.coda.put(("stato", t)))
            self.coda.put(("indice", indice))
        self._in_background(lavoro, "Preparo i documenti…")

    def chiedi(self):
        testo = self.domanda.get("1.0", "end").strip()
        if not testo or self.occupato:
            return
        if self.indice is None:
            messagebox.showinfo("Assistente AI", "I documenti non sono ancora pronti (vedi la barra in basso).",
                                parent=self)
            return
        area = self.area
        self.domanda.delete("1.0", "end")
        self._scrivi(f"\nDOMANDA · {area}\n", "domanda_titolo")
        self._scrivi(testo + "\n", "domanda")
        self._scrivi("RISPOSTA\n", "risposta_titolo")

        def lavoro():
            trovati = rag.cerca(self.cfg, self.indice, testo, area)
            if not trovati:
                self.coda.put(("testo", f"Nessun documento nell'area {area}."))
                return
            for pezzo in rag.rispondi(self.cfg, testo, trovati, area):
                self.coda.put(("testo", pezzo))
            self.coda.put(("fonti", list(dict.fromkeys(p["fonte"] for p in trovati))))
        self._in_background(lavoro, "Cerco nei documenti e preparo la risposta…")

    def scarica_dai_siti(self):
        if not messagebox.askyesno("Scarica dai siti", "Scarico i documenti pubblici di Compass (trasparenza, privacy, "
                                   "reclami, antiriciclaggio) e provo con l'OAM.\nPuò richiedere qualche minuto. "
                                   "Procedo?", parent=self):
            return

        def lavoro():
            r = scarica.aggiorna(self.cfg.cartella, avanzamento=lambda t: self.coda.put(("stato", t)))
            self.coda.put(("info", "\n" + scarica.testo_riepilogo(r) + "\n"))
            self.coda.put(("ricarica", None))
        self._in_background(lavoro, "Scarico i documenti dai siti…")

    def _proponi_modelli(self, mancanti):
        if not messagebox.askyesno("Assistente AI", f"Su questo PC mancano i modelli {', '.join(mancanti)} "
                                   "(circa 1-2 GB, si scaricano una volta sola).\n\nScaricarli adesso?", parent=self):
            self._scrivi("\nModelli non scaricati: puoi farlo da ⚙ Impostazioni → Ufficio e assistente AI.\n",
                         "errore")
            return

        def lavoro():
            for modello in mancanti:
                for stato in ollama_http.scarica_modello(self.cfg.host, modello):
                    self.coda.put(("stato", stato))
            self.coda.put(("ricarica", None))
        self._in_background(lavoro, "Scarico i modelli dell'AI…")

    def _invio(self, evento):
        if evento.state & 0x0001:  # Maiusc: va a capo
            return None
        self.chiedi()
        return "break"

    def _leggi_coda(self):
        try:
            while True:
                tipo, dato = self.coda.get_nowait()
                if tipo == "stato":
                    self.stato.configure(text=dato, fg=GRIGIO)
                elif tipo == "indice":
                    self.indice = dato
                    self.stato.configure(text=f"Pronto · {self.indice.documenti('Generale')} documenti · "
                                              f"modello {self.cfg.modello}", fg=VERDE)
                    self.scegli_area(self.area)
                elif tipo == "testo":
                    self._scrivi(dato, "risposta")
                elif tipo == "fonti":
                    self._scrivi("\n\nFonti consultate:\n", "fonti")
                    for f in dato:
                        self._scrivi(f"• {f}\n", "fonti")
                elif tipo == "info":
                    self._scrivi(dato, "info")
                elif tipo == "errore":
                    self._scrivi("\n" + dato + "\n", "errore")
                    self.stato.configure(text="Assistente non pronto", fg=ROSSO)
                elif tipo == "ricarica":
                    self.after(200, self.prepara)
                elif tipo == "mancano":
                    self.after(100, lambda m=dato: self._proponi_modelli(m))
                elif tipo == "fine":
                    self._occupa(False)
        except queue.Empty:
            pass
        if self.winfo_exists():
            self.after(60, self._leggi_coda)

    # ================= AGGIUNTE A MANO =================
    def _chiedi_area(self, titolo, domanda):
        win = tk.Toplevel(self)
        win.title(titolo)
        win.configure(bg=SFONDO)
        win.transient(self)
        win.grab_set()
        scelta = {"area": None}
        tk.Label(win, text=domanda, bg=SFONDO, font=("Segoe UI", 11)).pack(padx=20, pady=(16, 10))
        riga = tk.Frame(win, bg=SFONDO)
        riga.pack(padx=20, pady=(0, 16))
        for nome in rag.AREE:
            self._pulsante(riga, nome, lambda n=nome: (scelta.update(area=n), win.destroy()), COLORE_AREA[nome],
                           BIANCO).pack(side="left", padx=4)
        self.wait_window(win)
        return scelta["area"]

    def aggiungi_documento(self):
        file = filedialog.askopenfilenames(parent=self, title="Scegli i documenti da aggiungere", filetypes=[
            ("Documenti", "*.pdf *.docx *.txt *.md *.png *.jpg *.jpeg"), ("Tutti i file", "*.*")])
        if not file:
            return
        area = self._chiedi_area("Aggiungi documento", "In quale area metto i documenti?")
        if not area:
            return
        destinazione = self.cfg.cartella / CARTELLA_AGGIUNTI[area]
        destinazione.mkdir(parents=True, exist_ok=True)
        copiati = [shutil.copy2(f, destinazione / Path(f).name) for f in file
                   if Path(f).suffix.lower() in rag.ESTENSIONI]
        messagebox.showinfo("Aggiungi documento", f"{len(copiati)} documenti copiati in:\n{destinazione}", parent=self)
        if copiati:
            self.prepara()

    def aggiungi_nota(self):
        win = tk.Toplevel(self)
        win.title("Nuova nota")
        win.configure(bg=SFONDO)
        win.transient(self)
        win.grab_set()
        win.geometry(f"{_px(620)}x{_px(470)}")
        tk.Label(win, text="Titolo", bg=SFONDO, font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=14, pady=(14, 2))
        titolo = tk.Entry(win, font=("Segoe UI", 11), relief="flat", highlightbackground="#c3ccd8", highlightthickness=1)
        titolo.pack(fill="x", padx=14)
        tk.Label(win, text="Area", bg=SFONDO, font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=14, pady=(10, 2))
        area = tk.StringVar(value=self.area)
        riga = tk.Frame(win, bg=SFONDO)
        riga.pack(anchor="w", padx=14)
        for nome in rag.AREE:
            tk.Radiobutton(riga, text=nome, variable=area, value=nome, bg=SFONDO).pack(side="left", padx=(0, 12))
        tk.Label(win, text="Testo (scrivi come lo spiegheresti a un collega)", bg=SFONDO,
                 font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=14, pady=(10, 2))
        pulsanti = tk.Frame(win, bg=SFONDO)
        pulsanti.pack(side="bottom", fill="x", padx=14, pady=12)
        testo = tk.Text(win, wrap="word", width=1, height=1, font=("Segoe UI", 11), relief="flat",
                        highlightbackground="#c3ccd8", highlightthickness=1, padx=8, pady=6)
        testo.pack(fill="both", expand=True, padx=14)

        def salva():
            t, contenuto = titolo.get().strip(), testo.get("1.0", "end").strip()
            if not t or not contenuto:
                messagebox.showwarning("Nuova nota", "Scrivi un titolo e il testo.", parent=win)
                return
            cartella = self.cfg.cartella / CARTELLA_NOTE[area.get()]
            cartella.mkdir(parents=True, exist_ok=True)
            nome = re.sub(r'[<>:"/\\|?*]', " ", t).strip()[:100] or "nota"
            f, n = cartella / f"{nome}.txt", 2
            while f.exists():
                f, n = cartella / f"{nome} ({n}).txt", n + 1
            f.write_text(f"{t}\n(Nota scritta a mano il {datetime.now():%d/%m/%Y})\n\n{contenuto}", encoding="utf-8")
            win.destroy()
            self._scrivi(f"\nNota salvata: {f}\n", "info")
            self.prepara()
        self._pulsante(pulsanti, "Salva nota", salva, VERDE, BIANCO).pack(side="right")
        self._pulsante(pulsanti, "Annulla", win.destroy, BLU_CHIARO, BLU_SCURO).pack(side="right", padx=8)
        titolo.focus_set()

    def apri_cartella(self):
        self.cfg.cartella.mkdir(parents=True, exist_ok=True)
        try:
            from ..gui import apri_con_programma_predefinito
            apri_con_programma_predefinito(str(self.cfg.cartella))
        except Exception:
            messagebox.showinfo("Cartella documenti", str(self.cfg.cartella), parent=self)

    def chiudi(self):
        if self.occupato and not messagebox.askyesno("Chiudi", "Sto ancora lavorando. Chiudere lo stesso?", parent=self):
            return
        self.destroy()


def funzione_spiega(impostazioni: dict):
    """Per la finestra dei criteri Compass: spiega(testo, scrivi, fine) oppure None se l'AI non c'è."""
    cfg = rag.configurazione(impostazioni)

    def spiega(risultato, scrivi, fine):
        def lavoro():
            try:
                for pezzo in rag.spiega_verifica(cfg, risultato):
                    scrivi(pezzo)
            except ollama_http.ErroreOllama as e:
                scrivi(f"\n{e}\n", "ko")
            finally:
                fine()
        threading.Thread(target=lavoro, daemon=True).start()
    return spiega
