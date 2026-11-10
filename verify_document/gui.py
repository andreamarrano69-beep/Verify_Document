"""Interfaccia grafica (Tkinter, inclusa in Python: nessuna installazione aggiuntiva).

Avvio:
    python -m verify_document.gui

Funzioni:
- apertura di uno o più documenti (PDF, immagini, .txt), anche trascinandoli
  nella finestra se è installato il pacchetto opzionale ``tkinterdnd2``
- analisi in background (l'interfaccia non si blocca durante l'OCR)
- esiti colorati, dati estratti, testo letto dal documento
- esportazione del report in .txt o .json
"""

from __future__ import annotations

import json
import queue
import threading
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from . import __version__
from .cli import analizza_documento
from .estrazione import ErroreEstrazione
from .report import SIMBOLI, Esito, Report, etichetta_campo, formatta_valore, report_testuale, sintesi
from .validators import formatta_euro

# --- adattamento allo schermo ------------------------------------------------------------------
# Con lo zoom di Windows (es. 150% sui portatili da 14") i caratteri si ingrandiscono da soli, le misure in
# pixel no: px() le moltiplica per lo stesso fattore. Sugli schermi piccoli (meno di 1500×880 punti
# effettivi) il programma usa la modalità COMPATTO: caratteri un punto più piccoli e testi più brevi.
SCALA = 1.0
COMPATTO = False


def px(n: float) -> int:
    return int(round(n * SCALA))


def _f(dimensione: int, stile: str = "", famiglia: str = "Segoe UI") -> tuple:
    if COMPATTO and dimensione > 8:
        dimensione -= 2 if dimensione >= 16 else 1
    return (famiglia, dimensione, stile) if stile else (famiglia, dimensione)


def breve(lungo: str, corto: str) -> str:
    return corto if COMPATTO else lungo


def misura_schermo(root: tk.Misc) -> tuple[int, int]:
    """Imposta SCALA e COMPATTO; restituisce la dimensione dello schermo in punti effettivi."""
    import os

    global SCALA, COMPATTO
    try:
        SCALA = max(1.0, float(root.tk.call("tk", "scaling")) / (96 / 72))
    except (tk.TclError, ValueError):
        SCALA = 1.0
    larghezza = int(root.winfo_screenwidth() / SCALA)
    altezza = int(root.winfo_screenheight() / SCALA)
    scelta = os.environ.get("VERIFY_DOCUMENT_COMPATTO")
    COMPATTO = scelta == "1" if scelta in ("0", "1") else (larghezza < 1500 or altezza < 880)
    return larghezza, altezza


def adatta_finestra(win: tk.Toplevel, larghezza: int, altezza: int) -> None:
    """Dimensione della finestra (in punti) ridotta se lo schermo è più piccolo, e centrata."""
    sw, sh = win.winfo_screenwidth(), win.winfo_screenheight()
    w = min(px(larghezza), sw - px(30))
    h = min(px(altezza), sh - px(90))
    win.geometry(f"{w}x{h}+{max(0, (sw - w) // 2)}+{max(0, (sh - h) // 2 - px(20))}")
    win.minsize(min(w, px(600)), min(h, px(400)))


def _dpi_windows() -> None:
    """Su Windows: caratteri nitidi con lo zoom dello schermo (altrimenti l'immagine viene sfocata)."""
    import sys

    if sys.platform == "win32":
        try:
            import ctypes

            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass


