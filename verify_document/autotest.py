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

    passo("Analisi documenti di esempio", esempi)
    passo("Confronto tra documenti", confronto)
    passo("Lettura PDF e controllo autenticità", pdf_e_autenticita)
    passo("Rendering PDF (pypdfium2, per l'OCR)", pdfium)
    passo("Creazione report PDF", report_pdf)
    passo("Interfaccia grafica (Tkinter)", interfaccia)
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
