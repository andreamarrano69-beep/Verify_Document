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

TIPI = {
    "Automatico": "auto",
    "Busta paga": "busta",
    "Modello Redditi PF": "redditi",
    "Certificazione Unica (CU)": "cu",
    "Pensione (cedolino / ObisM)": "pensione",
    "Documento d'identità": "anagrafica",
}

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
        root.geometry("1180x720")
        root.minsize(900, 560)
        self._massimizza()
        root.protocol("WM_DELETE_WINDOW", self.esci)  # anche la X della finestra chiede conferma
        root.bind("<Control-q>", lambda _e: self.esci())
        root.bind("<F11>", lambda _e: self.schermo_intero())
        root.bind("<Escape>", lambda _e: self.schermo_intero(False))
        self._stile()
        self._costruisci()
        self.root.after(150, self._controlla_coda)

    # ------------------------------------------------------------------ layout
    def _stile(self) -> None:
        st = ttk.Style(self.root)
        if "clam" in st.theme_names():
            st.theme_use("clam")
        st.configure("Treeview", rowheight=26, font=("Segoe UI", 10))
        st.configure("Treeview.Heading", font=("Segoe UI", 10, "bold"))
        st.configure("Titolo.TLabel", font=("Segoe UI", 14, "bold"))
        st.configure("Esito.TLabel", font=("Segoe UI", 12, "bold"), padding=(10, 4))
        st.configure("Accent.TButton", font=("Segoe UI", 10, "bold"))
        st.configure("Esci.TButton", font=("Segoe UI", 10, "bold"), foreground="#b3261e")

    def _costruisci(self) -> None:
        # Barra superiore, riga 1: azioni principali
        barra = ttk.Frame(self.root, padding=(10, 8, 10, 2))
        barra.pack(fill="x")
        ttk.Button(barra, text="📂  Apri documenti…", style="Accent.TButton",
                   command=self.apri_file).pack(side="left")
        ttk.Button(barra, text="⇄  Confronta documenti", style="Accent.TButton",
                   command=self.confronta).pack(side="left", padx=6)
        ttk.Button(barra, text="📄  Report PDF", style="Accent.TButton",
                   command=self.esporta_pdf).pack(side="left")
        menu_esporta = ttk.Menubutton(barra, text="💾  Esporta ▾")
        menu = tk.Menu(menu_esporta, tearoff=0)
        menu.add_command(label="Report PDF…", command=self.esporta_pdf)
        menu.add_command(label="Testo (.txt)…", command=lambda: self.esporta("txt"))
        menu.add_command(label="Dati (.json)…", command=lambda: self.esporta("json"))
        menu_esporta["menu"] = menu
        menu_esporta.pack(side="left", padx=6)
        ttk.Button(barra, text="⏻  Esci", style="Esci.TButton", command=self.esci).pack(side="right")
        ttk.Separator(barra, orient="vertical").pack(side="right", fill="y", padx=8)
        ttk.Button(barra, text="⚙  Impostazioni", command=self.apri_impostazioni).pack(side="right")

        # riga 2: opzioni di analisi
        opzioni = ttk.Frame(self.root, padding=(10, 2, 10, 6))
        opzioni.pack(fill="x")
        ttk.Label(opzioni, text="Tipo di documento:").pack(side="left")
        self.var_tipo = tk.StringVar(value="Automatico")
        ttk.Combobox(opzioni, textvariable=self.var_tipo, values=list(TIPI), state="readonly",
                     width=26).pack(side="left", padx=4)
        self.var_ocr = tk.BooleanVar(value=True)
        ttk.Checkbutton(opzioni, text="Usa OCR per scansioni/foto", variable=self.var_ocr).pack(
            side="left", padx=10)
        ttk.Button(opzioni, text="↻  Rianalizza", command=self.rianalizza).pack(side="left", padx=(10, 0))
        ttk.Button(opzioni, text="🗑  Svuota", command=self.svuota).pack(side="left", padx=6)

        corpo = ttk.PanedWindow(self.root, orient="horizontal")
        corpo.pack(fill="both", expand=True, padx=10, pady=(0, 6))

        # Colonna sinistra: elenco documenti
        sx = ttk.Frame(corpo)
        ttk.Label(sx, text="Documenti", style="Titolo.TLabel").pack(anchor="w", pady=(0, 4))
        self.lista = ttk.Treeview(sx, columns=("esito", "tipo", "mensile"), show="tree headings",
                                  selectmode="browse")
        self.lista.heading("#0", text="File")
        self.lista.heading("esito", text="Esito")
        self.lista.heading("tipo", text="Tipo")
        self.lista.heading("mensile", text="Netto mensile")
        self.lista.column("#0", width=190)
        self.lista.column("esito", width=100, anchor="center")
        self.lista.column("tipo", width=120)
        self.lista.column("mensile", width=105, anchor="e")
        for esito, (fg, bg) in COLORI.items():
            self.lista.tag_configure(esito.value, foreground=fg, background=bg)
        self.lista.tag_configure("attesa", foreground="#666")
        self.lista.pack(fill="both", expand=True)
        self.lista.bind("<<TreeviewSelect>>", lambda _e: self.mostra_selezionato())
        suggerimento = ("Trascina qui i file oppure usa «Apri documenti…»" if self.dnd
                        else "Usa «Apri documenti…» per aggiungere file")
        suggerimento += "  ·  F11 schermo intero  ·  Ctrl+Q esci"
        ttk.Label(sx, text=suggerimento, foreground="#666").pack(anchor="w", pady=4)
        corpo.add(sx, weight=1)

        # Colonna destra: dettaglio
        dx = ttk.Frame(corpo)
        intest = ttk.Frame(dx)
        intest.pack(fill="x")
        self.lbl_titolo = ttk.Label(intest, text="Nessun documento selezionato", style="Titolo.TLabel")
        self.lbl_titolo.pack(side="left")
        self.lbl_esito = tk.Label(intest, text="", font=("Segoe UI", 12, "bold"), padx=12, pady=4)
        self.lbl_esito.pack(side="right")

        # Fascia di sintesi: regime / tipo di reddito e importo mensile, in grande
        self.banner = tk.Frame(dx, bg=COLORE_SINTESI)
        self.riepilogo = tk.Frame(dx, bg="#f4f6f8", highlightthickness=1,
                                  highlightbackground="#d0d7de")
        self.riepilogo.pack(fill="x", pady=(6, 0))

        self.schede = ttk.Notebook(dx)
        self.schede.pack(fill="both", expand=True, pady=(6, 0))

        # Scheda controlli
        f1 = ttk.Frame(self.schede)
        self.tab_controlli = ttk.Treeview(f1, columns=("esito", "controllo", "dettaglio"),
                                          show="headings")
        for col, testo, w in [("esito", "", 40), ("controllo", "Controllo", 210),
                              ("dettaglio", "Dettaglio", 560)]:
            self.tab_controlli.heading(col, text=testo)
            self.tab_controlli.column(col, width=w, anchor="center" if col == "esito" else "w",
                                      stretch=col == "dettaglio")
        for esito, (fg, bg) in COLORI.items():
            self.tab_controlli.tag_configure(esito.value, foreground=fg, background=bg)
        self.tab_controlli.tag_configure("gruppo", foreground="#ffffff", background="#57606a",
                                         font=("Segoe UI", 9, "bold"))
        self._con_scrollbar(f1, self.tab_controlli)
        self.tab_controlli.bind("<Double-1>", self._mostra_dettaglio_controllo)
        self.schede.add(f1, text="  Controlli  ")

        # Scheda dati estratti
        f2 = ttk.Frame(self.schede)
        self.tab_dati = ttk.Treeview(f2, columns=("campo", "valore"), show="headings")
        self.tab_dati.heading("campo", text="Campo")
        self.tab_dati.heading("valore", text="Valore")
        self.tab_dati.column("campo", width=260, stretch=False)
        self.tab_dati.column("valore", width=500)
        self.tab_dati.tag_configure("vuoto", foreground="#999")
        self._con_scrollbar(f2, self.tab_dati)
        self.schede.add(f2, text="  Dati estratti  ")

        # Scheda testo letto
        f3 = ttk.Frame(self.schede)
        self.txt = tk.Text(f3, wrap="none", font=("Consolas", 10))
        self._con_scrollbar(f3, self.txt, orizzontale=True)
        self.schede.add(f3, text="  Testo letto  ")
        corpo.add(dx, weight=3)

        # Barra di stato
        self.var_stato = tk.StringVar(value="Pronto. Tutti i documenti vengono elaborati in locale.")
        self.avviso_ocr_mostrato = False
        self.root.after(300, self._stato_ocr)
        stato = ttk.Frame(self.root, padding=(10, 2))
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
        percorsi = filedialog.askopenfilenames(title="Scegli i documenti da verificare",
                                               filetypes=TIPI_FILE)
        if percorsi:
            self.aggiungi(percorsi)

    def aggiungi(self, percorsi) -> None:
        for p in percorsi:
            p = Path(p)
            if p.is_dir():
                continue
            chiave = str(p.resolve())
            if self.lista.exists(chiave):
                self.lista.item(chiave, values=("in corso…", "", ""), tags=("attesa",))
            else:
                self.lista.insert("", "end", iid=chiave, text=p.name, values=("in corso…", "", ""),
                                  tags=("attesa",))
            self._avvia_analisi(p, chiave)
        if not self.lista.selection() and self.lista.get_children():
            self.lista.selection_set(self.lista.get_children()[-1])

    def _avvia_analisi(self, percorso: Path, chiave: str) -> None:
        tipo = TIPI[self.var_tipo.get()]
        ocr = self.var_ocr.get()
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
            self.coda.put((chiave, ris))

        threading.Thread(target=lavoro, daemon=True).start()

    def _stato_ocr(self) -> None:
        from .estrazione import trova_tesseract

        percorso, lingua = trova_tesseract()
        if percorso:
            self.var_stato.set(f"Pronto. OCR attivo (Tesseract, lingua {lingua or 'predefinita'}) per scansioni "
                               "e foto. Tutti i documenti vengono elaborati in locale.")
        else:
            self.var_stato.set("Pronto. OCR non disponibile: scansioni e foto non si possono leggere "
                               "(installa Tesseract). Tutti i documenti vengono elaborati in locale.")

    def _controlla_coda(self) -> None:
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
                    self.lista.item(chiave, values=(testo_esito, tipo, mensile), tags=(esito.value,))
                if chiave in self.lista.selection():
                    self.mostra_selezionato()
        except queue.Empty:
            pass
        if self.in_corso <= 0:
            self.in_corso = 0
            self.progress.stop()
            if self.risultati:
                n = len(self.risultati)
                errori = sum(1 for r in self.risultati.values() if r.esito == Esito.ERRORE)
                self.var_stato.set(f"{n} documenti analizzati — {errori} con errori.")
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
        for w in self.banner.winfo_children():
            w.destroy()
        s = sintesi(r) if r else None
        if s is None:
            self.banner.pack_forget()
            return
        self.banner.pack(fill="x", pady=(6, 0), before=self.riepilogo)
        blocchi = [(s.etichetta, s.categoria or "non determinato", 15),
                   ("Importo mensile lordo", formatta_euro(s.mensile_lordo), 20),
                   ("Importo mensile netto", formatta_euro(s.mensile_netto), 20)]
        for i, (titolo, valore, dim) in enumerate(blocchi):
            cella = tk.Frame(self.banner, bg=COLORE_SINTESI, padx=16, pady=8)
            cella.grid(row=0, column=i, sticky="nw")
            tk.Label(cella, text=titolo.upper(), bg=COLORE_SINTESI, fg="#c9dcf2",
                     font=("Segoe UI", 9, "bold")).pack(anchor="w")
            tk.Label(cella, text=valore, bg=COLORE_SINTESI, fg="#ffffff", font=("Segoe UI", dim, "bold"),
                     wraplength=380, justify="left").pack(anchor="w")
        self.banner.columnconfigure(0, weight=1)
        tk.Label(self.banner, text=s.nota, bg=COLORE_SINTESI, fg="#c9dcf2",
                 font=("Segoe UI", 9)).grid(row=1, column=0, columnspan=3, sticky="w", padx=16, pady=(0, 6))

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
            cella = tk.Frame(self.riepilogo, bg="#f4f6f8", padx=12, pady=6)
            cella.grid(row=i // 4, column=i % 4, sticky="w")
            tk.Label(cella, text=etichetta.upper(), bg="#f4f6f8", fg="#57606a",
                     font=("Segoe UI", 8, "bold")).pack(anchor="w")
            tk.Label(cella, text=valore, bg="#f4f6f8", fg="#1f2328",
                     font=("Segoe UI", 12, "bold")).pack(anchor="w")

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
            self.lista.item(chiave, values=("in corso…", "", ""), tags=("attesa",))
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

    def svuota(self) -> None:
        if self.in_corso:
            messagebox.showwarning("Attendere", "Analisi ancora in corso.", parent=self.root)
            return
        self.lista.delete(*self.lista.get_children())
        self.risultati.clear()
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
        FinestraConfronto(self.root, esito)
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
        if formato == "json":
            dati = [{"file": r.percorso.name, **r.report.to_dict()} for r in validi]
            contenuto = json.dumps(dati, ensure_ascii=False, indent=2)
        else:
            contenuto = "\n".join(report_testuale(r.percorso.name, r.report) for r in validi)
        Path(dest).write_text(contenuto, encoding="utf-8")
        self.var_stato.set(f"Report salvato in {dest}")

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
            initialfile=f"report_{cf}_{date.today():%Y%m%d}.pdf")
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
        self.note = tk.Text(corpo, width=52, height=4, font=("Segoe UI", 10), wrap="word")
        self.note.insert("1.0", dati.get("note", ""))
        self.note.grid(row=riga + 1, column=1, columnspan=2, sticky="we", pady=3)
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

    def _salva(self) -> None:
        dati = {k: v.get().strip() for k, v in self.var.items()}
        dati["note"] = self.note.get("1.0", "end").strip()
        if dati["logo"] and not Path(dati["logo"]).is_file():
            messagebox.showwarning("Logo", "Il file del logo non esiste.", parent=self.win)
            return
        self.imp.salva(dati)
        self.win.destroy()