class Flusso(ttk.Frame):
    """Riga di pulsanti che va a capo quando non c'è abbastanza spazio (schermi piccoli)."""

    def __init__(self, parent, spazio: int = 4, **kw):
        super().__init__(parent, **kw)
        self.spazio = spazio
        self.bind("<Configure>", self._disponi)

    def aggiorna(self) -> None:
        self.after_idle(self._disponi)

    def _disponi(self, _evento=None) -> None:
        larghezza = self.winfo_width()
        if larghezza <= 1:
            return
        spazio = px(self.spazio)
        righe: list[list] = [[]]
        x = 0
        for figlio in self.winfo_children():
            w = figlio.winfo_reqwidth()
            if x and x + w > larghezza:
                righe.append([])
                x = 0
            righe[-1].append(figlio)
            x += w + spazio
        y = 0
        for riga in righe:
            alt_riga = max((f.winfo_reqheight() for f in riga), default=0)
            x = 0
            for f in riga:  # elementi della riga centrati in verticale
                f.place(x=x, y=y + (alt_riga - f.winfo_reqheight()) // 2)
                x += f.winfo_reqwidth() + spazio
            y += alt_riga + spazio
        altezza = max(1, y - spazio)
        if int(str(self.cget("height") or 0)) != altezza:
            self.configure(height=altezza)


TIPI = {
    "Automatico": "auto",
    "Busta paga": "busta",
    "Modello Redditi PF": "redditi",
    "Certificazione Unica (CU)": "cu",
    "Pensione (cedolino / ObisM)": "pensione",
    "Estratto contributivo": "estratto",
    "Documento d'identità": "anagrafica",
}

from .settori import SETTORI, documenti_estranei, riepilogo, stato_documenti  # noqa: E402

COLORI_VOCE = {  # stato del documento nell'elenco del settore: (testo, sfondo)
    "completo": ("#1e7b34", "#e6f4ea"),
    "parziale": ("#8a5a00", "#fff4d6"),
    "manca": ("#b3261e", "#fdecea"),
    "facoltativo": ("#57606a", "#f4f6f8"),
}
BLU = "#1a5a96"

COLORI = {
    Esito.OK: ("#1e7b34", "#e6f4ea"),
    Esito.ATTENZIONE: ("#8a5a00", "#fff4d6"),
    Esito.ERRORE: ("#b3261e", "#fde7e7"),
    Esito.INFO: ("#1a5a96", "#e8f0fb"),
}

# Dati mostrati nel riquadro di riepilogo, per tipo di documento (prima parola del tipo)
RIEPILOGO = {
    "Busta": [("netto", "Netto in busta"), ("periodo", "Periodo"),
              ("codice_fiscale_dipendente", "CF dipendente"), ("partita_iva_azienda", "P.IVA azienda"),
              ("data_assunzione", "Assunzione"), ("totale_competenze", "Lordo"),
              ("cessione_quinto", "Cessione quinto"), ("delegazione_pagamento", "Delegazione"),
              ("pignoramento", "Pignoramento"), ("quinto_cedibile", "Quinto cedibile"),
              ("cessione_disponibile", "Quinto ancora disponibile"), ("rischio_alterazione", "Rischio alterazione")],
    # regime e importo mensile sono nella fascia di sintesi in alto
    "Modello": [("periodo_imposta", "Anno d'imposta"), ("codice_fiscale_contribuente", "Codice fiscale"),
                ("reddito_annuo", "Reddito annuo"), ("imposte_annue", "Imposte annue"),
                ("quadri_compilati", "Quadri compilati"), ("rischio_alterazione", "Rischio alterazione")],
    "Certificazione": [("periodo_imposta", "Anno d'imposta"), ("reddito_totale", "Reddito annuo"),
                       ("codice_fiscale_dipendente", "Codice fiscale"), ("sostituto_imposta", "Sostituto d'imposta"),
                       ("ritenute_irpef", "Ritenute IRPEF"), ("rischio_alterazione", "Rischio alterazione")],
    "Cedolino": [("periodo", "Rata"), ("ente", "Ente"), ("categoria", "Categoria"),
                 ("numero_pensione", "N. pensione"), ("codice_fiscale_pensionato", "Codice fiscale"),
                 ("eta", "Età"), ("reddito_annuo", "Lordo annuo (13 rate)"), ("cessione_quinto", "Cessione quinto"),
                 ("delegazione_pagamento", "Delegazione"), ("pignoramento", "Pignoramento"),
                 ("quinto_cedibile", "Quinto cedibile"), ("cessione_disponibile", "Quinto ancora disponibile"),
                 ("rischio_alterazione", "Rischio alterazione")],
    "Carta": [("cognome", "Cognome"), ("nome", "Nome"), ("codice_fiscale", "Codice fiscale"),
              ("data_scadenza", "Scadenza"), ("numero_documento", "N. documento"),
              ("rischio_alterazione", "Rischio alterazione")],
}
for _t in ("Patente", "Passaporto", "Tessera", "Documento"):
    RIEPILOGO[_t] = RIEPILOGO["Carta"]
RIEPILOGO["Certificato"] = [("anno", "Anno")] + RIEPILOGO["Cedolino"][1:]

COLORE_SINTESI = "#1a5a96"

TIPI_FILE = [
    ("Documenti supportati", "*.pdf *.jpg *.jpeg *.png *.tif *.tiff *.bmp *.txt"),
    ("PDF", "*.pdf"),
    ("Immagini", "*.jpg *.jpeg *.png *.tif *.tiff *.bmp"),
    ("Testo", "*.txt"),
    ("Tutti i file", "*.*"),
]


@dataclass
class Risultato:
    percorso: Path
    report: Report | None = None
    testo: str = ""
    errore: str | None = None
    archiviato: Path | None = None   # copia nell'archivio documenti
    nuovo_in_archivio: bool = False

    @property
    def esito(self) -> Esito:
        return self.report.esito_globale if self.report else Esito.ERRORE


def _crea_root() -> tuple[tk.Tk, bool]:
    """Usa tkinterdnd2 (trascina e rilascia) se disponibile."""
    try:
        from tkinterdnd2 import TkinterDnD

        return TkinterDnD.Tk(), True
    except Exception:
        return tk.Tk(), False


class App:
    def __init__(self, root: tk.Tk, dnd: bool):
        self.root = root
        self.dnd = dnd
        self.risultati: dict[str, Risultato] = {}
        self.coda: queue.Queue[Risultato] = queue.Queue()
        self.in_corso = 0

        root.title(f"Verify Document {__version__}")
        self._icona()
        larghezza, altezza = misura_schermo(root)
        root.geometry(f"{min(px(1180), root.winfo_screenwidth())}x{min(px(720), root.winfo_screenheight())}")
        root.minsize(min(px(800), root.winfo_screenwidth()), min(px(500), root.winfo_screenheight()))
        self._massimizza()
        root.protocol("WM_DELETE_WINDOW", self.esci)  # anche la X della finestra chiede conferma
        root.bind("<Control-q>", lambda _e: self.esci())
        root.bind("<F11>", lambda _e: self.schermo_intero())
        root.bind("<Escape>", lambda _e: self.schermo_intero(False))
        self._stile()
        self._costruisci()
        self.mostra_home()
        self.root.after(150, self._controlla_coda)

    # ------------------------------------------------------------------ layout
    def _stile(self) -> None:
        st = ttk.Style(self.root)
        if "clam" in st.theme_names():
            st.theme_use("clam")
        st.configure("Treeview", rowheight=px(24 if COMPATTO else 26), font=_f(10))
        st.configure("Treeview.Heading", font=_f(10, "bold"))
        st.configure("Titolo.TLabel", font=_f(14, "bold"))
        st.configure("Esito.TLabel", font=_f(12, "bold"), padding=(10, 4))
        st.configure("Accent.TButton", font=_f(10, "bold"))
        st.configure("Esci.TButton", font=_f(10, "bold"), foreground="#b3261e")

    def _costruisci(self) -> None:
        self.settore: str | None = None
        self.home = self._costruisci_home()
        self.principale = ttk.Frame(self.root)
        # Barra superiore: azioni principali (vanno a capo se lo schermo è stretto); a destra Impostazioni ed Esci
        barra = ttk.Frame(self.principale, padding=(px(10), px(6), px(10), px(2)))
        barra.pack(fill="x")
        destra = ttk.Frame(barra)
        destra.pack(side="right", anchor="n")
        ttk.Button(destra, text="⚙  " + breve("Impostazioni", "Impost."), command=self.apri_impostazioni).pack(
            side="left")
        ttk.Button(destra, text="⏻  Esci", style="Esci.TButton", command=self.esci).pack(side="left", padx=(6, 0))
        azioni = Flusso(barra)
        azioni.pack(side="left", fill="x", expand=True, padx=(0, 8))
        ttk.Button(azioni, text="🏠  Home", command=self.mostra_home)
        ttk.Button(azioni, text="📂  " + breve("Apri documenti…", "Apri…"), style="Accent.TButton",
                   command=self.apri_file)
        ttk.Button(azioni, text="⇄  " + breve("Confronta documenti", "Confronta"), style="Accent.TButton",
                   command=self.confronta)
        ttk.Button(azioni, text="📄  Report PDF", style="Accent.TButton", command=self.esporta_pdf)
        menu_esporta = ttk.Menubutton(azioni, text="💾  Esporta ▾")
        menu = tk.Menu(menu_esporta, tearoff=0)
        menu.add_command(label="Report PDF…", command=self.esporta_pdf)
        menu.add_command(label="Testo (.txt)…", command=lambda: self.esporta("txt"))
        menu.add_command(label="Dati (.json)…", command=lambda: self.esporta("json"))
        menu_esporta["menu"] = menu
        ttk.Button(azioni, text="🗂  Archivio", command=self.apri_archivio)
        ttk.Button(azioni, text="🧮  " + breve("Conteggio estinzione", "Estinzione"), command=self.apri_estinzione)
        azioni.aggiorna()

        # riga 2: opzioni di analisi
        opzioni = Flusso(self.principale, padding=(px(10), px(2), px(10), px(4)))
        opzioni.pack(fill="x")
        riquadro_tipo = ttk.Frame(opzioni)
        ttk.Label(riquadro_tipo, text=breve("Tipo di documento:", "Tipo:")).pack(side="left")
        self.var_tipo = tk.StringVar(value="Automatico")
        ttk.Combobox(riquadro_tipo, textvariable=self.var_tipo, values=list(TIPI), state="readonly",
                     width=24).pack(side="left", padx=4)
        self.var_ocr = tk.BooleanVar(value=True)
        ttk.Checkbutton(opzioni, text=breve("Usa OCR per scansioni/foto", "OCR scansioni"), variable=self.var_ocr)
        from . import impostazioni

        self.var_archivia = tk.BooleanVar(value=impostazioni.carica()["archivia_automaticamente"] != "0")
        ttk.Checkbutton(opzioni, text=breve("Salva copia nell'archivio", "Copia in archivio"),
                        variable=self.var_archivia,
                        command=lambda: impostazioni.salva(
                            {"archivia_automaticamente": "1" if self.var_archivia.get() else "0"}))
        ttk.Button(opzioni, text="↻  Rianalizza", command=self.rianalizza)
        ttk.Button(opzioni, text="🗑  Svuota", command=self.svuota)
        opzioni.spazio = 10
        opzioni.aggiorna()

        # riga 3: documenti da chiedere per il settore scelto (verdi quando caricati)
        riquadro = tk.Frame(self.principale, bg="#ffffff", highlightthickness=1, highlightbackground="#d0d7de")
        riquadro.pack(fill="x", padx=10, pady=(0, 6))
        testa = tk.Frame(riquadro, bg="#ffffff")
        testa.pack(fill="x", padx=10, pady=(6, 2))
        self.lbl_settore = tk.Label(testa, text="", bg="#ffffff", fg=BLU, font=_f(13, "bold"))
        self.lbl_settore.pack(side="left")
        ttk.Button(testa, text="Cambia settore", command=self.mostra_home).pack(side="right")
        tk.Label(testa, text=breve("   clic su un documento per caricarlo · verde = caricato, rosso = manca",
                                   "   clic = carica · verde ok, rosso manca"),
                 bg="#ffffff", fg="#666666", font=_f(9)).pack(side="left")
        ttk.Style(self.root).configure("Bianco.TFrame", background="#ffffff")
        self.riquadro_voci = Flusso(riquadro, style="Bianco.TFrame")
        self.riquadro_voci.pack(fill="x", padx=8, pady=2)
        self.lbl_riepilogo = tk.Label(riquadro, text="", bg="#ffffff", font=_f(10, "bold"), anchor="w",
                                      justify="left")
        self.lbl_riepilogo.pack(fill="x", padx=10, pady=(2, 6))
        self.lbl_riepilogo.bind("<Configure>", lambda e: self.lbl_riepilogo.configure(wraplength=max(100, e.width)))

        corpo = ttk.PanedWindow(self.principale, orient="horizontal")
        corpo.pack(fill="both", expand=True, padx=10, pady=(0, 6))

        # Colonna sinistra: elenco documenti
        sx = ttk.Frame(corpo)
        ttk.Label(sx, text="Documenti", style="Titolo.TLabel").pack(anchor="w", pady=(0, 4))
        self.lista = ttk.Treeview(sx, columns=("data", "esito", "tipo", "mensile"), show="tree headings",
                                  selectmode="browse")
        self.titoli_lista = {"#0": "File", "data": "Data", "esito": "Esito", "tipo": "Tipo",
                             "mensile": "Netto mensile"}
        for col, titolo in self.titoli_lista.items():
            self.lista.heading(col, text=titolo, command=lambda c=col: self.ordina_lista(c, cambia=True))
        self.ordinamento = ("data", True)  # colonna, decrescente (più recenti in alto)
        self.chiavi_data: dict[str, object] = {}
        # la colonna File si allarga o si stringe con il pannello, le altre restano leggibili
        self.lista.column("#0", width=px(150 if COMPATTO else 170), minwidth=px(80), stretch=True)
        self.lista.column("data", width=px(100 if COMPATTO else 105), minwidth=px(70), stretch=False)
        self.lista.column("esito", width=px(80 if COMPATTO else 100), minwidth=px(60), anchor="center", stretch=False)
        self.lista.column("tipo", width=px(95 if COMPATTO else 120), minwidth=px(60), stretch=False)
        self.lista.column("mensile", width=px(95 if COMPATTO else 105), minwidth=px(70), anchor="e", stretch=False)
        for esito, (fg, bg) in COLORI.items():
            self.lista.tag_configure(esito.value, foreground=fg, background=bg)
        self.lista.tag_configure("attesa", foreground="#666")
        self.lista.pack(fill="both", expand=True)
        self.lista.bind("<<TreeviewSelect>>", lambda _e: self.mostra_selezionato())
        self.lista.bind("<Delete>", lambda _e: self.rimuovi_selezionato())
        self.menu_lista = tk.Menu(self.lista, tearoff=0)
        self.menu_lista.add_command(label="Rimuovi dall'elenco", command=self.rimuovi_selezionato)
        self.menu_lista.add_command(label="Elimina la copia dall'archivio…",
                                    command=lambda: self.rimuovi_selezionato(elimina_copia=True))
        self.menu_lista.add_separator()
        self.menu_lista.add_command(label="Apri il file", command=lambda: self._apri_selezionato(cartella=False))
        self.menu_lista.add_command(label="Apri la cartella del file", command=lambda: self._apri_selezionato(cartella=True))

        def menu_contestuale(evento):
            riga = self.lista.identify_row(evento.y)
            if riga:
                self.lista.selection_set(riga)
                self.menu_lista.tk_popup(evento.x_root, evento.y_root)

        self.lista.bind("<Button-3>", menu_contestuale)
        suggerimento = ("Trascina qui i file oppure usa «Apri documenti…»" if self.dnd
                        else "Usa «Apri documenti…» per aggiungere file")
        suggerimento += "  ·  F11 schermo intero  ·  Ctrl+Q esci"
        ttk.Label(sx, text=suggerimento, foreground="#666").pack(anchor="w", pady=4)

        # Fascicolo cliente: documenti presenti, da aggiungere, esito dei controlli incrociati
        intestazione_f = ttk.Frame(sx)
        intestazione_f.pack(fill="x", pady=(6, 2))
        ttk.Label(intestazione_f, text="Fascicolo cliente", style="Titolo.TLabel").pack(side="left")
        ttk.Button(intestazione_f, text="⇄  Confronto completo", command=self.confronta).pack(side="right")
        self.txt_fascicolo = tk.Text(sx, height=6 if COMPATTO else 10, wrap="word", font=_f(9), relief="flat",
                                     background="#f4f6f8", padx=8, pady=6, cursor="arrow")
        self.txt_fascicolo.pack(fill="x")
        for tag, opzioni in {"cliente": {"font": _f(10, "bold")},
                             "presente": {"foreground": "#1e7b34"},
                             "manca": {"foreground": "#8a5a00"},
                             "nota": {"foreground": "#666666"},
                             **{e.value: {"foreground": COLORI[e][0], "font": _f(9, "bold")} for e in COLORI}
                             }.items():
            self.txt_fascicolo.tag_configure(tag, **opzioni)
        self.aggiorna_fascicolo()
        corpo.add(sx, weight=1)

        # Colonna destra: dettaglio
        dx = ttk.Frame(corpo)
        intest = ttk.Frame(dx)
        intest.pack(fill="x")
        self.lbl_titolo = ttk.Label(intest, text="Nessun documento selezionato", style="Titolo.TLabel")
        self.lbl_titolo.pack(side="left")
        self.lbl_esito = tk.Label(intest, text="", font=_f(12, "bold"), padx=12, pady=4)
        self.lbl_esito.pack(side="right")

        # Fascia di sintesi: regime / tipo di reddito e importo mensile, in grande
        st = ttk.Style(self.root)
        st.configure("Banner.TFrame", background=COLORE_SINTESI)
        st.configure("Riepilogo.TFrame", background="#f4f6f8")
        self.banner = tk.Frame(dx, bg=COLORE_SINTESI)
        self.banner_celle = Flusso(self.banner, spazio=0, style="Banner.TFrame")
        self.banner_celle.pack(fill="x")
        self.banner_nota = tk.Label(self.banner, bg=COLORE_SINTESI, fg="#c9dcf2", font=_f(9), anchor="w",
                                    justify="left")
        self.banner_nota.pack(fill="x", padx=px(12), pady=(0, px(4)))
        bordo = tk.Frame(dx, bg="#f4f6f8", highlightthickness=1, highlightbackground="#d0d7de")
        bordo.pack(fill="x", pady=(6, 0))
        self.riepilogo = Flusso(bordo, spazio=0, style="Riepilogo.TFrame")
        self.riepilogo.pack(fill="x")
        self.riepilogo_bordo = bordo

        self.schede = ttk.Notebook(dx)
        self.schede.pack(fill="both", expand=True, pady=(6, 0))

        # Scheda controlli
        f1 = ttk.Frame(self.schede)
        self.tab_controlli = ttk.Treeview(f1, columns=("esito", "controllo", "dettaglio"),
                                          show="headings")
        for col, testo, w in [("esito", "", 40), ("controllo", "Controllo", 210),
                              ("dettaglio", "Dettaglio", 560)]:
            self.tab_controlli.heading(col, text=testo)
            self.tab_controlli.column(col, width=px(w), anchor="center" if col == "esito" else "w",
                                      stretch=col == "dettaglio")
        for esito, (fg, bg) in COLORI.items():
            self.tab_controlli.tag_configure(esito.value, foreground=fg, background=bg)
        self.tab_controlli.tag_configure("gruppo", foreground="#ffffff", background="#57606a",
                                         font=_f(9, "bold"))
        self._con_scrollbar(f1, self.tab_controlli)
        self.tab_controlli.bind("<Double-1>", self._mostra_dettaglio_controllo)
        self.schede.add(f1, text="  Controlli  ")

        # Scheda dati estratti
        f2 = ttk.Frame(self.schede)
        self.tab_dati = ttk.Treeview(f2, columns=("campo", "valore"), show="headings")
        self.tab_dati.heading("campo", text="Campo")
        self.tab_dati.heading("valore", text="Valore")
        self.tab_dati.column("campo", width=px(260), stretch=False)
        self.tab_dati.column("valore", width=px(500))
        self.tab_dati.tag_configure("vuoto", foreground="#999")
        self._con_scrollbar(f2, self.tab_dati)
        self.schede.add(f2, text="  Dati estratti  ")

        # Scheda testo letto (con copia anonimizzata, da inviare per l'assistenza senza dati personali)
        f3 = ttk.Frame(self.schede)
        barra_testo = ttk.Frame(f3, padding=(0, 4))
        barra_testo.grid(row=0, column=0, columnspan=2, sticky="ew")
        ttk.Button(barra_testo, text="📋  Copia testo anonimizzato", command=self.copia_testo_anonimizzato).pack(side="left")
        ttk.Label(barra_testo, text="  senza codice fiscale, nome e IBAN: da incollare quando chiedi assistenza",
                  foreground="#666").pack(side="left")
        interno = ttk.Frame(f3)
        interno.grid(row=1, column=0, columnspan=2, sticky="nsew")
        f3.rowconfigure(1, weight=1)
        f3.columnconfigure(0, weight=1)
        self.txt = tk.Text(interno, wrap="none", font=_f(10, famiglia="Consolas"))
        self._con_scrollbar(interno, self.txt, orizzontale=True)
        self.schede.add(f3, text="  Testo letto  ")
        corpo.add(dx, weight=3)

        # Barra di stato
        self.var_stato = tk.StringVar(value="Pronto. Tutti i documenti vengono elaborati in locale.")
        self.avviso_ocr_mostrato = False
        self.root.after(300, self._stato_ocr)
        stato = ttk.Frame(self.principale, padding=(10, 2))
        stato.pack(fill="x", side="bottom")
        ttk.Label(stato, textvariable=self.var_stato).pack(side="left")
        self.progress = ttk.Progressbar(stato, mode="indeterminate", length=160)
        self.progress.pack(side="right")

        if self.dnd:
            from tkinterdnd2 import DND_FILES

            self.root.drop_target_register(DND_FILES)
            self.root.dnd_bind("<<Drop>>", lambda e: self.aggiungi(self.root.tk.splitlist(e.data)))

    @staticmethod
    def _con_scrollbar(parent, widget, orizzontale: bool = False) -> None:
        sy = ttk.Scrollbar(parent, orient="vertical", command=widget.yview)
        widget.configure(yscrollcommand=sy.set)
        widget.grid(row=0, column=0, sticky="nsew")
        sy.grid(row=0, column=1, sticky="ns")
        if orizzontale:
            sx = ttk.Scrollbar(parent, orient="horizontal", command=widget.xview)
            widget.configure(xscrollcommand=sx.set)
            sx.grid(row=1, column=0, sticky="ew")
        parent.rowconfigure(0, weight=1)
        parent.columnconfigure(0, weight=1)

    # ---------------------------------------------------------------- azioni
    def apri_file(self) -> None:
        from . import impostazioni

        imp = impostazioni.carica()
        iniziale = next((c for c in (imp["cartella_apertura"], imp["ultima_cartella"]) if c and Path(c).is_dir()), None)
        percorsi = filedialog.askopenfilenames(title="Scegli i documenti da verificare (vista Dettagli → "
                                               "clic su «Ultima modifica» per ordinare per data)",
                                               filetypes=TIPI_FILE, initialdir=iniziale)
        if percorsi:
            impostazioni.salva({"ultima_cartella": str(Path(percorsi[0]).parent)})
            self.aggiungi(percorsi)

    # ------------------------------------------------------------------ home
    def _costruisci_home(self) -> tk.Frame:
        sfondo = "#f4f6f8"
        home = tk.Frame(self.root, bg=sfondo)
        centro = tk.Frame(home, bg=sfondo)
        centro.place(relx=0.5, rely=0.45, anchor="center")
        tk.Label(centro, text="Verify Document", bg=sfondo, fg=BLU, font=_f(34, "bold")).pack()
        sottotitolo = tk.Label(centro, text="Verifica di buste paga, pensioni, CU, Modello Redditi, estratti "
                               "contributivi e documenti d'identità", bg=sfondo, fg="#444444", font=_f(12))
        sottotitolo.pack(pady=(2, 0))
        tk.Label(centro, text="Tutto in locale: nessun dato inviato su internet", bg=sfondo, fg="#777777",
                 font=_f(10)).pack(pady=(0, px(14 if COMPATTO else 26)))
        tk.Label(centro, text="Scegli il settore del cliente", bg=sfondo, fg="#1f2328",
                 font=_f(15, "bold")).pack(pady=(0, px(8 if COMPATTO else 12)))
        griglia = tk.Frame(centro, bg=sfondo)
        griglia.pack()
        colonne = []
        for nome, info in SETTORI.items():
            col = tk.Frame(griglia, bg=sfondo)
            richiesti = ", ".join(v.etichetta for v in info["documenti"] if v.richiesto)
            b = tk.Button(col, text=f"{info['icona']}\n{nome}", font=_f(20, "bold"), width=11,
                          height=2 if COMPATTO else 3, bg="#ffffff", fg=BLU, activebackground="#e8f0f8",
                          activeforeground=BLU, relief="flat", bd=0, highlightthickness=2,
                          highlightbackground="#c9d6e3", cursor="hand2", command=lambda s=nome: self.entra_settore(s))
            b.pack()
            b.bind("<Enter>", lambda _e, w=b: w.configure(bg="#e8f0f8", highlightbackground=BLU))
            b.bind("<Leave>", lambda _e, w=b: w.configure(bg="#ffffff", highlightbackground="#c9d6e3"))
            tk.Label(col, text=info["descrizione"], bg=sfondo, fg="#444444", font=_f(10, "bold"),
                     wraplength=px(220)).pack(pady=(px(6), 0))
            tk.Label(col, text=richiesti, bg=sfondo, fg="#777777", font=_f(9),
                     wraplength=px(220)).pack(pady=(2, 0))
            colonne.append(col)

        def disponi(_evento=None):
            """4 settori in fila; su finestre strette 2 per riga."""
            larghezza = home.winfo_width()
            per_riga = 4 if larghezza >= sum(c.winfo_reqwidth() for c in colonne) + px(120) else 2
            for n, c in enumerate(colonne):
                c.grid(row=n // per_riga, column=n % per_riga, padx=px(8), pady=px(6), sticky="n")
            sottotitolo.configure(wraplength=max(px(300), larghezza - px(60)))

        home.bind("<Configure>", disponi)
        piede = tk.Frame(home, bg=sfondo)
        piede.pack(side="bottom", fill="x", padx=20, pady=16)
        ttk.Button(piede, text="⏻  Esci", style="Esci.TButton", command=self.esci).pack(side="right")
        ttk.Button(piede, text="⚙  Impostazioni", command=self.apri_impostazioni).pack(side="right", padx=8)
        tk.Label(piede, text=f"versione {__version__}", bg=sfondo, fg="#999999",
                 font=_f(9)).pack(side="left")
        return home

    def mostra_home(self) -> None:
        self.principale.pack_forget()
        self.home.pack(fill="both", expand=True)

    def entra_settore(self, settore: str) -> None:
        if self.settore and settore != self.settore and self.risultati and not self.in_corso:
            nuovo = messagebox.askyesnocancel(
                "Cambio settore", f"Sono aperti {len(self.risultati)} documenti.\n\nIniziare un nuovo cliente?\n"
                "Sì = svuota l'elenco   ·   No = tieni i documenti", parent=self.root)
            if nuovo is None:
                return
            if nuovo:
                self.svuota()
        self.settore = settore
        info = SETTORI[settore]
        self.lbl_settore.configure(text=f"{info['icona']}  {settore} — documenti del cliente")
        self.root.title(f"Verify Document {__version__} — {settore}")
        self.home.pack_forget()
        self.principale.pack(fill="both", expand=True)
        self.aggiorna_elenco_settore()

    def aggiorna_elenco_settore(self) -> None:
        """Pulsanti dei documenti del settore: verde se caricato, giallo se ne servono altri, rosso se manca."""
        if not self.settore:
            return
        for w in self.riquadro_voci.winfo_children():
            w.destroy()
        reports = [r.report for r in self.risultati.values() if r.report]
        stati = stato_documenti(self.settore, reports)
        for st in stati:
            fg, bg = COLORI_VOCE[st.stato]
            nota = st.voce.nota or ("facoltativo" if not st.voce.richiesto else "")
            if not st.voce.richiesto and st.stato == "facoltativo":
                nota = f"facoltativo · {st.voce.nota}" if st.voce.nota else "facoltativo"
            b = tk.Button(self.riquadro_voci, text=st.testo if COMPATTO else f"{st.testo}\n{nota}",
                          justify="left", anchor="w",
                          font=_f(10, "bold"), fg=fg, bg=bg, activebackground=bg, activeforeground=fg,
                          relief="flat", bd=0, highlightthickness=1, highlightbackground=fg, padx=10, pady=4,
                          cursor="hand2", command=lambda t=st.voce.tipo_analisi: self.scansiona_prodotto(t))
        self.riquadro_voci.aggiorna()
        testo = riepilogo(stati)
        estranei = documenti_estranei(self.settore, reports)
        if estranei:
            testo += "   ·   altri documenti aperti: " + ", ".join(estranei)
        completo = all(s.stato == "completo" for s in stati if s.voce.richiesto)
        self.lbl_riepilogo.configure(text=testo, fg="#1e7b34" if completo else "#8a5a00")

    def scansiona_prodotto(self, tipo: str) -> None:
        """Imposta il tipo di documento del prodotto scelto e apre i file."""
        self.var_tipo.set(tipo)
        self.var_stato.set(f"{self.settore or ''} · {tipo}: scegli i documenti")
        try:
            self.apri_file()
        finally:
            self.var_tipo.set("Automatico")  # i file trascinati dopo vengono riconosciuti da soli

    def apri_estinzione(self) -> None:
        FinestraEstinzione(self.root)

    def aggiungi(self, percorsi) -> None:
        for p in percorsi:
            p = Path(p)
            if p.is_dir():
                continue
            chiave = str(p.resolve())
            if self.lista.exists(chiave):
                self.lista.item(chiave, values=("", "in corso…", "", ""), tags=("attesa",))
            else:
                self.lista.insert("", "end", iid=chiave, text=p.name, values=("", "in corso…", "", ""),
                                  tags=("attesa",))
            self._avvia_analisi(p, chiave)
        if not self.lista.selection() and self.lista.get_children():
            self.lista.selection_set(self.lista.get_children()[-1])

    def _avvia_analisi(self, percorso: Path, chiave: str) -> None:
        from . import impostazioni
        from .archivio import cartella_archivio

        tipo = TIPI[self.var_tipo.get()]
        ocr = self.var_ocr.get()
        archivio = cartella_archivio(impostazioni.carica()) if self.var_archivia.get() else None
        self.in_corso += 1
        self.progress.start(12)
        self.var_stato.set(f"Analisi in corso: {percorso.name}…")

        def lavoro():
            ris = Risultato(percorso)
            try:
                ris.testo, ris.report = analizza_documento(percorso, tipo, usa_ocr=ocr)
            except (ErroreEstrazione, ValueError) as e:
                ris.errore = str(e)
            except Exception as e:  # errore imprevisto: non bloccare l'interfaccia
                ris.errore = f"Errore imprevisto: {e!r}"
            if archivio is not None and ris.report is not None:
                from .archivio import archivia

                try:
                    ris.archiviato, ris.nuovo_in_archivio = archivia(percorso, ris.report, archivio)
                except OSError:
                    pass  # archivio non scrivibile: l'analisi resta valida
            self.coda.put((chiave, ris))

        threading.Thread(target=lavoro, daemon=True).start()

    def _stato_ocr(self) -> None:
        from .estrazione import trova_tesseract

        percorso, lingua = trova_tesseract()
        if self.risultati or self.in_corso:  # analisi già avviate: non coprire il loro messaggio
            return
        if percorso:
            self.var_stato.set(f"Pronto. OCR attivo (Tesseract, lingua {lingua or 'predefinita'}) per scansioni "
                               "e foto. Tutti i documenti vengono elaborati in locale.")
        else:
            self.var_stato.set("Pronto. OCR non disponibile: scansioni e foto non si possono leggere "
                               "(installa Tesseract; diagnosi: python -m verify_document.diagnosi).")

    def _controlla_coda(self) -> None:
        aggiornati = False
        try:
            while True:
                chiave, ris = self.coda.get_nowait()
                self.in_corso -= 1
                self.risultati[chiave] = ris
                if ris.errore and ris.errore.startswith("Questo documento è una scansione") \
                        and not self.avviso_ocr_mostrato:
                    self.avviso_ocr_mostrato = True
                    self.root.after(100, lambda testo=ris.errore: messagebox.showwarning(
                        "Serve l'OCR", testo, parent=self.root))
                if self.lista.exists(chiave):
                    esito = ris.esito
                    testo_esito = f"{SIMBOLI[esito]} {esito.value}" if ris.report else "✘ ILLEGGIBILE"
                    tipo = ris.report.tipo_documento if ris.report else "—"
                    sx = sintesi(ris.report) if ris.report else None
                    mensile = formatta_euro(sx.mensile_netto) if sx and sx.mensile_netto is not None else ""
                    from .archivio import data_documento, descrizione_periodo

                    data_doc = data_documento(ris.report)
                    if data_doc is None:  # documenti senza periodo: data del file
                        from datetime import datetime

                        data_doc = datetime.fromtimestamp(ris.percorso.stat().st_mtime).date()
                        testo_data = f"{data_doc:%d/%m/%Y}"
                    else:
                        testo_data = descrizione_periodo(ris.report)
                    self.chiavi_data[chiave] = data_doc
                    self.lista.item(chiave, values=(testo_data, testo_esito, tipo, mensile), tags=(esito.value,))
                    aggiornati = True
                if chiave in self.lista.selection():
                    self.mostra_selezionato()
        except queue.Empty:
            pass
        if aggiornati:
            self.ordina_lista(*self.ordinamento)
        if self.in_corso <= 0 and aggiornati:
            self.in_corso = 0
            self.progress.stop()
            if self.risultati:
                n = len(self.risultati)
                errori = sum(1 for r in self.risultati.values() if r.esito == Esito.ERRORE)
                nuovi = sum(1 for r in self.risultati.values() if r.nuovo_in_archivio)
                stato = f"{n} documenti analizzati — {errori} con errori."
                if nuovi:
                    stato += f" {nuovi} salvati nell'archivio documenti."
                self.var_stato.set(stato)
            self.aggiorna_fascicolo()
        elif self.in_corso <= 0:
            self.in_corso = 0
            self.progress.stop()
        self.root.after(150, self._controlla_coda)

    def mostra_selezionato(self) -> None:
        sel = self.lista.selection()
        for t in (self.tab_controlli, self.tab_dati):
            t.delete(*t.get_children())
        self.txt.delete("1.0", "end")
        self._aggiorna_riepilogo(None)
        if not sel:
            return
        ris = self.risultati.get(sel[0])
        nome = Path(sel[0]).name
        if ris is None:
            self.lbl_titolo.config(text=f"{nome} — analisi in corso…")
            self.lbl_esito.config(text="", bg=self.root.cget("bg"))
            return

        self.txt.insert("1.0", ris.testo or "")
        if ris.errore:
            self.lbl_titolo.config(text=nome)
            fg, bg = COLORI[Esito.ERRORE]
            self.lbl_esito.config(text="✘ NON LEGGIBILE", fg=fg, bg=bg)
            self.tab_controlli.insert("", "end", values=("✘", "Lettura documento", ris.errore),
                                      tags=(Esito.ERRORE.value,))
            return

        r = ris.report
        self._aggiorna_riepilogo(r)
        self.lbl_titolo.config(text=f"{nome}  ·  {r.tipo_documento}")
        fg, bg = COLORI[r.esito_globale]
        self.lbl_esito.config(text=f"{SIMBOLI[r.esito_globale]} {r.esito_globale.value}", fg=fg, bg=bg)
        for gruppo, controlli in r.gruppi().items():
            self.tab_controlli.insert("", "end", values=("", gruppo.upper(), ""), tags=("gruppo",))
            for c in controlli:
                self.tab_controlli.insert("", "end", values=(SIMBOLI[c.esito], c.nome, c.dettaglio),
                                          tags=(c.esito.value,))
        for k, v in r.dati.items():
            self.tab_dati.insert("", "end", values=(etichetta_campo(k), formatta_valore(k, v)),
                                 tags=("vuoto",) if v is None else ())

    def _aggiorna_banner(self, r: Report | None) -> None:
        for w in self.banner_celle.winfo_children():
            w.destroy()
        s = sintesi(r) if r else None
        if s is None:
            self.banner.pack_forget()
            return
        self.banner.pack(fill="x", pady=(6, 0), before=self.riepilogo_bordo)
        blocchi = [(s.etichetta, s.categoria or "non determinato", 15),
                   ("Importo mensile lordo", formatta_euro(s.mensile_lordo), 20),
                   ("Importo mensile netto", formatta_euro(s.mensile_netto), 20)]
        for i, (titolo, valore, dim) in enumerate(blocchi):
            cella = tk.Frame(self.banner_celle, bg=COLORE_SINTESI, padx=px(12 if COMPATTO else 16),
                             pady=px(5 if COMPATTO else 8))
            tk.Label(cella, text=titolo.upper(), bg=COLORE_SINTESI, fg="#c9dcf2",
                     font=_f(9, "bold")).pack(anchor="w")
            tk.Label(cella, text=valore, bg=COLORE_SINTESI, fg="#ffffff", font=_f(dim, "bold"),
                     wraplength=px(340), justify="left").pack(anchor="w")
        self.banner_celle.aggiorna()
        self.banner_nota.configure(text=s.nota)

    def _aggiorna_riepilogo(self, r: Report | None) -> None:
        self._aggiorna_banner(r)
        for w in self.riepilogo.winfo_children():
            w.destroy()
        if r is None:
            return
        campi = [(etichetta, formatta_valore(k, r.dati.get(k)))
                 for k, etichetta in RIEPILOGO.get(r.tipo_documento.split(" ")[0], [])
                 if r.dati.get(k) is not None]
        for i, (etichetta, valore) in enumerate(campi):
            cella = tk.Frame(self.riepilogo, bg="#f4f6f8", padx=px(10 if COMPATTO else 12), pady=px(4 if COMPATTO else 6),
                             width=px(150))
            tk.Label(cella, text=etichetta.upper(), bg="#f4f6f8", fg="#57606a",
                     font=_f(8, "bold")).pack(anchor="w")
            tk.Label(cella, text=valore, bg="#f4f6f8", fg="#1f2328",
                     font=_f(12, "bold")).pack(anchor="w")
        self.riepilogo.aggiorna()

    def _mostra_dettaglio_controllo(self, _evento) -> None:
        sel = self.tab_controlli.selection()
        if sel:
            _, nome, dettaglio = self.tab_controlli.item(sel[0], "values")
            if not dettaglio:
                return
            messagebox.showinfo(nome, dettaglio, parent=self.root)

    def rianalizza(self) -> None:
        """Rianalizza tutti i documenti (es. dopo aver cambiato il tipo)."""
        for chiave in self.lista.get_children():
            self.lista.item(chiave, values=("", "in corso…", "", ""), tags=("attesa",))
            self.risultati.pop(chiave, None)
            self._avvia_analisi(Path(chiave), chiave)

    def _icona(self) -> None:
        from .risorse import risorsa

        try:
            self._img_icona = tk.PhotoImage(file=str(risorsa("assets/icona.png")))
            self.root.iconphoto(True, self._img_icona)
        except (tk.TclError, OSError):
            pass

    def _massimizza(self) -> None:
        """Apre la finestra a tutto schermo (massimizzata, con la barra delle applicazioni visibile)."""
        try:
            self.root.state("zoomed")  # Windows e macOS
        except tk.TclError:
            try:
                self.root.attributes("-zoomed", True)  # Linux
            except tk.TclError:
                larghezza, altezza = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
                self.root.geometry(f"{larghezza}x{altezza}+0+0")

    def schermo_intero(self, attivo: bool | None = None) -> None:
        """F11: schermo intero senza bordi; Esc: torna alla finestra massimizzata."""
        if attivo is None:
            attivo = not self.root.attributes("-fullscreen")
        self.root.attributes("-fullscreen", attivo)
        if not attivo:
            self._massimizza()

    def esci(self) -> None:
        if self.in_corso:
            domanda = "Ci sono analisi ancora in corso. Uscire comunque?"
        elif self.risultati:
            domanda = "Uscire da Verify Document?\nI report non esportati andranno persi."
        else:
            domanda = None
        if domanda and not messagebox.askyesno("Esci", domanda, icon="question", parent=self.root):
            return
        self.root.destroy()

    # --- ordinamento, rimozione, archivio ------------------------------------------
    def ordina_lista(self, colonna: str, decrescente: bool | None = None, cambia: bool = False) -> None:
        if cambia:  # clic sull'intestazione: stessa colonna inverte, nuova colonna parte decrescente per la data
            col_att, dec_att = self.ordinamento
            decrescente = (not dec_att) if col_att == colonna else (colonna in ("data", "mensile"))
        elif decrescente is None:
            decrescente = self.ordinamento[1]
        self.ordinamento = (colonna, decrescente)

        def chiave(iid):
            if colonna == "#0":
                return self.lista.item(iid, "text").lower()
            if colonna == "data":
                d = self.chiavi_data.get(iid)
                return d.toordinal() if d is not None else (-1 if decrescente else 10**9)
            if colonna == "mensile":
                ris = self.risultati.get(iid)
                sx = sintesi(ris.report) if ris and ris.report else None
                return float(sx.mensile_netto) if sx and sx.mensile_netto is not None else -1.0
            return str(self.lista.set(iid, colonna)).lower()

        for i, iid in enumerate(sorted(self.lista.get_children(), key=chiave, reverse=decrescente)):
            self.lista.move(iid, "", i)
        for col, titolo in self.titoli_lista.items():
            freccia = (" ▼" if decrescente else " ▲") if col == colonna else ""
            self.lista.heading(col, text=titolo + freccia)

    def copia_testo_anonimizzato(self) -> None:
        from .anonimizza import anonimizza

        sel = self.lista.selection()
        ris = self.risultati.get(sel[0]) if sel else None
        if not ris or not ris.testo:
            messagebox.showinfo("Copia testo", "Seleziona un documento analizzato.", parent=self.root)
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(anonimizza(ris.testo, ris.report))
        self.var_stato.set("Testo anonimizzato copiato: incollalo dove serve (controlla comunque che non restino "
                           "dati personali, ad esempio l'indirizzo).")

    def aggiorna_fascicolo(self) -> None:
        """Riepilogo per cliente: documenti presenti, cosa aggiungere per altri controlli, esito incrociato."""
        from .confronto import fascicolo

        self.aggiorna_elenco_settore()
        t = self.txt_fascicolo
        t.configure(state="normal")
        t.delete("1.0", "end")
        schede = fascicolo(self._validi()) if not self.in_corso else []
        if not schede:
            t.insert("end", "Apri i documenti di un cliente (buste paga, CU, Modello Redditi, cedolini di pensione, "
                            "documento d'identità): qui vedrai quali controlli incrociati sono possibili e quali "
                            "documenti aggiungere.", "nota")
        for i, s in enumerate(schede):
            if i:
                t.insert("end", "\n")
            t.insert("end", f"{s.nominativo or 'Cliente'}  ·  {s.codice_fiscale}\n", "cliente")
            for voce in s.presenti:
                t.insert("end", f"✔ {voce}\n", "presente")
            if s.esito is not None:
                testo = {Esito.OK: "tutti coerenti", Esito.ATTENZIONE: f"{s.da_verificare} da verificare",
                         Esito.ERRORE: f"{s.da_verificare} da verificare (anomalie)"}[s.esito]
                t.insert("end", "Controlli incrociati: ", "nota")
                t.insert("end", f"{SIMBOLI[s.esito]} {s.esito.value} – {testo}\n", s.esito.value)
            for voce in s.suggerimenti:
                iniziale = voce[0].lower() if voce[1:2].islower() else voce[0]  # "CU" resta maiuscolo
                t.insert("end", f"+ Aggiungi {iniziale}{voce[1:]}\n", "manca")
        t.configure(state="disabled")

    def rimuovi_selezionato(self, elimina_copia: bool = False) -> None:
        sel = self.lista.selection()
        if not sel:
            return
        chiave = sel[0]
        ris = self.risultati.get(chiave)
        if elimina_copia:
            from . import impostazioni
            from .archivio import cartella_archivio, e_in_archivio, elimina

            archivio = cartella_archivio(impostazioni.carica())
            copia = ris.archiviato if ris and ris.archiviato else (Path(chiave) if e_in_archivio(Path(chiave), archivio) else None)
            if copia is None or not copia.exists():
                messagebox.showinfo("Archivio", "Questo documento non ha una copia nell'archivio.", parent=self.root)
                return
            if not messagebox.askyesno("Elimina dall'archivio",
                                       f"Eliminare la copia nell'archivio?\n{copia.name}\n\n"
                                       "Il file originale non viene toccato.", parent=self.root):
                return
            try:
                dove = elimina(copia, archivio)
            except (OSError, ValueError) as e:
                messagebox.showerror("Archivio", str(e), parent=self.root)
                return
            self.var_stato.set(f"Copia eliminata dall'archivio ({dove}): {copia.name}")
        self.lista.delete(chiave)
        self.risultati.pop(chiave, None)
        self.chiavi_data.pop(chiave, None)
        figli = self.lista.get_children()
        if figli:
            self.lista.selection_set(figli[0])
        else:
            self.mostra_selezionato()
        self.aggiorna_fascicolo()

    def _apri_selezionato(self, cartella: bool) -> None:
        sel = self.lista.selection()
        if sel:
            p = Path(sel[0])
            apri_con_programma_predefinito(str(p.parent if cartella else p))

    def apri_archivio(self) -> None:
        FinestraArchivio(self)

    def svuota(self) -> None:
        if self.in_corso:
            messagebox.showwarning("Attendere", "Analisi ancora in corso.", parent=self.root)
            return
        self.lista.delete(*self.lista.get_children())
        self.risultati.clear()
        self.chiavi_data.clear()
        self.aggiorna_fascicolo()
        self.lbl_titolo.config(text="Nessun documento selezionato")
        self.lbl_esito.config(text="", bg=self.root.cget("bg"))
        self.mostra_selezionato()
        self.var_stato.set("Pronto.")

    def confronta(self) -> None:
        from .confronto import confronta

        if self.in_corso:
            messagebox.showwarning("Attendere", "Analisi ancora in corso.", parent=self.root)
            return
        validi = [(r.percorso.name, r.report) for r in self.risultati.values() if r.report]
        if len(validi) < 2:
            messagebox.showinfo("Confronto", "Apri almeno 2 documenti dello stesso cliente "
                                "(es. più buste paga, carta d'identità, Modello Redditi).", parent=self.root)
            return
        esito = confronta(validi)
        FinestraConfronto(self.root, esito, validi)
        self.var_stato.set(f"Confronto tra {len(validi)} documenti: {esito.report.esito_globale.value}")

    def _validi(self) -> list[tuple[str, Report]]:
        return [(r.percorso.name, r.report) for r in self.risultati.values() if r.report]

    def esporta(self, formato: str = "txt") -> None:
        validi = [r for r in self.risultati.values() if r.report]
        if not validi:
            messagebox.showinfo("Esporta", "Nessun report da esportare.", parent=self.root)
            return
        tipi = {"txt": [("Testo", "*.txt")], "json": [("JSON", "*.json")]}[formato]
        dest = filedialog.asksaveasfilename(title="Salva report", defaultextension=f".{formato}",
                                            initialfile=f"report_verifica.{formato}", filetypes=tipi)
        if not dest:
            return
        documenti = [(r.percorso.name, r.report) for r in validi]
        if _oscura_esportazioni():
            from .anonimizza import oscura_documenti

            documenti, _ = oscura_documenti(documenti)
        if formato == "json":
            dati = [{"file": nome, **report.to_dict()} for nome, report in documenti]
            contenuto = json.dumps(dati, ensure_ascii=False, indent=2)
        else:
            contenuto = "\n".join(report_testuale(nome, report) for nome, report in documenti)
        Path(dest).write_text(contenuto, encoding="utf-8")
        self.var_stato.set(f"Report salvato in {dest}" + (" (dati personali oscurati)" if _oscura_esportazioni() else ""))

    def esporta_pdf(self) -> None:
        from datetime import date

        from . import impostazioni
        from .confronto import confronta

        if self.in_corso:
            messagebox.showwarning("Attendere", "Analisi ancora in corso.", parent=self.root)
            return
        validi = self._validi()
        if not validi:
            messagebox.showinfo("Report PDF", "Apri prima uno o più documenti.", parent=self.root)
            return
        imp = impostazioni.carica()
        if not imp["studio"] and messagebox.askyesno(
                "Report PDF", "Non hai ancora inserito i dati del tuo studio e il logo.\n"
                "Vuoi inserirli ora? (compariranno nell'intestazione del report)", parent=self.root):
            self.apri_impostazioni(attendi=True)
            imp = impostazioni.carica()
        cf = next((r.dati.get(k) for _, r in validi for k in ("codice_fiscale", "codice_fiscale_dipendente",
                   "codice_fiscale_contribuente", "codice_fiscale_pensionato") if r.dati.get(k)), "cliente")
        dest = filedialog.asksaveasfilename(
            title="Salva report PDF", defaultextension=".pdf", filetypes=[("PDF", "*.pdf")],
            initialfile=(f"report_cliente_{date.today():%Y%m%d}.pdf" if _oscura_esportazioni()
                         else f"report_{cf}_{date.today():%Y%m%d}.pdf"))
        if not dest:
            return
        try:
            from .report_pdf import genera_report_pdf

            esito_confronto = confronta(validi) if len(validi) >= 2 else None
            genera_report_pdf(dest, validi, esito_confronto, imp)
        except ImportError:
            messagebox.showerror("Report PDF", "Manca la libreria reportlab.\nNel terminale: pip install reportlab",
                                 parent=self.root)
            return
        except Exception as e:
            messagebox.showerror("Report PDF", f"Impossibile creare il PDF:\n{e}", parent=self.root)
            return
        self.var_stato.set(f"Report PDF salvato in {dest}")
        if messagebox.askyesno("Report PDF", f"Report creato:\n{dest}\n\nVuoi aprirlo?", parent=self.root):
            apri_con_programma_predefinito(dest)

    def apri_impostazioni(self, attendi: bool = False) -> None:
        finestra = FinestraImpostazioni(self.root)
        if attendi:
            self.root.wait_window(finestra.win)


def _oscura_esportazioni() -> bool:
    from . import impostazioni

    return impostazioni.carica().get("oscura_dati_esportati", "1") != "0"


def apri_con_programma_predefinito(percorso: str) -> None:
    import os
    import subprocess
    import sys

    try:
        if sys.platform.startswith("win"):
            os.startfile(percorso)  # noqa: S606 - file creato dal programma
        elif sys.platform == "darwin":
            subprocess.Popen(["open", percorso])
        else:
            subprocess.Popen(["xdg-open", percorso])
    except Exception:
        pass


class FinestraImpostazioni:
    """Dati dello studio e logo da mostrare nel report PDF."""

    CAMPI = [("studio", "Nome studio / agenzia"), ("indirizzo", "Indirizzo"), ("contatti", "Telefono, email, sito"),
             ("partita_iva", "Partita IVA"), ("operatore", "Operatore (firma del report)")]

    def __init__(self, parent: tk.Tk):
        from . import impostazioni

        self.imp = impostazioni
        dati = impostazioni.carica()
        self.win = tk.Toplevel(parent)
        self.win.title("Impostazioni del report")
        self.win.transient(parent)
        self.win.resizable(False, False)
        corpo = ttk.Frame(self.win, padding=16)
        corpo.pack(fill="both", expand=True)
        ttk.Label(corpo, text="Dati che compaiono nell'intestazione del report PDF",
                  style="Titolo.TLabel").grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 10))
        self.var = {}
        for i, (chiave, etichetta) in enumerate(self.CAMPI, start=1):
            ttk.Label(corpo, text=etichetta).grid(row=i, column=0, sticky="w", pady=3)
            self.var[chiave] = tk.StringVar(value=dati.get(chiave, ""))
            ttk.Entry(corpo, textvariable=self.var[chiave], width=52).grid(row=i, column=1, columnspan=2,
                                                                           sticky="we", pady=3)
        riga = len(self.CAMPI) + 1
        ttk.Label(corpo, text="Logo (PNG o JPG)").grid(row=riga, column=0, sticky="w", pady=3)
        self.var["logo"] = tk.StringVar(value=dati.get("logo", ""))
        ttk.Entry(corpo, textvariable=self.var["logo"], width=40).grid(row=riga, column=1, sticky="we", pady=3)
        ttk.Button(corpo, text="Scegli…", command=self._scegli_logo).grid(row=riga, column=2, padx=(6, 0))
        ttk.Label(corpo, text="Note in fondo al report").grid(row=riga + 1, column=0, sticky="nw", pady=3)
        self.note = tk.Text(corpo, width=52, height=4, font=_f(10), wrap="word")
        self.note.insert("1.0", dati.get("note", ""))
        self.note.grid(row=riga + 1, column=1, columnspan=2, sticky="we", pady=3)
        from .archivio import cartella_archivio

        for i, (chiave, etichetta, suggerimento) in enumerate([
                ("cartella_apertura", "Cartella da cui aprire i documenti",
                 "es. la cartella delle scansioni; vuota = ultima cartella usata"),
                ("archivio", "Cartella archivio documenti",
                 f"vuota = {cartella_archivio({})}")]):
            r = riga + 2 + i * 2
            ttk.Label(corpo, text=etichetta).grid(row=r, column=0, sticky="w", pady=(6, 0))
            self.var[chiave] = tk.StringVar(value=dati.get(chiave, ""))
            ttk.Entry(corpo, textvariable=self.var[chiave], width=40).grid(row=r, column=1, sticky="we", pady=(6, 0))
            ttk.Button(corpo, text="Scegli…", command=lambda c=chiave: self._scegli_cartella(c)).grid(
                row=r, column=2, padx=(6, 0), pady=(6, 0))
            ttk.Label(corpo, text=suggerimento, foreground="#666").grid(row=r + 1, column=1, columnspan=2, sticky="w")
        riga += 4
        self.var_oscura = tk.BooleanVar(value=dati.get("oscura_dati_esportati", "1") != "0")
        ttk.Checkbutton(corpo, variable=self.var_oscura,
                        text="Oscura i dati personali in report PDF ed esportazioni (consigliato)").grid(
            row=riga + 2, column=0, columnspan=3, sticky="w", pady=(10, 0))
        ttk.Label(corpo, text="Nome → iniziali, codice fiscale, data e luogo di nascita, numeri di documento e IBAN "
                  "oscurati. Sullo schermo i dati restano visibili.", foreground="#666", wraplength=px(560)).grid(
            row=riga + 3, column=0, columnspan=3, sticky="w")
        riga += 2
        ttk.Label(corpo, text=f"Salvate in: {impostazioni.FILE}", foreground="#666").grid(
            row=riga + 2, column=0, columnspan=3, sticky="w", pady=(8, 0))
        pulsanti = ttk.Frame(corpo)
        pulsanti.grid(row=riga + 3, column=0, columnspan=3, sticky="e", pady=(12, 0))
        ttk.Button(pulsanti, text="Annulla", command=self.win.destroy).pack(side="right")
        ttk.Button(pulsanti, text="Salva", style="Accent.TButton", command=self._salva).pack(side="right", padx=6)
        self.win.grab_set()

    def _scegli_logo(self) -> None:
        percorso = filedialog.askopenfilename(parent=self.win, title="Scegli il logo",
                                              filetypes=[("Immagini", "*.png *.jpg *.jpeg"), ("Tutti i file", "*.*")])
        if percorso:
            self.var["logo"].set(percorso)

    def _scegli_cartella(self, chiave: str) -> None:
        cartella = filedialog.askdirectory(parent=self.win, title="Scegli la cartella",
                                           initialdir=self.var[chiave].get() or None)
        if cartella:
            self.var[chiave].set(cartella)

    def _salva(self) -> None:
        dati = {k: v.get().strip() for k, v in self.var.items()}
        for chiave in ("cartella_apertura", "archivio"):
            if dati[chiave] and not Path(dati[chiave]).is_dir():
                try:
                    Path(dati[chiave]).mkdir(parents=True, exist_ok=True)
                except OSError:
                    messagebox.showwarning("Cartella", f"Cartella non valida:\n{dati[chiave]}", parent=self.win)
                    return
        dati["note"] = self.note.get("1.0", "end").strip()
        dati["oscura_dati_esportati"] = "1" if self.var_oscura.get() else "0"
        if dati["logo"] and not Path(dati["logo"]).is_file():
            messagebox.showwarning("Logo", "Il file del logo non esiste.", parent=self.win)
            return
        self.imp.salva(dati)
        self.win.destroy()


