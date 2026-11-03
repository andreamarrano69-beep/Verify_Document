"""Punto di avvio del programma (usato anche per creare il .exe con PyInstaller).

    python avvia_gui.py                 apre l'interfaccia grafica
    python avvia_gui.py file1.pdf ...   apre l'interfaccia con questi documenti
    python avvia_gui.py --autotest      verifica che il programma contenga tutto il necessario
"""

import sys

if __name__ == "__main__":
    if "--autotest" in sys.argv:
        from verify_document.autotest import esegui

        sys.exit(esegui())

    from verify_document.gui import main

    main([a for a in sys.argv[1:] if not a.startswith("--")])
