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
from .cli import analizza_testo
from .estrazione import ErroreEstrazione, estrai_testo
from .report import SIMBOLI, Esito, Report, etichetta_campo, formatta_valore, report_testuale

TIPI = {
    "Automatico": "auto",
    "Busta paga": "busta",
    "Modello Redditi PF": "redditi",
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
              ("data_assunzione", "Assunzione"), ("totale_competenze", "Lordo")],
    "Modello": [("regime_fiscale", "Regime fiscale"), ("reddito_mensile_lordo", "Reddito mensile"),
                ("reddito_mensile_netto", "Mensile netto imposte"), ("periodo_imposta", "Anno d'imposta"),
                ("codice_fiscale_contribuente", "Codice fiscale"), ("reddito_annuo", "Reddito annuo")],
    "Carta": [("cognome", "Cognome"), ("nome", "Nome"), ("codice_fiscale", "Codice fiscale"),
              ("data_scadenza", "Scadenza"), ("numero_documento", "N. documento")],
}
for _t in ("Patente", "Passaporto", "Tessera", "Documento"):
    RIEPILOGO[_t] = RIEPILOGO["Carta"]

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
        root.geometry("1180x720")
        root.minsize(900, 560)
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

    def _costruisci(self) -> None:
        # Barra superiore
        barra = ttk.Frame(self.root, padding=(10, 8))
        barra.pack(fill="x")
        ttk.Button(barra, text="📂  Apri documenti…", style="Accent.TButton",
                   command=self.apri_file).pack(side="left")
        ttk.Label(barra, text="   Tipo:").pack(side="left")
        self.var_tipo = tk.StringVar(value="Automatico")
        ttk.Combobox(barra, textvariable=self.var_tipo, values=list(TIPI), state="readonly",
                     width=22).pack(side="left", padx=4)
        self.var_ocr = tk.BooleanVar(value=True)
        ttk.Checkbutton(barra, text="Usa OCR per scansioni/foto", variable=self.var_ocr).pack(
            side="left", padx=10)
        ttk.Button(barra, text="🗑  Svuota", command=self.svuota).pack(side="right")
        ttk.Button(barra, text="💾  Esporta report…", command=self.esporta).pack(side="right", padx=6)
        ttk.Button(barra, text="↻  Rianalizza", command=self.rianalizza).pack(side="right")

        corpo = ttk.PanedWindow(self.root, orient="horizontal")
        corpo.pack(fill="both", expand=True, padx=10, pady=(0, 6))

        # Colonna sinistra: elenco documenti
        sx = ttk.Frame(corpo)
        ttk.Label(sx, text="Documenti", style="Titolo.TLabel").pack(anchor="w", pady=(0, 4))
        self.lista = ttk.Treeview(sx, columns=("esito", "tipo"), show="tree headings",
                                  selectmode="browse")
        self.lista.heading("#0", text="File")
        self.lista.heading("esito", text="Esito")
        self.lista.heading("tipo", text="Tipo")
        self.lista.column("#0", width=190)
        self.lista.column("esito", width=100, anchor="center")
        self.lista.column("tipo", width=120)
        for esito, (fg, bg) in COLORI.items():
            self.lista.tag_configure(esito.value, foreground=fg, background=bg)
        self.lista.tag_configure("attesa", foreground="#666")
        self.lista.pack(fill="both", expand=True)
        self.lista.bind("<<TreeviewSelect>>", lambda _e: self.mostra_selezionato())
        suggerimento = ("Trascina qui i file oppure usa «Apri documenti…»" if self.dnd
                        else "Usa «Apri documenti…» per aggiungere file")
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
                self.lista.item(chiave, values=("in corso…", ""), tags=("attesa",))
            else:
                self.lista.insert("", "end", iid=chiave, text=p.name, values=("in corso…", ""),
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
                ris.testo = estrai_testo(percorso, usa_ocr=ocr)
                ris.report = analizza_testo(ris.testo, tipo)
            except (ErroreEstrazione, ValueError) as e:
                ris.errore = str(e)
            except Exception as e:  # errore imprevisto: non bloccare l'interfaccia
                ris.errore = f"Errore imprevisto: {e!r}"
            self.coda.put((chiave, ris))

        threading.Thread(target=lavoro, daemon=True).start()

    def _controlla_coda(self) -> None:
        try:
            while True:
                chiave, ris = self.coda.get_nowait()
                self.in_corso -= 1
                self.risultati[chiave] = ris
                if self.lista.exists(chiave):
                    esito = ris.esito
                    testo_esito = f"{SIMBOLI[esito]} {esito.value}" if ris.report else "✘ ILLEGGIBILE"
                    tipo = ris.report.tipo_documento if ris.report else "—"
                    self.lista.item(chiave, values=(testo_esito, tipo), tags=(esito.value,))
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
        for c in r.controlli:
            self.tab_controlli.insert("", "end", values=(SIMBOLI[c.esito], c.nome, c.dettaglio),
                                      tags=(c.esito.value,))
        for k, v in r.dati.items():
            self.tab_dati.insert("", "end", values=(etichetta_campo(k), formatta_valore(k, v)),
                                 tags=("vuoto",) if v is None else ())

    def _aggiorna_riepilogo(self, r: Report | None) -> None:
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
            messagebox.showinfo(nome, dettaglio, parent=self.root)

    def rianalizza(self) -> None:
        """Rianalizza tutti i documenti (es. dopo aver cambiato il tipo)."""
        for chiave in self.lista.get_children():
            self.lista.item(chiave, values=("in corso…", ""), tags=("attesa",))
            self.risultati.pop(chiave, None)
            self._avvia_analisi(Path(chiave), chiave)

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

    def esporta(self) -> None:
        validi = {k: r for k, r in self.risultati.items() if r.report}
        if not validi:
            messagebox.showinfo("Esporta", "Nessun report da esportare.", parent=self.root)
            return
        dest = filedialog.asksaveasfilename(
            title="Salva report", defaultextension=".txt", initialfile="report_verifica.txt",
            filetypes=[("Testo", "*.txt"), ("JSON", "*.json")],
        )
        if not dest:
            return
        if dest.lower().endswith(".json"):
            dati = [{"file": r.percorso.name, **r.report.to_dict()} for r in validi.values()]
            contenuto = json.dumps(dati, ensure_ascii=False, indent=2)
        else:
            contenuto = "\n".join(report_testuale(r.percorso.name, r.report) for r in validi.values())
        Path(dest).write_text(contenuto, encoding="utf-8")
        self.var_stato.set(f"Report salvato in {dest}")


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
