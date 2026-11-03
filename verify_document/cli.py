"""Interfaccia a riga di comando.

Esempi:
    python -m verify_document esempi/busta_paga_esempio.txt
    python -m verify_document documenti/*.pdf --tipo busta --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__, anagrafica, busta_paga, modello_redditi
from .estrazione import ErroreEstrazione, estrai_testo
from .report import Report, report_testuale

ANALIZZATORI = {
    "busta": busta_paga,
    "redditi": modello_redditi,
    "anagrafica": anagrafica,
}


def riconosci_tipo(testo: str) -> str:
    punteggi = {nome: mod.riconosci(testo) for nome, mod in ANALIZZATORI.items()}
    migliore = max(punteggi, key=punteggi.get)
    if punteggi[migliore] == 0:
        raise ValueError("Tipo di documento non riconosciuto: usa --tipo busta|redditi|anagrafica")
    return migliore


def analizza_testo(testo: str, tipo: str = "auto") -> Report:
    if tipo == "auto":
        tipo = riconosci_tipo(testo)
    return ANALIZZATORI[tipo].analizza(testo)


def analizza_documento(
    percorso: str | Path, tipo: str = "auto", usa_ocr: bool = True, autenticita: bool = True
) -> tuple[str, Report]:
    """Estrae il testo, analizza i dati e, per i PDF, esamina il file in cerca di alterazioni."""
    testo = estrai_testo(percorso, usa_ocr=usa_ocr)
    report = analizza_testo(testo, tipo)
    if autenticita and Path(percorso).suffix.lower() == ".pdf":
        from .autenticita import aggiungi_al_report

        aggiungi_al_report(report, percorso)
    return testo, report


def analizza_file(percorso: str | Path, tipo: str = "auto", usa_ocr: bool = True) -> Report:
    return analizza_documento(percorso, tipo, usa_ocr)[1]


def stampa_report(nome_file: str, r: Report) -> None:
    print(report_testuale(nome_file, r))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="verify_document",
        description="Verifica buste paga, Modello Redditi PF e documenti d'identità (in locale).",
    )
    parser.add_argument("file", nargs="+", help="PDF, immagini (JPG/PNG) o .txt")
    parser.add_argument("--tipo", choices=["auto", *ANALIZZATORI], default="auto")
    parser.add_argument("--json", action="store_true", help="output in formato JSON")
    parser.add_argument("--no-ocr", action="store_true", help="non usare l'OCR")
    parser.add_argument("--testo", action="store_true", help="mostra il testo estratto (debug)")
    parser.add_argument("--no-autenticita", action="store_true",
                        help="non esaminare il file PDF in cerca di alterazioni")
    parser.add_argument("--confronta", action="store_true",
                        help="confronta tra loro i documenti (stesso cliente, buste paga consecutive, ...)")
    parser.add_argument("--version", action="version", version=__version__)
    args = parser.parse_args(argv)

    codice_uscita = 0
    risultati = []
    analizzati = []
    for f in args.file:
        try:
            testo, r = analizza_documento(f, args.tipo, not args.no_ocr, not args.no_autenticita)
            if args.testo:
                print(testo)
        except (ErroreEstrazione, ValueError) as e:
            print(f"[{f}] ERRORE: {e}", file=sys.stderr)
            codice_uscita = 2
            continue
        if r.esito_globale.value == "ERRORE":
            codice_uscita = max(codice_uscita, 1)
        analizzati.append((Path(f).name, r))
        if args.json:
            risultati.append({"file": str(f), **r.to_dict()})
        else:
            stampa_report(str(f), r)
    if args.confronta:
        from .confronto import confronta, confronto_testuale

        c = confronta(analizzati)
        if c.report.esito_globale.value == "ERRORE":
            codice_uscita = max(codice_uscita, 1)
        if args.json:
            risultati = {"documenti": risultati, "confronto": c.report.to_dict()}
        else:
            print(confronto_testuale(c))
    if args.json:
        print(json.dumps(risultati, ensure_ascii=False, indent=2))
    return codice_uscita
