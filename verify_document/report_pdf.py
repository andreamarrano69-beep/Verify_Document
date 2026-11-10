"""Report PDF da consegnare al cliente o alla finanziaria.

Contenuto:
1. intestazione con logo e dati dello studio (da impostazioni.json)
2. esito complessivo e rischio di alterazione
3. sintesi dei redditi: per ogni documento regime/tipo e importo mensile lordo e netto
4. confronto tra i documenti (se più di uno)
5. dettaglio di ogni documento: dati principali e controlli
6. nota sui limiti dello strumento, numeri di pagina

Usa i font standard del PDF (Helvetica): i simboli non supportati vengono convertiti.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from xml.sax.saxutils import escape

from .report import Esito, Report, etichetta_campo, formatta_valore, sintesi
from .validators import formatta_euro

COLORI = {
    Esito.OK: ("#1e7b34", "#e6f4ea"),
    Esito.ATTENZIONE: ("#8a5a00", "#fff4d6"),
    Esito.ERRORE: ("#b3261e", "#fde7e7"),
    Esito.INFO: ("#1a5a96", "#e8f0fb"),
}
BLU = "#1a5a96"
GRIGIO = "#57606a"

# caratteri non presenti nei font standard del PDF
_SOSTITUZIONI = {
    "−": "-", "≈": "~", "→": "->", "↔": "<->", "⇄": "<->", "≤": "<=", "≥": ">=",
    "✔": "", "✘": "", "⚠": "", "ℹ": "", "⏻": "", "≠": "<>", "×": "x",
}

AVVERTENZA = (
    "Il presente report è prodotto da uno strumento automatico che verifica la coerenza formale e "
    "aritmetica dei documenti e segnala possibili anomalie o segni di alterazione dei file. Non certifica "
    "l'autenticità dei documenti né sostituisce la verifica di un professionista o delle fonti ufficiali "
    "(datore di lavoro, INPS, Agenzia delle Entrate). Gli importi mensili sono calcolati dai dati dei "
    "documenti e hanno valore indicativo."
)

# Dati mostrati nel dettaglio di ogni documento (gli altri restano nella tabella completa)
CAMPI_ESCLUSI = {"data_nascita_da_cf", "sesso", "mensilita_aggiuntiva", "tredicesima", "irpef_lorda_teorica",
                 "imposta_lorda_calcolata", "totale_trattenute_calcolato", "base_netta_quinto"}


def _t(testo) -> str:
    """Testo sicuro per Paragraph: caratteri supportati e XML escapato."""
    s = str(testo if testo is not None else "")
    for a, b in _SOSTITUZIONI.items():
        s = s.replace(a, b)
    return escape(s.strip())


def _periodo(r: Report) -> str:
    d = r.dati
    if d.get("periodo"):
        return str(d["periodo"])
    if d.get("periodo_imposta"):
        return f"Anno {d['periodo_imposta']}"
    if d.get("anno"):
        return f"Anno {d['anno']}"
    if d.get("data_scadenza"):
        return f"Scad. {formatta_valore('data_scadenza', d['data_scadenza'])}"
    return "-"


def _cliente(documenti: list[tuple[str, Report]]) -> str:
    """Nome e codice fiscale del cliente, se ricavabili dai documenti."""
    nomi, codici = [], []
    for _, r in documenti:
        d = r.dati
        if d.get("cognome") and d.get("nome"):
            nomi.append(f"{d['cognome']} {d['nome']}")
        elif d.get("nominativo"):
            nomi.append(d["nominativo"])
        for k in ("codice_fiscale", "codice_fiscale_dipendente", "codice_fiscale_contribuente",
                  "codice_fiscale_pensionato"):
            if d.get(k):
                codici.append(d[k])
    nomi, codici = list(dict.fromkeys(nomi)), list(dict.fromkeys(codici))
    parti = []
    if nomi:
        parti.append(", ".join(nomi))
    if codici:
        parti.append("C.F. " + ", ".join(codici))
    return " - ".join(parti) or "non indicato"


def genera_report_pdf(destinazione: str | Path, documenti: list[tuple[str, Report]],
                      confronto=None, impostazioni: dict | None = None, oscura: bool | None = None) -> Path:
    """Crea il PDF. ``documenti``: [(nome file, Report)]; ``confronto``: EsitoConfronto o None.

    ``oscura``: dati personali oscurati (nome → iniziali, codice fiscale, data di nascita, numeri di documento);
    se non indicato segue l'impostazione "oscura_dati_esportati" (attiva per default).
    """
    if oscura is None:
        oscura = (impostazioni or {}).get("oscura_dati_esportati", "1") != "0"
    if oscura:
        from .anonimizza import oscura_documenti

        documenti, confronto = oscura_documenti(documenti, confronto)
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_RIGHT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import (CondPageBreak, Image, KeepTogether, Paragraph, SimpleDocTemplate, Spacer,
                                    Table, TableStyle)

    imp = impostazioni or {}
    dest = Path(destinazione)
    larghezza = A4[0] - 30 * mm

    base = getSampleStyleSheet()
    st = {
        "titolo": ParagraphStyle("titolo", parent=base["Title"], fontName="Helvetica-Bold", fontSize=18,
                                 textColor=colors.HexColor(BLU), alignment=0, spaceAfter=2),
        "h2": ParagraphStyle("h2", parent=base["Heading2"], fontName="Helvetica-Bold", fontSize=13,
                             textColor=colors.HexColor(BLU), spaceBefore=10, spaceAfter=6),
        "h3": ParagraphStyle("h3", parent=base["Heading3"], fontName="Helvetica-Bold", fontSize=11,
                             spaceBefore=8, spaceAfter=4),
        "n": ParagraphStyle("n", parent=base["Normal"], fontName="Helvetica", fontSize=9, leading=11.5),
        "piccolo": ParagraphStyle("piccolo", parent=base["Normal"], fontName="Helvetica", fontSize=7.5,
                                  leading=9.5, textColor=colors.HexColor(GRIGIO)),
        "cella": ParagraphStyle("cella", parent=base["Normal"], fontName="Helvetica", fontSize=8, leading=10),
        "cella_b": ParagraphStyle("cella_b", parent=base["Normal"], fontName="Helvetica-Bold", fontSize=8,
                                  leading=10),
        "cella_d": ParagraphStyle("cella_d", parent=base["Normal"], fontName="Helvetica", fontSize=8,
                                  leading=10, alignment=TA_RIGHT),
        "studio": ParagraphStyle("studio", parent=base["Normal"], fontName="Helvetica", fontSize=8.5,
                                 leading=11, alignment=TA_RIGHT, textColor=colors.HexColor(GRIGIO)),
        "grande": ParagraphStyle("grande", parent=base["Normal"], fontName="Helvetica-Bold", fontSize=14,
                                 leading=17, textColor=colors.white),
        "etichetta": ParagraphStyle("etichetta", parent=base["Normal"], fontName="Helvetica-Bold", fontSize=7,
                                    leading=9, textColor=colors.HexColor("#c9dcf2")),
    }

    def P(testo, stile="n"):
        return Paragraph(_t(testo), st[stile])

    def badge(esito: Esito):
        fg, _ = COLORI[esito]
        return Paragraph(f'<font color="{fg}"><b>{esito.value}</b></font>', st["cella"])

    def stile_tabella(intestazione=True, righe_colore=None):
        comandi = [
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#d0d7de")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]
        if intestazione:
            comandi += [("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(BLU)),
                        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white)]
        for riga, colore in (righe_colore or []):
            comandi.append(("BACKGROUND", (0, riga), (-1, riga), colors.HexColor(colore)))
        return TableStyle(comandi)

    def intestazione_col(*titoli):
        return [Paragraph(f'<font color="white"><b>{_t(x)}</b></font>', st["cella"]) for x in titoli]

    storia = []

    # --- 1. Intestazione -------------------------------------------------------------
    logo = None
    if imp.get("logo") and Path(imp["logo"]).is_file():
        try:
            from reportlab.lib.utils import ImageReader

            w, h = ImageReader(imp["logo"]).getSize()
            altezza = 18 * mm
            logo = Image(imp["logo"], width=altezza * w / h, height=altezza)
            if logo.drawWidth > 60 * mm:
                logo = Image(imp["logo"], width=60 * mm, height=60 * mm * h / w)
        except Exception:
            logo = None
    righe_studio = [f"<b>{_t(imp.get('studio'))}</b>" if imp.get("studio") else ""]
    for k in ("indirizzo", "contatti"):
        if imp.get(k):
            righe_studio.append(_t(imp[k]))
    if imp.get("partita_iva"):
        righe_studio.append("P.IVA " + _t(imp["partita_iva"]))
    studio = Paragraph("<br/>".join(x for x in righe_studio if x), st["studio"])
    testata = Table([[logo or "", studio]], colWidths=[larghezza * 0.45, larghezza * 0.55])
    testata.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                 ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    storia += [testata, Spacer(1, 6 * mm), Paragraph("Report di verifica documenti", st["titolo"])]
    adesso = datetime.now()
    info = [f"<b>Cliente:</b> {_t(_cliente(documenti))}",
            f"<b>Data:</b> {adesso:%d/%m/%Y %H:%M}",
            f"<b>Documenti esaminati:</b> {len(documenti)}"]
    if imp.get("operatore"):
        info.append(f"<b>Operatore:</b> {_t(imp['operatore'])}")
    if oscura:
        info.append("<b>Dati personali oscurati</b>")
    storia += [Paragraph(" &nbsp;&nbsp;|&nbsp;&nbsp; ".join(info), st["n"]), Spacer(1, 4 * mm)]

    # --- 2. Esito complessivo -------------------------------------------------------------
    esiti = [r.esito_globale for _, r in documenti]
    if confronto is not None:
        esiti.append(confronto.report.esito_globale)
    peggiore = Esito.ERRORE if Esito.ERRORE in esiti else Esito.ATTENZIONE if Esito.ATTENZIONE in esiti else Esito.OK
    conteggi = {e: sum(1 for _, r in documenti if r.esito_globale == e) for e in (Esito.OK, Esito.ATTENZIONE, Esito.ERRORE)}
    rischi = [r.dati.get("rischio_alterazione") for _, r in documenti if r.dati.get("rischio_alterazione")]
    livelli = [x.split()[0] for x in rischi]
    rischio = next((lv for lv in ("ALTO", "MEDIO", "BASSO") if lv in livelli), None)
    fg, bg = COLORI[peggiore]
    testo_esito = {
        Esito.OK: "Nessuna anomalia rilevata",
        Esito.ATTENZIONE: "Alcuni punti da verificare",
        Esito.ERRORE: "Rilevate anomalie: verificare i documenti indicati",
    }[peggiore]
    dettagli = (f"Documenti: {conteggi[Esito.OK]} OK, {conteggi[Esito.ATTENZIONE]} con punti di attenzione, "
                f"{conteggi[Esito.ERRORE]} con errori")
    if confronto is not None:
        dettagli += f". Confronto tra documenti: {confronto.report.esito_globale.value}"
    if rischio:
        dettagli += f". Rischio di alterazione dei file PDF: {rischio}"
    elif not any(n.lower().endswith(".pdf") for n, _ in documenti):
        dettagli += ". Analisi dei file PDF non eseguita (nessun PDF originale)"
    box = Table([[Paragraph(f'<font color="{fg}" size="13"><b>ESITO COMPLESSIVO: {peggiore.value}</b></font>'
                            f'<br/><font color="{fg}">{_t(testo_esito)}</font>', st["n"])],
                 [Paragraph(_t(dettagli), st["n"])]], colWidths=[larghezza])
    box.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(bg)),
                             ("BOX", (0, 0), (-1, -1), 1, colors.HexColor(fg)),
                             ("LEFTPADDING", (0, 0), (-1, -1), 8), ("TOPPADDING", (0, 0), (-1, -1), 6),
                             ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    storia += [box, Spacer(1, 2 * mm)]

    # --- 3. Sintesi dei redditi -----------------------------------------------------------
    righe = [intestazione_col("Documento", "Tipo", "Periodo", "Regime / tipo di reddito",
                              "Mensile lordo", "Mensile netto", "Esito")]
    colori_righe = []
    for i, (nome, r) in enumerate(documenti, start=1):
        s = sintesi(r)
        righe.append([P(nome, "cella"), P(r.tipo_documento, "cella"), P(_periodo(r), "cella"),
                      P(s.categoria if s and s.categoria else "-", "cella_b"),
                      P(formatta_euro(s.mensile_lordo) if s and s.mensile_lordo is not None else "-", "cella_d"),
                      P(formatta_euro(s.mensile_netto) if s and s.mensile_netto is not None else "-", "cella_d"),
                      badge(r.esito_globale)])
        colori_righe.append((i, COLORI[r.esito_globale][1]))
    tab = Table(righe, colWidths=[w * larghezza for w in (0.19, 0.15, 0.11, 0.21, 0.11, 0.11, 0.12)],
                repeatRows=1)
    tab.setStyle(stile_tabella(righe_colore=colori_righe))
    storia += [Paragraph("Sintesi dei redditi", st["h2"]), tab,
               Paragraph("Mensile netto: per buste paga e pensioni è l'importo del mese; per Modello Redditi e CU "
                         "è il reddito annuo al netto delle imposte diviso 12.", st["piccolo"])]

    # --- 4. Confronto ------------------------------------------------------------------------
    if confronto is not None:
        storia.append(Paragraph("Confronto tra i documenti", st["h2"]))
        storia.append(_tabella_controlli(confronto.report, larghezza, P, badge, stile_tabella, intestazione_col))
        for cf, righe_t in confronto.tabelle.items():
            if not righe_t:
                continue
            dati = [intestazione_col("Periodo", "Lordo", "Netto", "Netto/lordo", "Progressivo imp.", "Esito")]
            for x in righe_t:
                nl = f"{x['netto_su_lordo']}%".replace(".", ",") if x.get("netto_su_lordo") else "-"
                prog = x.get("progressivo_imponibile_fiscale")
                dati.append([P(x["periodo"], "cella"), P(formatta_euro(x["lordo"]), "cella_d"),
                             P(formatta_euro(x["netto"]), "cella_d"), P(nl, "cella_d"),
                             P(formatta_euro(prog) if prog is not None else "-", "cella_d"),
                             badge(Esito(x["esito"]))])
            t = Table(dati, colWidths=[w * larghezza for w in (0.28, 0.15, 0.15, 0.12, 0.17, 0.13)], repeatRows=1)
            t.setStyle(stile_tabella())
            storia += [Spacer(1, 3 * mm), Paragraph(f"Andamento mese per mese - C.F. {_t(cf)}", st["h3"]), t]

    # --- 5. Dettaglio dei documenti -------------------------------------------------------------
    storia.append(CondPageBreak(90 * mm))  # nuova pagina solo se lo spazio rimasto è poco
    storia.append(Paragraph("Dettaglio dei documenti", st["h2"]))
    for n, (nome, r) in enumerate(documenti, start=1):
        blocco = [Paragraph(f"{n}. {_t(nome)} - {_t(r.tipo_documento)}", st["h3"])]
        s = sintesi(r)
        if s:
            celle = [[Paragraph(_t(s.etichetta.upper()), st["etichetta"]),
                      Paragraph("IMPORTO MENSILE LORDO", st["etichetta"]),
                      Paragraph("IMPORTO MENSILE NETTO", st["etichetta"])],
                     [Paragraph(_t(s.categoria or "non determinato"), st["grande"]),
                      Paragraph(_t(formatta_euro(s.mensile_lordo)), st["grande"]),
                      Paragraph(_t(formatta_euro(s.mensile_netto)), st["grande"])]]
            fascia = Table(celle, colWidths=[larghezza * 0.5, larghezza * 0.25, larghezza * 0.25])
            fascia.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(BLU)),
                                        ("LEFTPADDING", (0, 0), (-1, -1), 8), ("TOPPADDING", (0, 0), (-1, 0), 6),
                                        ("BOTTOMPADDING", (0, -1), (-1, -1), 8), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
            blocco.append(fascia)
        storia.append(KeepTogether(blocco))
        campi = [(etichetta_campo(k), formatta_valore(k, v)) for k, v in r.dati.items()
                 if v is not None and k not in CAMPI_ESCLUSI]
        if campi:
            dati = []
            for i in range(0, len(campi), 2):
                coppia = campi[i:i + 2] + [("", "")] * (2 - len(campi[i:i + 2]))
                dati.append([P(coppia[0][0], "cella"), P(coppia[0][1], "cella_b"),
                             P(coppia[1][0], "cella"), P(coppia[1][1], "cella_b")])
            t = Table(dati, colWidths=[w * larghezza for w in (0.22, 0.28, 0.22, 0.28)])
            t.setStyle(stile_tabella(intestazione=False))
            storia += [Spacer(1, 2 * mm), t]
        storia += [Spacer(1, 2 * mm),
                   _tabella_controlli(r, larghezza, P, badge, stile_tabella, intestazione_col), Spacer(1, 4 * mm)]

    # --- 6. Note ----------------------------------------------------------------------------------
    storia += [Spacer(1, 4 * mm), Paragraph("Note", st["h3"]), Paragraph(_t(AVVERTENZA), st["piccolo"])]
    if imp.get("note"):
        storia += [Spacer(1, 2 * mm), Paragraph(_t(imp["note"]), st["piccolo"])]
    if imp.get("operatore"):
        storia += [Spacer(1, 12 * mm),
                   Paragraph(f"Firma ({_t(imp['operatore'])}) ______________________________", st["n"])]

    def pagina(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(colors.HexColor(GRIGIO))
        sinistra = _t(imp.get("studio") or "Verify Document").replace("&amp;", "&")
        canvas.drawString(15 * mm, 10 * mm, f"{sinistra} - Report di verifica documenti - {adesso:%d/%m/%Y}")
        canvas.drawRightString(A4[0] - 15 * mm, 10 * mm, f"Pagina {doc.page}")
        canvas.setStrokeColor(colors.HexColor("#d0d7de"))
        canvas.line(15 * mm, 13 * mm, A4[0] - 15 * mm, 13 * mm)
        canvas.restoreState()

    doc = SimpleDocTemplate(str(dest), pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm,
                            topMargin=14 * mm, bottomMargin=18 * mm,
                            title="Report di verifica documenti", author=imp.get("studio") or "Verify Document",
                            creator="Verify Document")
    doc.build(storia, onFirstPage=pagina, onLaterPages=pagina)
    return dest


def _tabella_controlli(r: Report, larghezza, P, badge, stile_tabella, intestazione_col):
    from reportlab.platypus import Paragraph, Table

    righe = [intestazione_col("Esito", "Controllo", "Dettaglio")]
    colori = []
    for gruppo, controlli in r.gruppi().items():
        righe.append([Paragraph(f'<font color="white"><b>{_t(gruppo.upper())}</b></font>',
                                P("", "cella").style), "", ""])
        colori.append((len(righe) - 1, "#57606a"))
        for c in controlli:
            righe.append([badge(c.esito), P(c.nome, "cella_b"), P(c.dettaglio, "cella")])
            colori.append((len(righe) - 1, COLORI[c.esito][1]))
    t = Table(righe, colWidths=[larghezza * 0.12, larghezza * 0.24, larghezza * 0.64], repeatRows=1)
    stile = stile_tabella(righe_colore=colori)
    for i, (riga, colore) in enumerate(colori):
        if colore == "#57606a":
            stile.add("SPAN", (0, riga), (-1, riga))
    t.setStyle(stile)
    return t
