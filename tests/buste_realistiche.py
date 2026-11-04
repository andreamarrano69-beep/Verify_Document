"""Genera buste paga con impaginazione "da software paghe" (riquadri, griglia, etichette sopra e valori
sotto in colonne) e le relative scansioni rumorose e storte, per i test di lettura e OCR."""

from pathlib import Path

ATTESI = {
    "totale_competenze": "2150.00", "totale_trattenute": "517.74", "netto": "1632.00",
    "arrotondamento": "0.14", "arrotondamento_precedente": "0.40", "imponibile_previdenziale": "2150.00",
    "contributi_dipendente": "197.59", "irpef_lorda": "449.05", "irpef_netta": "320.15",
}


def busta_a_colonne(percorso: Path) -> Path:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    c = canvas.Canvas(str(percorso), pagesize=A4)
    _, altezza = A4

    def cella(x, y, w, h, etichetta, valore, a_destra=False):
        c.setLineWidth(0.8)
        c.rect(x, y, w, h)
        c.setFont("Helvetica", 6.5)
        c.drawString(x + 3, y + h - 8, etichetta)
        c.setFont("Helvetica-Bold", 9)
        if a_destra:
            c.drawRightString(x + w - 4, y + 5, valore)
        else:
            c.drawString(x + 4, y + 5, valore)

    c.setFont("Helvetica-Bold", 12)
    c.drawString(30, altezza - 40, "CEDOLINO PAGA")
    c.setFont("Helvetica", 8)
    c.drawString(400, altezza - 40, "LIBRO UNICO DEL LAVORO")
    y = altezza - 80
    cella(30, y, 300, 26, "AZIENDA", "ESEMPIO SRL - VIA ROMA 1 ROMA")
    cella(330, y, 120, 26, "PARTITA IVA", "12345678903")
    cella(450, y, 115, 26, "PERIODO DI RETRIBUZIONE", "OTTOBRE 2026")
    y -= 26
    cella(30, y, 220, 26, "COGNOME E NOME", "ROSSI MARIO")
    cella(250, y, 140, 26, "CODICE FISCALE", "RSSMRA80A01H501U")
    cella(390, y, 90, 26, "DATA ASSUNZIONE", "01/03/2019")
    cella(480, y, 85, 26, "LIVELLO", "4")
    y -= 30
    colonne = [30, 80, 330, 390, 470, 565]
    c.setFont("Helvetica-Bold", 7)
    c.rect(30, y, 535, 16)
    for i, t in enumerate(["COD.", "DESCRIZIONE", "ORE/GG", "COMPETENZE", "TRATTENUTE"]):
        c.drawString(colonne[i] + 3, y + 5, t)
    voci = [("0010", "Retribuzione ordinaria", "168,00", "2.000,00", ""), ("0020", "Superminimo", "", "150,00", ""),
            ("1000", "Contributo IVS", "", "", "197,59"), ("2000", "Ritenute IRPEF", "", "", "320,15")]
    c.setFont("Helvetica", 8.5)
    for voce in voci:
        y -= 15
        c.rect(30, y, 535, 15)
        for i, v in enumerate(voce):
            if i >= 2:
                c.drawRightString(colonne[i + 1] - 4, y + 4, v)
            else:
                c.drawString(colonne[i] + 3, y + 4, v)
    for x in colonne[1:-1]:
        c.line(x, y, x, y + 16 + 15 * len(voci))
    larghezza = 535 / 5
    y -= 40
    for i, (e, v) in enumerate([("IMPONIBILE PREVIDENZIALE", "2.150,00"), ("CONTRIBUTI DIPENDENTE", "197,59"),
                                ("IMPONIBILE FISCALE", "1.952,41"), ("IRPEF LORDA", "449,05"),
                                ("IRPEF NETTA", "320,15")]):
        cella(30 + i * larghezza, y, larghezza, 26, e, v, a_destra=True)
    y -= 40
    for i, (e, v) in enumerate([("TOTALE COMPETENZE", "2.150,00"), ("TOTALE TRATTENUTE", "517,74"),
                                ("ARROTONDAMENTO PRECEDENTE", "0,40"), ("ARROTONDAMENTO ATTUALE", "0,14"),
                                ("NETTO DEL MESE", "1.632,00")]):
        cella(30 + i * larghezza, y, larghezza, 30, e, v, a_destra=True)
    c.save()
    return percorso


def scansione(pdf: Path, uscita: Path, dpi: int = 200, angolo: float = -2.0, seme: int = 2) -> Path:
    """Simula una scansione: storta, sfocata, rumorosa, carta grigia, compressione JPEG; salvata come PDF."""
    import numpy as np
    import pypdfium2 as pdfium
    from PIL import Image, ImageFilter

    documento = pdfium.PdfDocument(str(pdf))
    img = documento[0].render(scale=dpi / 72).to_pil().convert("L")
    documento.close()
    img = img.rotate(angolo, expand=True, fillcolor=255, resample=Image.BICUBIC).filter(ImageFilter.GaussianBlur(0.8))
    a = np.asarray(img).astype(np.int16) + np.random.default_rng(seme).normal(0, 18, img.size[::-1]).astype(np.int16)
    img = Image.fromarray((a * 0.85 + 30).clip(0, 255).astype(np.uint8))
    jpg = uscita.with_suffix(".jpg")
    img.save(jpg, quality=55)
    with Image.open(jpg) as j:
        j.save(uscita, resolution=dpi)
    return uscita


