"""Verifica rapida che il programma (in particolare il .exe) contenga tutto il necessario.

Avvio:  VerifyDocument.exe --autotest     oppure     python avvia_gui.py --autotest
Il risultato è scritto in %TEMP%\\verify_document_autotest.log; codice di uscita 0 = tutto OK.
"""

from __future__ import annotations

import sys
import tempfile
import traceback
from pathlib import Path

LOG = Path(tempfile.gettempdir()) / "verify_document_autotest.log"


def esegui() -> int:
    from . import __version__
    from .risorse import e_eseguibile, risorsa

    righe = [f"Verify Document {__version__} - autotest ({'exe' if e_eseguibile() else 'sorgente'})"]
    errori = 0

    def passo(nome, funzione):
        nonlocal errori
        try:
            esito = funzione()
            righe.append(f"[OK]     {nome}" + (f": {esito}" if esito else ""))
        except Exception:
            errori += 1
            righe.append(f"[ERRORE] {nome}\n{traceback.format_exc()}")

    tmp = Path(tempfile.mkdtemp(prefix="verify_document_"))

    def esempi():
        from .cli import analizza_documento

        file = sorted(risorsa("esempi").rglob("*.txt"))
        assert file, "cartella esempi non trovata"
        tipi = {analizza_documento(f)[1].tipo_documento for f in file}
        return f"{len(file)} documenti, {len(tipi)} tipi"

    def confronto():
        from .cli import analizza_documento
        from .confronto import confronta

        docs = [(f.name, analizza_documento(f)[1]) for f in sorted(risorsa("esempi/pensionato").glob("*.txt"))]
        return confronta(docs).report.esito_globale.value

    def pdf_e_autenticita():
        from reportlab.pdfgen import canvas

        from .cli import analizza_documento

        pdf = tmp / "busta.pdf"
        c = canvas.Canvas(str(pdf))
        c.setFont("Courier", 9)
        for i, riga in enumerate(risorsa("esempi/busta_paga_esempio.txt").read_text(encoding="utf-8").splitlines()):
            c.drawString(30, 800 - 12 * i, riga)
        c.save()
        _, r = analizza_documento(pdf, usa_ocr=False)
        assert r.tipo_documento == "Busta paga", r.tipo_documento
        return f"{r.esito_globale.value}, rischio {r.dati.get('rischio_alterazione')}"

    def pdfium():
        import pypdfium2 as pdfium

        immagine = pdfium.PdfDocument(str(tmp / "busta.pdf"))[0].render(scale=1).to_pil()
        return f"pagina {immagine.size[0]}x{immagine.size[1]}"

    def ocr():
        import pypdfium2 as pdfium

        from .estrazione import _ocr_immagine, trova_tesseract

        percorso, lingua = trova_tesseract()
        if percorso is None:
            if e_eseguibile():
                raise RuntimeError("Tesseract non incluso nel programma: scansioni e foto non leggibili")
            return "non disponibile (Tesseract non installato) - ignorato fuori dal .exe"
        immagine = pdfium.PdfDocument(str(tmp / "busta.pdf"))[0].render(scale=200 / 72).to_pil()
        testo = _ocr_immagine(immagine)
        assert "NETTO IN BUSTA" in testo.upper() and "1.632,00" in testo, testo[:300]
        incluso = "incluso nel programma" if "tesseract" in Path(percorso).parent.name.lower() else percorso
        return f"lingua {lingua}, {incluso}"

    def report_pdf():
        from .cli import analizza_documento
        from .report_pdf import genera_report_pdf

        docs = [(f.name, analizza_documento(f)[1]) for f in sorted(risorsa("esempi/confronto").glob("*.txt"))]
        out = genera_report_pdf(tmp / "report.pdf", docs, None, {})
        return f"{out.stat().st_size // 1024} KB"

    def interfaccia():
        import tkinter as tk

        from . import gui  # noqa: F401

        root = tk.Tk()
        root.withdraw()
        root.update()
        root.destroy()
        return f"Tk {tk.TkVersion}"

    def criteri_compass():
        from datetime import date

        from .criteri_compass import archivio_regole, motore

        motore.CARTELLA_REGOLE = None
        p = motore.Pratica(sesso="M", nascita=date(1975, 3, 15), assunzione=date(2010, 9, 1), netto=1800, tfr=25000,
                           rata=360, durata=120, decorrenza=date(2027, 1, 1), anzianita_contributiva_mesi=300,
                           dipendenti_azienda=200, oggi=date(2026, 11, 12))
        for prodotto, settore in motore.SETTORI:
            if settore != "Pensionato":
                p.prodotto, p.settore = prodotto, settore
                motore.verifica_pratica(p)
        p.prodotto, p.settore = "CQS", "Dipendente privato"
        esiti = {e.compagnia: e.livello for e in motore.verifica_pratica(p)[2]}
        assert esiti["HDI"] == "OK" and esiti["METLIFE"] == "KO", esiti
        scritti = archivio_regole.esporta(tmp / "condivisa", [v["regole"] for v in motore.SETTORI.values()])
        return f"{len(motore.SETTORI)} settori, {len(scritti)} regole esportabili"

    def assistente():
        from .assistente import ollama_http, rag, scarica  # noqa: F401

        pezzi = rag.dividi_in_pezzi("Testo di prova per l'assistente. " * 60)
        return f"moduli presenti, {len(pezzi)} pezzi di testo (Ollama non richiesto)"

    passo("Analisi documenti di esempio", esempi)
    passo("Confronto tra documenti", confronto)
    passo("Lettura PDF e controllo autenticità", pdf_e_autenticita)
    passo("Rendering PDF (pypdfium2, per l'OCR)", pdfium)
    passo("OCR di una busta paga scansionata (Tesseract)", ocr)
    passo("Creazione report PDF", report_pdf)
    passo("Interfaccia grafica (Tkinter)", interfaccia)
    passo("Criteri Compass (tutti i settori)", criteri_compass)
    passo("Assistente AI (moduli)", assistente)
    righe.append("ESITO: " + ("TUTTO OK" if not errori else f"{errori} ERRORI"))

    testo = "\n".join(righe)
    LOG.write_text(testo, encoding="utf-8")
    if sys.stdout is not None:  # nel .exe senza console stdout non esiste
        try:
            print(testo)
            print(f"(log: {LOG})")
        except Exception:
            pass
    return 0 if not errori else 1
