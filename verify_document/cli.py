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


def analizza_file(percorso: str | Path, tipo: str = "auto", usa_ocr: bool = True) -> Report:
    return analizza_testo(estrai_testo(percorso, usa_ocr=usa_ocr), tipo)


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
    parser.add_argument("--version", action="version", version=__version__)
    args = parser.parse_args(argv)

    codice_uscita = 0
    risultati = []
    for f in args.file:
        try:
            testo = estrai_testo(f, usa_ocr=not args.no_ocr)
            if args.testo:
                print(testo)
            r = analizza_testo(testo, args.tipo)
        except (ErroreEstrazione, ValueError) as e:
            print(f"[{f}] ERRORE: {e}", file=sys.stderr)
            codice_uscita = 2
            continue
        if r.esito_globale.value == "ERRORE":
            codice_uscita = max(codice_uscita, 1)
        if args.json:
            risultati.append({"file": str(f), **r.to_dict()})
        else:
            stampa_report(str(f), r)
    if args.json:
        print(json.dumps(risultati, ensure_ascii=False, indent=2))
    return codice_uscita