CU_ATTESI = {
    "reddito_indeterminato": "25381.33", "giorni_lavoro": 365, "ritenute_irpef": "4161.95",
    "addizionale_regionale": "380.00", "addizionale_comunale_saldo": "95.00",
    "addizionale_comunale_acconto": "55.00", "imposta_lorda": "5837.71", "totale_detrazioni": "1675.76",
    "imponibile_previdenziale": "27950.00", "contributi_lavoratore": "2568.67",
}


def cu_a_caselle(percorso: Path, sostituzioni: dict | None = None) -> Path:
    """CU con caselle numerate: numero e descrizione in alto (anche su due righe), importo in basso a destra.

    ``sostituzioni``: {valore originale: valore alterato}, per simulare una CU modificata."""
    sostituzioni = sostituzioni or {}
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    c = canvas.Canvas(str(percorso), pagesize=A4)
    _, altezza = A4

    def casella(x, y, w, h, numero, descrizione, valore=""):
        c.setLineWidth(0.6)
        c.rect(x, y, w, h)
        c.setFont("Helvetica-Bold", 6)
        c.drawString(x + 2, y + h - 7, str(numero))
        c.setFont("Helvetica", 5.5)
        for i, riga in enumerate(descrizione.split("\n")):
            c.drawString(x + 2 + (8 if i == 0 else 0), y + h - 7 - 6.5 * i, riga)
        valore = sostituzioni.get(valore, valore)
        if valore:
            c.setFont("Courier-Bold", 9)
            c.drawRightString(x + w - 3, y + 4, valore)

    def titolo(y, testo):
        c.setFont("Helvetica-Bold", 8)
        c.drawString(30, y, testo)

    c.setFont("Helvetica-Bold", 13)
    c.drawString(30, altezza - 40, "CERTIFICAZIONE UNICA 2026")
    c.setFont("Helvetica", 7)
    c.drawString(30, altezza - 52, "CERTIFICAZIONE LAVORO DIPENDENTE, ASSIMILATI ED ASSISTENZA FISCALE - Periodo d'imposta 2025")
    titolo(altezza - 75, "DATI RELATIVI AL SOSTITUTO D'IMPOSTA")
    y = altezza - 105
    casella(30, y, 160, 26, 1, "Codice fiscale", "12345678903")
    casella(190, y, 375, 26, 2, "Cognome o Denominazione", "ESEMPIO SRL")
    titolo(y - 15, "DATI RELATIVI AL DIPENDENTE, PENSIONATO O ALTRO PERCETTORE DELLE SOMME")
    y -= 45
    casella(30, y, 160, 26, 1, "Codice fiscale", "RSSMRA80A01H501U")
    casella(190, y, 190, 26, 2, "Cognome", "ROSSI")
    casella(380, y, 185, 26, 3, "Nome", "MARIO")
    titolo(y - 15, "DATI FISCALI")
    w = 535 / 4
    y -= 50
    for i, (n, d, v) in enumerate([(1, "Redditi di lavoro dipendente ed\nassimilati (indeterminato)", "25.381,33"),
                                   (2, "Redditi di lavoro dipendente ed\nassimilati (determinato)", ""),
                                   (3, "Redditi di pensione", ""),
                                   (6, "Numero di giorni per i quali spettano\nle detrazioni - Lavoro dipendente", "365")]):
        casella(30 + i * w, y, w, 32, n, d, v)
    y -= 32
    for i, (n, d, v) in enumerate([(7, "Numero di giorni - Pensione", ""), (8, "Data inizio rapporto", "01/03/2019"),
                                   (9, "Data cessazione rapporto", ""), (10, "In forza al 31/12", "X")]):
        casella(30 + i * w, y, w, 26, n, d, v)
    y -= 32
    for i, (n, d, v) in enumerate([(21, "Ritenute Irpef", "4.161,95"),
                                   (22, "Addizionale regionale\nall'Irpef", "380,00"),
                                   (26, "Saldo 2025 addizionale\ncomunale all'Irpef", "95,00"),
                                   (29, "Acconto 2026 addizionale\ncomunale all'Irpef", "55,00")]):
        casella(30 + i * w, y, w, 32, n, d, v)
    titolo(y - 15, "DETRAZIONI E CREDITI")
    y -= 50
    for i, (n, d, v) in enumerate([(361, "Imposta lorda", "5.837,71"),
                                   (362, "Detrazioni per carichi\ndi famiglia", ""),
                                   (367, "Detrazioni per redditi di\nlavoro dipendente", "1.675,76"),
                                   (373, "Totale detrazioni", "1.675,76")]):
        casella(30 + i * w, y, w, 32, n, d, v)
    y -= 32
    casella(30, y, w, 26, 392, "Trattamento integrativo erogato", "")
    titolo(y - 15, "DATI PREVIDENZIALI E ASSISTENZIALI INPS")
    y -= 50
    w3 = 535 / 3
    for i, (n, d, v) in enumerate([(1, "Matricola azienda", "1234567890"),
                                   (4, "Imponibile previdenziale", "27.950,00"),
                                   (5, "Contributi a carico del\nlavoratore trattenuti", "2.568,67")]):
        casella(30 + i * w3, y, w3, 32, n, d, v)
    c.save()
    return percorso