from datetime import date  # noqa: E402  (usato dalla finestra archivio)


def leggi_mese(testo: str) -> date | None:
    """'03/2024', '3-2024', '15/03/2024' -> date (primo giorno indicato o 1)."""
    import re

    testo = testo.strip()
    if not testo:
        return None
    m = re.fullmatch(r"(?:(\d{1,2})[/.-])?(\d{1,2})[/.-](\d{4})", testo)
    if not m:
        raise ValueError(f"Data non valida: «{testo}» (usa mm/aaaa oppure gg/mm/aaaa)")
    return date(int(m.group(3)), int(m.group(2)), int(m.group(1) or 1))


class FinestraEstinzione:
    """Conteggio sommario di estinzione anticipata: rata, decorrenza, scadenza, rate residue."""

    CAMPI = [("rata", "Rata mensile (€) *", "es. 250,00"),
             ("decorrenza", "Decorrenza – prima rata", "mm/aaaa"),
             ("scadenza", "Scadenza – ultima rata", "mm/aaaa"),
             ("rate_totali", "Rate totali", "se non indicate: da decorrenza e scadenza"),
             ("rate_residue", "Rate residue", "se non indicate: calcolate alla data del conteggio"),
             ("tan", "TAN %", "dal contratto (es. 6,5)"),
             ("capitale", "Importo finanziato (€)", "se il TAN non è noto"),
             ("costi", "Costi / commissioni iniziali (€)", "per la stima dei costi da restituire"),
             ("data", "Data del conteggio", "gg/mm/aaaa (vuota = oggi)")]

    def __init__(self, parent: tk.Tk):
        self.win = tk.Toplevel(parent)
        self.win.title("Conteggio sommario di estinzione")
        adatta_finestra(self.win, 1060, 640)
        self.win.transient(parent)
        sx = ttk.Frame(self.win, padding=14)
        sx.pack(side="left", fill="y")
        ttk.Label(sx, text="Dati del finanziamento", style="Titolo.TLabel").grid(row=0, column=0, columnspan=2,
                                                                                 sticky="w", pady=(0, 8))
        self.var: dict[str, tk.StringVar] = {}
        for i, (chiave, etichetta, aiuto) in enumerate(self.CAMPI):
            ttk.Label(sx, text=etichetta).grid(row=1 + i * 2, column=0, sticky="w", pady=(4, 0))
            self.var[chiave] = tk.StringVar()
            e = ttk.Entry(sx, textvariable=self.var[chiave], width=18)
            e.grid(row=1 + i * 2, column=1, sticky="w", padx=(8, 0), pady=(4, 0))
            e.bind("<Return>", lambda _e: self.calcola())
            ttk.Label(sx, text=aiuto, foreground="#666", font=_f(8)).grid(row=2 + i * 2, column=0,
                                                                                  columnspan=2, sticky="w")
        self.var_quinto = tk.BooleanVar(value=True)
        r = 1 + len(self.CAMPI) * 2
        ttk.Checkbutton(sx, text="Cessione del quinto / delega", variable=self.var_quinto).grid(
            row=r, column=0, columnspan=2, sticky="w", pady=(8, 0))
        pulsanti = ttk.Frame(sx)
        pulsanti.grid(row=r + 1, column=0, columnspan=2, sticky="w", pady=(12, 0))
        ttk.Button(pulsanti, text="🧮  Calcola", style="Accent.TButton", command=self.calcola).pack(side="left")
        ttk.Button(pulsanti, text="📋  Copia", command=self.copia).pack(side="left", padx=6)
        ttk.Button(pulsanti, text="💾  Salva…", command=self.salva).pack(side="left")
        ttk.Button(pulsanti, text="Chiudi", command=self.win.destroy).pack(side="left", padx=6)

        dx = ttk.Frame(self.win, padding=(0, 14, 14, 14))
        dx.pack(side="left", fill="both", expand=True)
        self.risultato = tk.Text(dx, wrap="word", font=_f(10, famiglia="Consolas"), padx=10, pady=8, background="#f8fafc",
                                 width=72)
        self.risultato.pack(fill="both", expand=True)
        self.risultato.tag_configure("totale", font=_f(11, "bold", "Consolas"), foreground="#1a5a96")
        self.risultato.tag_configure("avviso", foreground="#8a5a00")
        self._mostra("Inserisci la rata e almeno due tra decorrenza, scadenza, rate totali e rate residue,\n"
                     "poi premi «Calcola».\n\nCon il TAN (o l'importo finanziato) il programma calcola il capitale "
                     "residuo,\ngli interessi non dovuti e l'indennizzo di estinzione anticipata.")
        self.testo = ""

    def _mostra(self, testo: str) -> None:
        self.risultato.configure(state="normal")
        self.risultato.delete("1.0", "end")
        for riga in testo.split("\n"):
            tag = "totale" if riga.startswith("TOTALE") else "avviso" if riga.lstrip().startswith("⚠") else ""
            self.risultato.insert("end", riga + "\n", tag)
        self.risultato.configure(state="disabled")

    def _valori(self) -> dict:
        import re
        from decimal import Decimal, InvalidOperation

        def importo(chiave):
            s = self.var[chiave].get().strip().replace("€", "").replace(" ", "").replace("%", "")
            if not s:
                return None
            if "," in s or re.fullmatch(r"\d{1,3}(?:\.\d{3})+", s):  # 1.500 / 1.500,00 = millecinquecento
                s = s.replace(".", "").replace(",", ".")
            try:
                return Decimal(s)
            except InvalidOperation:
                raise ValueError(f"Valore non valido: «{self.var[chiave].get()}»") from None

        def intero(chiave):
            v = importo(chiave)
            return int(v) if v is not None else None

        rata = importo("rata")
        if rata is None:
            raise ValueError("Inserire la rata mensile")
        return dict(rata=rata, decorrenza=leggi_mese(self.var["decorrenza"].get()),
                    scadenza=leggi_mese(self.var["scadenza"].get()), rate_totali=intero("rate_totali"),
                    rate_residue=intero("rate_residue"), tan=importo("tan"), capitale=importo("capitale"),
                    costi=importo("costi"), data_conteggio=leggi_mese(self.var["data"].get()),
                    quinto=self.var_quinto.get())

    def calcola(self) -> None:
        from .estinzione import calcola

        try:
            self.testo = calcola(**self._valori()).testo()
        except ValueError as e:
            messagebox.showwarning("Conteggio estinzione", str(e), parent=self.win)
            return
        self._mostra(self.testo)

    def copia(self) -> None:
        if self.testo:
            self.win.clipboard_clear()
            self.win.clipboard_append(self.testo)

    def salva(self) -> None:
        if not self.testo:
            return
        dest = filedialog.asksaveasfilename(parent=self.win, defaultextension=".txt",
                                            initialfile=f"conteggio_estinzione_{date.today():%Y%m%d}.txt",
                                            filetypes=[("Testo", "*.txt")])
        if dest:
            Path(dest).write_text(self.testo, encoding="utf-8")


