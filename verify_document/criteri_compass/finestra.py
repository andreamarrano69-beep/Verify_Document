"""Finestra «Verifica criteri Compass».

Si apre dal pulsante «🏦 Criteri Compass» della finestra principale, già compilata con i dati letti dai
documenti del cliente (vedi da_documenti.py). L'operatore completa le valutazioni dell'azienda sui DB delle
assicurazioni e la richiesta (rata, durata), poi preme Verifica.
"""

from __future__ import annotations

import tkinter as tk
from datetime import date
from tkinter import messagebox, ttk

from . import archivio_regole
from . import motore as V

SFONDO = "#f5f7fa"
BIANCO = "#ffffff"
BLU_SCURO = "#1f3a5f"
ARANCIO = "#d35400"
GRIGIO = "#6b7280"
VERDE = "#2e7d32"
ROSSO = "#c62828"
GIALLO = "#b26a00"


def prossima_decorrenza(oggi=None):
    """Di solito la prima rata parte il primo giorno del secondo mese successivo."""
    oggi = oggi or date.today()
    return V.aggiungi_mesi(date(oggi.year, oggi.month, 1), 2)


def _px(n):
    try:
        from ..gui import px
        return px(n)
    except Exception:
        return int(n)


class FinestraVerifica(tk.Toplevel):
    def __init__(self, genitore, campi_iniziali: dict | None = None, note: list[str] | None = None,
                 spiega=None):
        """campi_iniziali: {campo: testo} dai documenti; spiega(testo, scrivi, fine): riassunto con l'AI."""
        super().__init__(genitore)
        self.title("Verifica criteri Compass · CQS e Deleghe")
        try:
            from ..gui import adatta_finestra
            adatta_finestra(self, 1240, 800)
        except Exception:
            self.geometry("1180x780")
        self.configure(bg=SFONDO)
        self.spiega_fn = spiega
        self.campi = {}
        self.ultimo_risultato = ""
        self.iniziali = dict(campi_iniziali or {})
        self.note_iniziali = list(note or [])
        self._crea()

    # ================= INTERFACCIA =================
    def _crea(self):
        alto = tk.Frame(self, bg=ARANCIO)
        alto.pack(fill="x")
        tk.Label(alto, text="Criteri Compass", bg=ARANCIO, fg=BIANCO,
                 font=("Segoe UI", 16, "bold")).pack(side="left", padx=16, pady=10)
        self.sottotitolo = tk.Label(alto, text="", bg=ARANCIO, fg="#fde3d0", font=("Segoe UI", 10))
        self.sottotitolo.pack(side="left")
        self._pulsante(alto, "Chiudi", self.destroy, BIANCO, ARANCIO).pack(side="right", padx=12, pady=8)

        corpo = tk.Frame(self, bg=SFONDO)
        corpo.pack(fill="both", expand=True, padx=12, pady=10)

        # ---- Modulo a sinistra, con scorrimento ----
        sinistra = tk.Frame(corpo, bg=SFONDO, width=_px(480))
        sinistra.pack(side="left", fill="y")
        sinistra.pack_propagate(False)
        tela = tk.Canvas(sinistra, bg=SFONDO, highlightthickness=0)
        barra = ttk.Scrollbar(sinistra, orient="vertical", command=tela.yview)
        modulo = tk.Frame(tela, bg=SFONDO)
        modulo.bind("<Configure>", lambda e: tela.configure(scrollregion=tela.bbox("all")))
        tela.create_window((0, 0), window=modulo, anchor="nw")
        tela.configure(yscrollcommand=barra.set)
        tela.pack(side="left", fill="both", expand=True)
        barra.pack(side="right", fill="y")
        # rotella del mouse attiva solo quando il puntatore è sopra il modulo
        rotella = lambda e: tela.yview_scroll(int(-e.delta / 120), "units")
        sinistra.bind("<Enter>", lambda e: tela.bind_all("<MouseWheel>", rotella))
        sinistra.bind("<Leave>", lambda e: tela.unbind_all("<MouseWheel>"))

        # ---- selettore prodotto e settore ----
        sel = tk.Frame(modulo, bg=SFONDO)
        sel.pack(fill="x", pady=(2, 4))
        tk.Label(sel, text="Prodotto", bg=SFONDO, fg=ARANCIO, font=("Segoe UI", 10, "bold")).grid(
            row=0, column=0, sticky="w")
        tk.Label(sel, text="Settore", bg=SFONDO, fg=ARANCIO, font=("Segoe UI", 10, "bold")).grid(
            row=0, column=1, sticky="w", padx=(10, 0))
        self.var_prodotto = tk.StringVar(value="CQS")
        self.var_settore = tk.StringVar(value="Dipendente privato")
        cb_p = ttk.Combobox(sel, textvariable=self.var_prodotto, values=["CQS", "Delega"], state="readonly",
                            width=10, font=("Segoe UI", 10))
        cb_p.grid(row=1, column=0, sticky="w")
        self.cb_settore = ttk.Combobox(sel, textvariable=self.var_settore, state="readonly", width=24,
                                       font=("Segoe UI", 10))
        self.cb_settore.grid(row=1, column=1, sticky="w", padx=(10, 0))
        cb_p.bind("<<ComboboxSelected>>", lambda e: self._cambia_prodotto())
        self.cb_settore.bind("<<ComboboxSelected>>", lambda e: self.scegli_settore(self.var_settore.get()))
        self.area_modulo = tk.Frame(modulo, bg=SFONDO)
        self.area_modulo.pack(fill="x")
        self.settore = None
        self.prodotto = "CQS"

        pulsanti = tk.Frame(modulo, bg=SFONDO)
        pulsanti.pack(fill="x", pady=(14, 20))
        self._pulsante(pulsanti, "Verifica", self.verifica, ARANCIO, BIANCO).pack(side="left")
        self._pulsante(pulsanti, "Svuota", self.svuota, BIANCO, BLU_SCURO).pack(side="left", padx=8)

        # ---- Risultato a destra ----
        destra = tk.Frame(corpo, bg=BIANCO, highlightbackground="#d5dce5", highlightthickness=1)
        destra.pack(side="left", fill="both", expand=True, padx=(12, 0))
        barra_r = tk.Frame(destra, bg=BIANCO)
        barra_r.pack(fill="x", padx=10, pady=(8, 0))
        tk.Label(barra_r, text="Risultato", bg=BIANCO, fg=BLU_SCURO,
                 font=("Segoe UI", 12, "bold")).pack(side="left")
        self.pulsante_ai = self._pulsante(barra_r, "Spiega con l'AI", self.spiega_ai, BIANCO, BLU_SCURO)
        self.pulsante_ai.pack(side="right")
        self._pulsante(barra_r, "Copia", self.copia, BIANCO, BLU_SCURO).pack(side="right", padx=6)

        self.risultato = tk.Text(destra, wrap="word", width=1, height=1, relief="flat", bg=BIANCO,
                                 font=("Segoe UI", 10), padx=12, pady=10, state="disabled")
        barra2 = ttk.Scrollbar(destra, command=self.risultato.yview)
        self.risultato.configure(yscrollcommand=barra2.set)
        barra2.pack(side="right", fill="y")
        self.risultato.pack(fill="both", expand=True)
        for tag, colore, peso in [("titolo", BLU_SCURO, "bold"), ("ok", VERDE, "bold"),
                                  ("ko", ROSSO, "bold"), ("pre", GIALLO, "bold"),
                                  ("dettaglio", "#374151", "normal"), ("nota", GRIGIO, "normal"),
                                  ("ai", "#1f2937", "normal")]:
            self.risultato.tag_configure(tag, foreground=colore, font=("Segoe UI", 10, peso))
        self.risultato.tag_configure("ai", lmargin1=8, lmargin2=8, spacing1=2)
        self._scrivi("Scegli prodotto e settore, compila il modulo e premi Verifica.\n\n"
                     "DIPENDENTI\nObbligatori: data di nascita, data di assunzione, stipendio netto, rata, durata.\n"
                     "Consigliati: anzianità contributiva (per i limiti pensionistici), TFR, n. dipendenti, "
                     "e la valutazione dell'azienda sul DB di ogni assicurazione (esito, scoring, codice).\n\n"
                     "DELEGA\nInserisci anche la CQS in corso (compagnia, rata, montante residuo).\n\n"
                     "PENSIONATO\nObbligatori: data di nascita, pensione netta, quota cedibile "
                     "(dalla comunicazione dell'Ente), rata, durata.\n", "nota")
        if self.iniziali.get("_settore") in [st for (_, st) in V.SETTORI]:
            self.var_settore.set(self.iniziali["_settore"])
        self._cambia_prodotto()
        if self.note_iniziali:
            self._scrivi("\nDATI PRESI DAI DOCUMENTI (controllali e completa il resto)\n", "titolo")
            for n in self.note_iniziali:
                self._scrivi(f"  • {n}\n", "dettaglio")
        errori = list(archivio_regole.ultimo_errore.values())
        for e in errori:
            self._scrivi(f"\n⚠ Regole condivise non leggibili: {e}\n", "ko")

    # ================= MODULI PER SETTORE =================
    def _cambia_prodotto(self):
        prodotto = self.var_prodotto.get()
        settori = [st for (pr, st) in V.SETTORI if pr == prodotto]
        self.cb_settore.configure(values=settori)
        if self.var_settore.get() not in settori:
            self.var_settore.set(settori[0])
        self.scegli_settore(self.var_settore.get())

    def scegli_settore(self, nome):
        self.prodotto = self.var_prodotto.get()
        self.settore = nome
        for w in self.area_modulo.winfo_children():
            w.destroy()
        self.campi = {}
        self.campi_db = {}
        m = self.area_modulo
        if nome == "Pensionato":
            self._modulo_pensionati(m)
            self.sottotitolo.configure(text="Cessione del quinto della pensione · Pensionati · criteri Compass 07/2026")
        else:
            self._modulo_dipendenti(m, self.prodotto, nome)
            titolo = "Cessione del quinto" if self.prodotto == "CQS" else "Delegazione di pagamento"
            self.sottotitolo.configure(text=f"{titolo} · {nome} · criteri Compass 07/2026")
        self._precompila()
        self.ultimo_risultato = ""

    def _precompila(self):
        """Scrive nei campi i dati letti dai documenti (solo i campi presenti nel modulo di questo settore)."""
        valori = dict(self.iniziali)
        if self.prodotto == "Delega" and valori.get("_cqs_in_corso"):
            valori.setdefault("cqs_rata", valori["_cqs_in_corso"])
        for chiave, valore in valori.items():
            campo = self.campi.get(chiave)
            if campo is None or chiave.startswith("_"):
                continue
            if isinstance(campo, tk.Entry):
                campo.delete(0, "end")
                campo.insert(0, valore)
                campo.configure(fg="#111827")
            elif isinstance(campo, tk.BooleanVar):
                campo.set(bool(valore))
            else:
                campo.set(valore)

    def _imposta_decorrenza(self):
        c = self.campi["decorrenza"]
        c.delete(0, "end")
        c.insert(0, prossima_decorrenza().strftime("%d/%m/%Y"))
        c.configure(fg="#111827")

    def _modulo_dipendenti(self, m, prodotto, settore):
        delega = prodotto == "Delega"
        statale = settore == "Statale / pubblico"
        medico = settore == "Medico convenzionato"
        privato = settore in ("Dipendente privato", "Privato NO TFR", "Parapubblico")
        usa_tfr = not statale and not medico

        self._sezione(m, "Cliente  (non inserire nome o codice fiscale)")
        self._scelta(m, "sesso", "Sesso", ["M", "F"], "M")
        self._campo(m, "nascita", "Data di nascita", "gg/mm/aaaa")
        self._scelta(m, "cittadinanza", "Cittadinanza", ["Italiana", "UE", "Extra-UE"], "Italiana")

        self._sezione(m, "Lavoro")
        self._campo(m, "assunzione", "Data di assunzione", "gg/mm/aaaa")
        self._campo(m, "anz_anni", "Anzianità contributiva oggi: anni", "da estratto INPS")
        self._campo(m, "anz_mesi", "Anzianità contributiva oggi: mesi", "0-11")
        if statale:
            self._spunta(m, "militare", "Militare")
            self._spunta(m, "docente_neo", "Docente neoassunto a tempo indeterminato")
            self._spunta(m, "ferroviere", "Ferroviere")
            self._spunta(m, "carabiniere", "Carabiniere in ferma quadriennale volontaria")
        if privato or medico:
            self._scelta(m, "contratto", "Contratto",
                         ["Indeterminato", "Determinato", "Apprendistato", "Somministrazione-interinale"],
                         "Indeterminato")
        self._scelta(m, "part_time", "Part-time", ["No", "Orizzontale", "Verticale", "Misto"], "No")
        self._campo(m, "part_time_perc", "Part-time orizzontale %", "es. 75")
        if privato:
            self._scelta(m, "cig", "Cassa integrazione", ["No", "Ordinaria", "Straordinaria", "Per maltempo"], "No")
        self._spunta(m, "sospensione", "Aspettativa / sospensione / provv. disciplinari")
        if privato:
            self._campo(m, "dipendenti", "N. dipendenti azienda (o soci coop)", "")
            self._spunta(m, "cooperativa", "L'azienda è una cooperativa")

        self._tabella_valutazioni(m, prodotto, settore)

        self._sezione(m, "Reddito")
        self._campo(m, "netto", "Stipendio netto mensile €", "prima di cessioni/deleghe")
        if usa_tfr:
            self._campo(m, "tfr", "TFR maturato in azienda €", "")

        if delega:
            self._sezione(m, "CQS in corso")
            self._scelta(m, "cqs_compagnia", "Compagnia della CQS", V.COMPAGNIE_CQS, "Nessuna CQS in corso")
            self._campo(m, "cqs_rata", "Rata CQS €", "")
            self._campo(m, "cqs_residuo", "Montante residuo CQS €", "")
            self._spunta(m, "cqs_compass", "CQS stipulata da Compass", valore=True)

        self._sezione(m, "Richiesta")
        self._campo(m, "rata", "Rata delega €" if delega else "Rata €", "")
        self._campo(m, "durata", "Durata (mesi)", "24-120")
        self._campo(m, "decorrenza", "Decorrenza", "gg/mm/aaaa")
        self._imposta_decorrenza()

        self._sezione(m, "Altre trattenute in corso")
        self._campo(m, "rata_delega", "Rata altra delega / prestito aziendale €" if delega
                    else "Rata delega / prestito aziendale €", "")
        self._campo(m, "residuo_delega", "Montante residuo delega €", "")
        self._campo(m, "rata_pign", "Rata pignoramento €", "")
        self._campo(m, "residuo_pign", "Residuo pignoramento €", "")
        if delega:
            self._spunta(m, "pign_alimenti", "Il pignoramento è per alimenti")
        self._campo(m, "altre", "Altre trattenute (assic., alimenti…) €", "")

    def _tabella_valutazioni(self, m, prodotto, settore):
        """Una riga per assicurazione: esito sul DB, scoring (n/1) e codice/categoria."""
        self._sezione(m, "Valutazione azienda sui DB delle assicurazioni")
        tk.Label(m, text="Esito, scoring (es. 6 per 6/1) e codice/categoria dove previsto.", bg=SFONDO,
                 fg=GRIGIO, font=("Segoe UI", 8, "italic"), anchor="w").pack(fill="x")
        griglia = tk.Frame(m, bg=SFONDO)
        griglia.pack(fill="x", pady=(2, 0))
        for col, testo in enumerate(["Assicurazione", "Esito", "Scoring", "Codice"]):
            tk.Label(griglia, text=testo, bg=SFONDO, fg=GRIGIO, font=("Segoe UI", 8, "bold"),
                     anchor="w").grid(row=0, column=col, sticky="w", padx=(0, 4))
        self.campi_db = {}
        for i, riga in enumerate(V.righe_db(prodotto, settore), start=1):
            tk.Label(griglia, text=V.NOMI_DB.get(riga, riga), bg=SFONDO, font=("Segoe UI", 9),
                     anchor="w", width=19).grid(row=i, column=0, sticky="w", pady=1)
            esito = tk.StringVar(value="Non verificato")
            ttk.Combobox(griglia, textvariable=esito, values=V.ESITI_DB, state="readonly",
                         width=13).grid(row=i, column=1, sticky="w", padx=(0, 4))
            scoring = tk.Entry(griglia, width=5, font=("Segoe UI", 9), relief="flat",
                               highlightbackground="#c3ccd8", highlightthickness=1)
            scoring.grid(row=i, column=2, sticky="w", padx=(0, 4))
            codice = tk.StringVar(value="")
            if riga in V.CODICI_DB:
                ttk.Combobox(griglia, textvariable=codice, values=V.CODICI_DB[riga], state="readonly",
                             width=11).grid(row=i, column=3, sticky="w")
            self.campi_db[riga] = (esito, scoring, codice)

    def _leggi_valutazioni(self):
        valutazioni = {}
        for riga, (esito, scoring, codice) in getattr(self, "campi_db", {}).items():
            testo = scoring.get().strip().replace("/1", "")
            valutazioni[riga] = {
                "esito": esito.get(),
                "scoring": V.leggi_numero(testo, f"Scoring {V.NOMI_DB.get(riga, riga)}") if testo else None,
                "codice": codice.get() or None,
            }
        return valutazioni

    def _modulo_pensionati(self, m):
        self._sezione(m, "Cliente  (non inserire nome o codice fiscale)")
        self._campo(m, "nascita", "Data di nascita", "gg/mm/aaaa")
        self._scelta(m, "residenza", "Residenza",
                     ["Italia", "UE", "Portogallo", "Regno Unito", "Tunisia", "Altro"], "Italia")
        self._scelta(m, "invalidita", "Invalidità", ["Nessuna", "Invalido", "Sordomuto"], "Nessuna")
        self._spunta(m, "no_buono_stato", "NON può firmare la Dichiarazione di Buono Stato di Salute")

        self._sezione(m, "Pensione")
        self._campo(m, "pensione", "Pensione netta mensile €", "")
        self._campo(m, "quota_cedibile", "Quota cedibile (comunicazione Ente) €", "")
        self._campo(m, "altre", "Altre trattenute sulla pensione €", "")

        self._sezione(m, "Richiesta")
        self._campo(m, "rata", "Rata €", "min 50")
        self._campo(m, "durata", "Durata (mesi)", "24-120")
        self._campo(m, "decorrenza", "Decorrenza", "gg/mm/aaaa")
        self._imposta_decorrenza()
        tk.Label(m, text="Per i pensionati non si possono istruire deleghe di pagamento.", bg=SFONDO,
                 fg=GRIGIO, font=("Segoe UI", 9, "italic"), anchor="w").pack(fill="x", pady=(8, 0))

    def _sezione(self, genitore, testo):
        tk.Label(genitore, text=testo, bg=SFONDO, fg=ARANCIO, font=("Segoe UI", 10, "bold"),
                 anchor="w").pack(fill="x", pady=(12, 2))

    def _riga(self, genitore, etichetta):
        riga = tk.Frame(genitore, bg=SFONDO)
        riga.pack(fill="x", pady=2)
        tk.Label(riga, text=etichetta, bg=SFONDO, fg="#1f2937", font=("Segoe UI", 9),
                 width=30, anchor="w").pack(side="left")
        return riga

    def _campo(self, genitore, chiave, etichetta, suggerimento):
        riga = self._riga(genitore, etichetta)
        campo = tk.Entry(riga, font=("Segoe UI", 10), relief="flat", width=16,
                         highlightbackground="#c3ccd8", highlightthickness=1)
        campo.pack(side="left", fill="x", expand=True)
        campo.suggerimento = suggerimento
        if suggerimento:
            campo.insert(0, suggerimento)
            campo.configure(fg="#9ca3af")
            campo.bind("<FocusIn>", lambda e, c=campo: self._entra(c))
            campo.bind("<FocusOut>", lambda e, c=campo: self._esci(c))
        self.campi[chiave] = campo

    def _entra(self, c):
        if c.get() == c.suggerimento and c.cget("fg") == "#9ca3af":
            c.delete(0, "end")
            c.configure(fg="#111827")

    def _esci(self, c):
        if not c.get().strip():
            c.insert(0, c.suggerimento)
            c.configure(fg="#9ca3af")

    def _valore(self, chiave, predefinito=""):
        c = self.campi.get(chiave)
        if c is None:
            return predefinito
        if isinstance(c, tk.Entry):
            if c.cget("fg") == "#9ca3af":
                return ""
            return c.get().strip()
        return c.get()

    def _scelta(self, genitore, chiave, etichetta, valori, predefinito):
        riga = self._riga(genitore, etichetta)
        var = tk.StringVar(value=predefinito)
        ttk.Combobox(riga, textvariable=var, values=valori, state="readonly", width=24).pack(
            side="left", fill="x", expand=True)
        self.campi[chiave] = var

    def _spunta(self, genitore, chiave, etichetta, valore=False):
        var = tk.BooleanVar(value=valore)
        tk.Checkbutton(genitore, text=etichetta, variable=var, bg=SFONDO, font=("Segoe UI", 9),
                       anchor="w").pack(fill="x")
        self.campi[chiave] = var

    def _pulsante(self, genitore, testo, comando, sfondo, colore):
        return tk.Button(genitore, text=testo, command=comando, bg=sfondo, fg=colore,
                         activebackground=colore, activeforeground=sfondo, relief="flat",
                         font=("Segoe UI", 10, "bold"), cursor="hand2", padx=12, pady=5, bd=0,
                         highlightthickness=1, highlightbackground=colore)

    def _scrivi(self, testo, tag=None, pulisci=False):
        self.risultato.configure(state="normal")
        if pulisci:
            self.risultato.delete("1.0", "end")
        self.risultato.insert("end", testo, tag)
        self.risultato.configure(state="disabled")
        self.risultato.see("end")

    # ================= AZIONI =================
    def _leggi_pratica(self):
        n = V.leggi_numero
        anni = self._valore("anz_anni")
        mesi = self._valore("anz_mesi")
        anz = None
        if anni or mesi:
            anz = int(n(anni, "Anzianità anni")) * 12 + int(n(mesi, "Anzianità mesi"))
        dip = self._valore("dipendenti")
        return V.Pratica(
            prodotto=self.prodotto,
            settore=self.settore,
            sesso=self._valore("sesso", "M"),
            nascita=V.leggi_data(self._valore("nascita"), "Data di nascita"),
            assunzione=V.leggi_data(self._valore("assunzione"), "Data di assunzione"),
            netto=n(self._valore("netto"), "Stipendio netto", True),
            tfr=n(self._valore("tfr"), "TFR"),
            rata=n(self._valore("rata"), "Rata", True),
            durata=int(n(self._valore("durata"), "Durata", True)),
            decorrenza=V.leggi_data(self._valore("decorrenza"), "Decorrenza"),
            anzianita_contributiva_mesi=anz,
            dipendenti_azienda=int(n(dip, "N. dipendenti")) if dip else None,
            cooperativa=self._valore("cooperativa", False),
            contratto=self._valore("contratto", "Indeterminato"),
            part_time=self._valore("part_time", "No"),
            part_time_perc=n(self._valore("part_time_perc"), "Part-time %"),
            cig=self._valore("cig", "No"),
            cittadinanza=self._valore("cittadinanza", "Italiana"),
            sospensione=self._valore("sospensione", False),
            valutazioni=self._leggi_valutazioni(),
            militare=self._valore("militare", False),
            docente_neoassunto=self._valore("docente_neo", False),
            ferroviere=self._valore("ferroviere", False),
            carabiniere_ferma=self._valore("carabiniere", False),
            rata_delega=n(self._valore("rata_delega"), "Rata delega"),
            residuo_delega=n(self._valore("residuo_delega"), "Residuo delega"),
            rata_pignoramento=n(self._valore("rata_pign"), "Rata pignoramento"),
            residuo_pignoramento=n(self._valore("residuo_pign"), "Residuo pignoramento"),
            pignoramento_alimenti=self._valore("pign_alimenti", False),
            altre_trattenute=n(self._valore("altre"), "Altre trattenute"),
            cqs_compagnia=self._valore("cqs_compagnia", "Nessuna CQS in corso"),
            cqs_rata=n(self._valore("cqs_rata"), "Rata CQS"),
            cqs_residuo=n(self._valore("cqs_residuo"), "Residuo CQS"),
            cqs_compass=self._valore("cqs_compass", True),
        )

    def _leggi_pensionato(self):
        n = V.leggi_numero
        return V.PraticaPensionato(
            nascita=V.leggi_data(self._valore("nascita"), "Data di nascita"),
            pensione_netta=n(self._valore("pensione"), "Pensione netta", True),
            quota_cedibile=n(self._valore("quota_cedibile"), "Quota cedibile"),
            rata=n(self._valore("rata"), "Rata", True),
            durata=int(n(self._valore("durata"), "Durata", True)),
            decorrenza=V.leggi_data(self._valore("decorrenza"), "Decorrenza"),
            altre_trattenute=n(self._valore("altre"), "Altre trattenute"),
            invalidita=self._valore("invalidita"),
            residenza=self._valore("residenza"),
            buono_stato_salute=not self._valore("no_buono_stato"),
        )

    def verifica(self):
        try:
            if self.settore == "Pensionato":
                calcoli, generali, esiti = V.verifica_pensionato(self._leggi_pensionato())
            else:
                calcoli, generali, esiti = V.verifica_pratica(self._leggi_pratica())
        except ValueError as e:
            messagebox.showwarning("Verifica pratica", str(e), parent=self)
            return
        self.ultimo_risultato = V.testo_risultato(calcoli, generali, esiti)

        self._scrivi("", pulisci=True)
        self._scrivi("CALCOLI\n", "titolo")
        for c in calcoli:
            self._scrivi(f"  • {c}\n", "dettaglio")
        self._scrivi("\nRIEPILOGO\n", "titolo")
        ok = [e.nome for e in esiti if e.livello == "OK"]
        pre = [e.nome for e in esiti if e.livello == "PREACC"]
        ver = [e.nome for e in esiti if e.livello == "VERIFICA"]
        self._scrivi(f"  ✅ Assumibile con: {', '.join(ok) if ok else 'nessuna compagnia'}\n", "ok")
        if pre:
            self._scrivi(f"  ⚠️ Pre-accettazione: {', '.join(pre)}\n", "pre")
        if ver:
            self._scrivi(f"  ❔ Da verificare: {', '.join(ver)}\n", "pre")
        self._scrivi("\n")
        tag_esito = {"OK": "ok", "KO": "ko", "PREACC": "pre", "VERIFICA": "pre"}
        for e in esiti:
            self._scrivi(f"{V.SIMBOLO[e.livello]} {e.nome} — {V.ESITO[e.livello]}\n", tag_esito[e.livello])
            visti = set()
            for livello, testo in e.motivi:
                if testo in visti:
                    continue
                visti.add(testo)
                self._scrivi(f"     {V.SIMBOLO.get(livello, '•')} {testo}\n",
                             "nota" if livello == "INFO" else "dettaglio")
            self._scrivi("\n")
        self._scrivi(f"[{self.settore}] Verifica indicativa basata sui Criteri Assuntivi Compass 07/2026. "
                     "L'esito vincolante è "
                     "quello del simulatore / pre-accettazione Compass.\n", "nota")
        self.risultato.see("1.0")

    def svuota(self):
        self.scegli_settore(self.settore)
        self._scrivi("Modulo svuotato.\n", "nota", pulisci=True)

    def copia(self):
        if self.ultimo_risultato:
            self.clipboard_clear()
            self.clipboard_append(self.ultimo_risultato)
            messagebox.showinfo("Copia", "Risultato copiato negli appunti.", parent=self)

    def spiega_ai(self):
        if not self.ultimo_risultato:
            messagebox.showinfo("Spiega con l'AI", "Prima premi Verifica.", parent=self)
            return
        if self.spiega_fn is None:
            messagebox.showinfo("Spiega con l'AI", "L'assistente AI non è installato su questo PC "
                                "(vedi ⚙ Impostazioni → Assistente AI).", parent=self)
            return
        self.pulsante_ai.configure(state="disabled", text="Attendi...")
        self._scrivi("\nSPIEGAZIONE DELL'AI\n", "titolo")

        def scrivi(testo, tag="ai"):
            self.after(0, self._scrivi, testo, tag)

        def fine():
            self.after(0, lambda: self.pulsante_ai.configure(state="normal", text="Spiega con l'AI"))
            self.after(0, self._scrivi, "\n")

        self.spiega_fn(self.ultimo_risultato, scrivi, fine)
