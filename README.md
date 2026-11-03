# Verify Document

Programma Python **locale** (nessun dato inviato su internet) che legge e verifica:

| Documento | Cosa estrae | Cosa controlla |
|---|---|---|
| **Busta paga** | P.IVA azienda, CF dipendente, data assunzione, periodo, competenze, trattenute, netto, imponibili, contributi, IRPEF | P.IVA e CF validi (cifra di controllo), netto = competenze − trattenute ± arrotondamenti, aliquota INPS (9,19% / 9,49% / 5,84%), imponibile fiscale = previdenziale − contributi, IRPEF netta ≤ lorda, assunzione coerente con periodo ed età |
| **Modello Redditi PF (ex Unico)** | Quadri compilati, regime fiscale, reddito, imposte | Regime (forfettario, semplificato, ordinario, professionista, dipendente), reddito **mensile** lordo e netto; per il forfettario: soglia 85.000 €, coefficiente di redditività, aliquota 5%/15% |
| **Documento d'identità** (CIE, carta, patente, passaporto, tessera sanitaria) | Cognome, nome, nascita, sesso, numero, rilascio, scadenza, CF | CF valido e coerente con cognome/nome/data/sesso, documento scaduto o in scadenza |

Formati: PDF con testo (generati dai software paghe/Entratel), PDF scansionati e immagini (con OCR opzionale), file `.txt`.

## Installazione

Linux / macOS:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Windows (PowerShell / terminale di VS Code):

```powershell
python -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

OCR (solo per scansioni/foto): installare [Tesseract](https://github.com/UB-Mannheim/tesseract/wiki) con la lingua italiana, poi `pip install pytesseract Pillow`.

## Interfaccia grafica

![Interfaccia grafica](docs/interfaccia.png)

Doppio clic su **`Avvia Verify Document.bat`** (Windows), oppure dal terminale:

```powershell
python -m verify_document.gui
```

- **Apri documenti…**: seleziona uno o più PDF, immagini o .txt (analizzati in parallelo)
- in alto il **riepilogo**: netto/CF/P.IVA/assunzione per la busta paga, regime e reddito mensile per il Modello Redditi
- schede **Controlli** (✔ verde, ⚠ giallo, ✘ rosso; doppio clic per leggere il dettaglio completo),
  **Dati estratti** e **Testo letto** (per capire cosa non è stato trovato)
- **Esporta report…** in .txt o .json; **Rianalizza** dopo aver cambiato il tipo di documento
- per trascinare i file nella finestra: `pip install tkinterdnd2`

## Uso da riga di comando

```bash
python -m verify_document esempi/busta_paga_esempio.txt
python -m verify_document documenti/cedolino.pdf --tipo busta
python -m verify_document documenti/*.pdf --json > report.json
python -m verify_document documenti/cedolino.pdf --testo     # mostra il testo letto (per tarare le etichette)
```

Codice di uscita: `0` tutto ok, `1` almeno un controllo in ERRORE, `2` file non leggibile.

## Test

```bash
python -m unittest discover -s tests -v
```

## Struttura

```
verify_document/
  estrazione.py       testo da PDF / OCR
  validators.py       codice fiscale, partita IVA, importi, date
  busta_paga.py       analisi cedolino
  modello_redditi.py  analisi Modello Redditi PF
  anagrafica.py       analisi documenti d'identità
  report.py           esiti dei controlli
  cli.py              riga di comando
  gui.py              interfaccia grafica (Tkinter)
esempi/               documenti FITTIZI di prova
tests/                test automatici
```

## Limiti attuali (da sapere prima di vendere)

- Ogni software paghe (Zucchetti, TeamSystem, INAZ, ADP…) impagina il cedolino in modo diverso:
  le diciture cercate sono nelle liste `ETICHETTE` dei moduli e vanno tarate su **documenti reali anonimizzati**.
- La numerazione dei righi del Modello Redditi cambia ogni anno: la ricerca avviene per descrizione.
- Il programma segnala incongruenze, **non sostituisce** la verifica di un professionista.

> ⚠ Non salvare mai documenti reali dei clienti nel repository (le cartelle `documenti/` e `clienti/` sono già escluse in `.gitignore`).