class FinestraArchivio:
    """Documenti salvati nell'archivio, divisi per cliente: riapri, ordina per data, elimina."""

    def __init__(self, app: "App"):
        from . import impostazioni
        from .archivio import cartella_archivio

        self.app = app
        self.archivio = cartella_archivio(impostazioni.carica())
        self.win = tk.Toplevel(app.root)
        self.win.title("Archivio documenti")
        adatta_finestra(self.win, 1000, 620)
        self.win.transient(app.root)

        alto = ttk.Frame(self.win, padding=(10, 8))
        alto.pack(fill="x")
        ttk.Label(alto, text="Archivio documenti", style="Titolo.TLabel").pack(side="left")
        ttk.Label(alto, text=f"   {self.archivio}", foreground="#666").pack(side="left")

        barra = ttk.Frame(self.win, padding=(10, 0, 10, 6))
        barra.pack(fill="x")
        ttk.Button(barra, text="📂  Apri nel programma", style="Accent.TButton",
                   command=self.apri_nel_programma).pack(side="left")
        ttk.Button(barra, text="🗑  Elimina…", command=self.elimina).pack(side="left", padx=6)
        ttk.Button(barra, text="📁  Apri cartella", command=self.apri_cartella).pack(side="left")
        ttk.Button(barra, text="↻  Aggiorna", command=self.aggiorna).pack(side="left", padx=6)
        ttk.Label(barra, text="Cerca:").pack(side="left", padx=(16, 4))
        self.var_cerca = tk.StringVar()
        self.var_cerca.trace_add("write", lambda *_: self.aggiorna())
        ttk.Entry(barra, textvariable=self.var_cerca, width=28).pack(side="left")
        ttk.Button(barra, text="Chiudi", command=self.win.destroy).pack(side="right")

        corpo = ttk.Frame(self.win, padding=(10, 0, 10, 6))
        corpo.pack(fill="both", expand=True)
        self.albero = ttk.Treeview(corpo, columns=("periodo", "data", "dimensione"), show="tree headings",
                                   selectmode="extended")
        self.titoli = {"#0": "Cliente / documento", "periodo": "Periodo", "data": "Data del file",
                       "dimensione": "Dimensione"}
        for col, titolo in self.titoli.items():
            self.albero.heading(col, text=titolo, command=lambda c=col: self.ordina(c, cambia=True))
        self.albero.column("#0", width=px(500))
        self.albero.column("periodo", width=px(130))
        self.albero.column("data", width=px(150), anchor="center")
        self.albero.column("dimensione", width=px(100), anchor="e")
        self.albero.tag_configure("cliente", font=_f(10, "bold"))
        self.albero.tag_configure("categoria", font=_f(9, "bold"), foreground="#1a5a96")
        App._con_scrollbar(corpo, self.albero)
        self.albero.bind("<Double-1>", lambda _e: self.apri_nel_programma())
        self.albero.bind("<Delete>", lambda _e: self.elimina())
        self.stato = tk.StringVar()
        ttk.Label(self.win, textvariable=self.stato, padding=(10, 0, 10, 8)).pack(fill="x")
        self.ordinamento = ("periodo", True)
        self.voci: dict[str, object] = {}
        self.aggiorna()

    def aggiorna(self) -> None:
        from .archivio import elenco

        aperti = {iid for iid in self.albero.get_children() if self.albero.item(iid, "open")}
        self.albero.delete(*self.albero.get_children())
        self.voci.clear()
        filtro = self.var_cerca.get().strip().lower()
        voci = [v for v in elenco(self.archivio)
                if not filtro or filtro in v.percorso.name.lower() or filtro in v.cliente.lower()]
        clienti: dict[str, list] = {}
        for v in voci:
            clienti.setdefault(v.cliente or "(senza cartella cliente)", []).append(v)

        def riepilogo(file):
            periodi = [f.periodo for f in file if f.periodo]
            return (max(f.archiviato_il for f in file), sum(f.dimensione for f in file),
                    max(periodi) if periodi else date.min)

        for cliente, file in clienti.items():
            ultimo, dimensione, recente = riepilogo(file)
            iid_cliente = f"cliente::{cliente}"
            self.albero.insert("", "end", iid=iid_cliente, text=f"{cliente}   ({len(file)})",
                               values=("", f"{ultimo:%d/%m/%Y %H:%M}", ""), tags=("cliente",),
                               open=bool(filtro) or iid_cliente in aperti or len(clienti) <= 3)
            self.voci[iid_cliente] = (self.archivio / cliente if cliente != "(senza cartella cliente)" else None,
                                      ultimo, dimensione, cliente.lower(), recente)
            # sottocartelle per prodotto (Buste paga, CU, ...)
            per_categoria: dict[str, list] = {}
            for f in file:
                per_categoria.setdefault(f.categoria, []).append(f)
            for cat, file_cat in per_categoria.items():
                genitore = iid_cliente
                if cat:
                    genitore = f"categoria::{cliente}/{cat}"
                    u, dim, rec = riepilogo(file_cat)
                    self.albero.insert(iid_cliente, "end", iid=genitore, text=f"📁 {cat}   ({len(file_cat)})",
                                       values=("", f"{u:%d/%m/%Y %H:%M}", ""), tags=("categoria",), open=True)
                    self.voci[genitore] = (self.archivio / cliente / cat, u, dim, cat.lower(), rec)
                for f in file_cat:
                    iid = str(f.percorso)
                    kb = max(1, round(f.dimensione / 1024))
                    self.albero.insert(genitore, "end", iid=iid, text=f.percorso.name,
                                       values=(f.testo_periodo, f"{f.archiviato_il:%d/%m/%Y %H:%M}",
                                               f"{kb:,} KB".replace(",", ".")))
                    self.voci[iid] = (f.percorso, f.archiviato_il, f.dimensione, f.percorso.name.lower(),
                                      f.periodo or date.min)
        self.ordina(*self.ordinamento)
        totale = len(voci)
        self.stato.set(f"{totale} documenti di {len(clienti)} clienti" + (" (filtrati)" if filtro else "")
                       + "  ·  doppio clic per aprire  ·  Canc per eliminare (nel Cestino)")

    def ordina(self, colonna: str, decrescente: bool | None = None, cambia: bool = False) -> None:
        if cambia:
            col_att, dec_att = self.ordinamento
            decrescente = (not dec_att) if col_att == colonna else colonna != "#0"
        elif decrescente is None:
            decrescente = self.ordinamento[1]
        self.ordinamento = (colonna, decrescente)
        indice = {"#0": 3, "data": 1, "dimensione": 2, "periodo": 4}[colonna]

        def ordina_livello(genitore):
            figli = self.albero.get_children(genitore)
            if colonna == "#0" or genitore == "" or all(not i.startswith("categoria::") for i in figli):
                figli = sorted(figli, key=lambda i: self.voci[i][indice], reverse=decrescente)
            else:  # le sottocartelle dei prodotti restano in ordine alfabetico
                figli = sorted(figli, key=lambda i: self.voci[i][3])
            for n, iid in enumerate(figli):
                self.albero.move(iid, genitore, n)
                ordina_livello(iid)

        ordina_livello("")
        for col, titolo in self.titoli.items():
            self.albero.heading(col, text=titolo + ((" ▼" if decrescente else " ▲") if col == colonna else ""))

    def _foglie(self, iid: str) -> list[Path]:
        if not iid.startswith(("cliente::", "categoria::")):
            return [Path(iid)]
        return [f for figlio in self.albero.get_children(iid) for f in self._foglie(figlio)]

    def _selezionati(self) -> list[Path]:
        return list(dict.fromkeys(f for iid in self.albero.selection() for f in self._foglie(iid)))

    def apri_nel_programma(self) -> None:
        file = self._selezionati()
        if file:
            self.app.aggiungi([str(f) for f in file])
            self.app.root.lift()

    def apri_cartella(self) -> None:
        sel = self.albero.selection()
        cartella = self.archivio
        if sel:
            p = self.voci[sel[0]][0]
            cartella = p if p and p.is_dir() else (p.parent if p else self.archivio)
        cartella.mkdir(parents=True, exist_ok=True)
        apri_con_programma_predefinito(str(cartella))

    def elimina(self) -> None:
        from .archivio import elimina

        sel = self.albero.selection()
        if not sel:
            messagebox.showinfo("Elimina", "Seleziona uno o più documenti (o un cliente).", parent=self.win)
            return
        bersagli = []
        for iid in sel:
            p = self.voci[iid][0]
            if iid.startswith(("cliente::", "categoria::")):
                if p is not None:
                    bersagli.append(p)
                else:
                    bersagli += self._foglie(iid)
            elif not any(str(Path(iid)).startswith(str(b)) for b in bersagli if b.is_dir()):
                bersagli.append(Path(iid))
        n_file = len(self._selezionati())
        cartelle = [b.relative_to(self.archivio).as_posix() for b in bersagli if b.is_dir()]
        testo = f"Eliminare {n_file} documenti dall'archivio?"
        if cartelle:
            testo += "\n\nCartelle intere: " + ", ".join(cartelle)
        testo += "\n\nI file vanno nel Cestino di Windows (recuperabili). Gli originali non vengono toccati."
        if not messagebox.askyesno("Elimina dall'archivio", testo, icon="warning", parent=self.win):
            return
        dove, errori = "", []
        for b in bersagli:
            try:
                dove = elimina(b, self.archivio)
            except (OSError, ValueError) as e:
                errori.append(f"{b.name}: {e}")
        # i documenti eliminati non sono più nell'archivio: lo si indica nell'elenco principale
        for ris in self.app.risultati.values():
            if ris.archiviato and not ris.archiviato.exists():
                ris.archiviato = None
        self.aggiorna()
        if errori:
            messagebox.showerror("Elimina", "\n".join(errori), parent=self.win)
        else:
            self.stato.set(f"Eliminati {n_file} documenti ({dove}).")