class FinestraConfronto:
    """Finestra con l'esito del confronto tra i documenti caricati."""

    COLONNE = [("periodo", "Periodo", 150, "w"), ("lordo", "Lordo", 110, "e"), ("netto", "Netto", 110, "e"),
               ("netto_su_lordo", "Netto/lordo", 95, "e"), ("imponibile_fiscale", "Imponibile fiscale", 130, "e"),
               ("progressivo_imponibile_fiscale", "Progressivo imp.", 130, "e"), ("esito", "Esito busta", 110, "center"),
               ("file", "File", 220, "w")]

    def __init__(self, parent: tk.Tk, esito):
        self.esito = esito
        r = esito.report
        self.win = tk.Toplevel(parent)
        self.win.title("Confronto tra documenti")
        self.win.geometry("1100x680")
        self.win.transient(parent)

        intest = ttk.Frame(self.win, padding=(10, 8))
        intest.pack(fill="x")
        ttk.Label(intest, text=f"Confronto tra {r.dati['documenti_confrontati']} documenti",
                  style="Titolo.TLabel").pack(side="left")
        fg, bg = COLORI[r.esito_globale]
        tk.Label(intest, text=f"{SIMBOLI[r.esito_globale]} {r.esito_globale.value}", fg=fg, bg=bg,
                 font=("Segoe UI", 12, "bold"), padx=12, pady=4).pack(side="right")
        ttk.Button(intest, text="💾  Esporta…", command=self.esporta).pack(side="right", padx=8)

        divisore = ttk.PanedWindow(self.win, orient="vertical")
        divisore.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        f1 = ttk.Frame(divisore)
        self.albero = ttk.Treeview(f1, columns=("esito", "controllo", "dettaglio"), show="headings")
        for col, testo, w in [("esito", "", 40), ("controllo", "Controllo", 200), ("dettaglio", "Dettaglio", 760)]:
            self.albero.heading(col, text=testo)
            self.albero.column(col, width=w, anchor="center" if col == "esito" else "w",
                               stretch=col == "dettaglio")
        for e, (fg, bg) in COLORI.items():
            self.albero.tag_configure(e.value, foreground=fg, background=bg)
        self.albero.tag_configure("gruppo", foreground="#ffffff", background="#57606a",
                                  font=("Segoe UI", 9, "bold"))
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
                tab.column(chiave, width=w, anchor=anchor)
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
        if dest.lower().endswith(".json"):
            contenuto = json.dumps(self.esito.report.to_dict(), ensure_ascii=False, indent=2)
        else:
            contenuto = confronto_testuale(self.esito)
        Path(dest).write_text(contenuto, encoding="utf-8")


def main(file_iniziali: list[str] | None = None) -> None:
    import sys

    root, dnd = _crea_root()
    app = App(root, dnd)
    file_iniziali = file_iniziali if file_iniziali is not None else sys.argv[1:]
    if file_iniziali:
        app.aggiungi(file_iniziali)
    root.mainloop()


if __name__ == "__main__":
    main()