class FinestraConfronto:
    """Finestra con l'esito del confronto tra i documenti caricati."""

    COLONNE = [("periodo", "Periodo", 150, "w"), ("lordo", "Lordo", 110, "e"), ("netto", "Netto", 110, "e"),
               ("netto_su_lordo", "Netto/lordo", 95, "e"), ("imponibile_fiscale", "Imponibile fiscale", 130, "e"),
               ("progressivo_imponibile_fiscale", "Progressivo imp.", 130, "e"), ("esito", "Esito busta", 110, "center"),
               ("file", "File", 220, "w")]

    def __init__(self, parent: tk.Tk, esito, documenti=None):
        self.esito = esito
        self.documenti = documenti or []
        r = esito.report
        self.win = tk.Toplevel(parent)
        self.win.title("Confronto tra documenti")
        adatta_finestra(self.win, 1100, 680)
        self.win.transient(parent)

        intest = ttk.Frame(self.win, padding=(10, 8))
        intest.pack(fill="x")
        ttk.Label(intest, text=f"Confronto tra {r.dati['documenti_confrontati']} documenti",
                  style="Titolo.TLabel").pack(side="left")
        fg, bg = COLORI[r.esito_globale]
        tk.Label(intest, text=f"{SIMBOLI[r.esito_globale]} {r.esito_globale.value}", fg=fg, bg=bg,
                 font=_f(12, "bold"), padx=12, pady=4).pack(side="right")
        ttk.Button(intest, text="💾  Esporta…", command=self.esporta).pack(side="right", padx=8)

        divisore = ttk.PanedWindow(self.win, orient="vertical")
        divisore.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        f1 = ttk.Frame(divisore)
        self.albero = ttk.Treeview(f1, columns=("esito", "controllo", "dettaglio"), show="headings")
        for col, testo, w in [("esito", "", 40), ("controllo", "Controllo", 200), ("dettaglio", "Dettaglio", 760)]:
            self.albero.heading(col, text=testo)
            self.albero.column(col, width=px(w), anchor="center" if col == "esito" else "w",
                               stretch=col == "dettaglio")
        for e, (fg, bg) in COLORI.items():
            self.albero.tag_configure(e.value, foreground=fg, background=bg)
        self.albero.tag_configure("gruppo", foreground="#ffffff", background="#57606a",
                                  font=_f(9, "bold"))
        for gruppo, controlli in r.gruppi().items():
            self.albero.insert("", "end", values=("", gruppo.upper(), ""), tags=("gruppo",))
            for c in controlli:
                self.albero.insert("", "end", values=(SIMBOLI[c.esito], c.nome, c.dettaglio),
                                   tags=(c.esito.value,))
        self.albero.bind("<Double-1>", self._dettaglio)
        App._con_scrollbar(f1, self.albero)
        divisore.add(f1, weight=3)

        if esito.tabelle:
            f2 = ttk.Frame(divisore)
            ttk.Label(f2, text="Buste paga mese per mese", style="Titolo.TLabel").grid(
                row=0, column=0, sticky="w", pady=(6, 4))
            interno = ttk.Frame(f2)
            interno.grid(row=1, column=0, sticky="nsew")
            f2.rowconfigure(1, weight=1)
            f2.columnconfigure(0, weight=1)
            tab = ttk.Treeview(interno, columns=[c[0] for c in self.COLONNE], show="headings", height=6)
            for chiave, titolo, w, anchor in self.COLONNE:
                tab.heading(chiave, text=titolo)
                tab.column(chiave, width=px(w), anchor=anchor)
            for e, (fg, bg) in COLORI.items():
                tab.tag_configure(e.value, foreground=fg, background=bg)
            tab.tag_configure("gruppo", foreground="#ffffff", background="#57606a")
            for cf, righe in esito.tabelle.items():
                if len(esito.tabelle) > 1:
                    tab.insert("", "end", values=(f"CLIENTE {cf}",), tags=("gruppo",))
                for riga in righe:
                    valori = [formatta_valore(k + ("_%" if k == "netto_su_lordo" else ""), riga.get(k))
                              for k, *_ in self.COLONNE]
                    tab.insert("", "end", values=valori, tags=(riga["esito"],))
            App._con_scrollbar(interno, tab)
            divisore.add(f2, weight=2)

    def _dettaglio(self, _e) -> None:
        sel = self.albero.selection()
        if sel:
            _, nome, dettaglio = self.albero.item(sel[0], "values")
            if dettaglio:
                messagebox.showinfo(nome, dettaglio, parent=self.win)

    def esporta(self) -> None:
        from .confronto import confronto_testuale

        dest = filedialog.asksaveasfilename(parent=self.win, title="Salva confronto",
                                            defaultextension=".txt", initialfile="confronto_documenti.txt",
                                            filetypes=[("Testo", "*.txt"), ("JSON", "*.json")])
        if not dest:
            return
        esito = self.esito
        if _oscura_esportazioni():
            from .anonimizza import oscura_documenti

            _, esito = oscura_documenti(self.documenti, esito)
        if dest.lower().endswith(".json"):
            contenuto = json.dumps(esito.report.to_dict(), ensure_ascii=False, indent=2)
        else:
            contenuto = confronto_testuale(esito)
        Path(dest).write_text(contenuto, encoding="utf-8")


def main(file_iniziali: list[str] | None = None) -> None:
    import sys

    _dpi_windows()
    root, dnd = _crea_root()
    app = App(root, dnd)
    file_iniziali = file_iniziali if file_iniziali is not None else sys.argv[1:]
    if file_iniziali:
        app.aggiungi(file_iniziali)
    root.mainloop()


if __name__ == "__main__":
    main()
