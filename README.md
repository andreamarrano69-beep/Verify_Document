# Verify Document

Programma Python **locale** (nessun dato inviato su internet) che legge e verifica:

| Documento | Cosa estrae | Cosa controlla |
|---|---|---|
| **Busta paga** | P.IVA azienda, CF dipendente, data assunzione, periodo, competenze, trattenute, netto, imponibili, contributi, IRPEF | P.IVA e CF validi (cifra di controllo), netto = competenze − trattenute ± arrotondamenti, aliquota INPS (9,19% / 9,49% / 5,84%), imponibile fiscale = previdenziale − contributi, IRPEF netta ≤ lorda, assunzione coerente con periodo ed età |
| **Modello Redditi PF (ex Unico)** | Quadri compilati, regime fiscale, redditi dei quadri, imponibile, imposte, ritenute, acconti, cedolare secca, addizionali | Regime (forfettario, semplificato, ordinario, professionista, dipendente), reddito **mensile** lordo e netto; **catena del quadro RN** (complessivo = somma dei quadri, imponibile = complessivo − deduzioni, imposta lorda = IRPEF a scaglioni dell'anno, netta = lorda − detrazioni, saldo = netta − ritenute − acconti); quadro RE (compensi − spese) e RG (ricavi − costi); cedolare 10/21/26%; addizionali entro i limiti; forfettario: soglia 85.000 €, coefficiente di redditività, aliquota 5%/15% |
| **Certificazione Unica (CU)** | Datore di lavoro (sostituto d'imposta), dipendente, anno, redditi, giorni lavorati, ritenute IRPEF, addizionali, imponibile e contributi INPS, data inizio rapporto | CF e P.IVA validi, giorni ≤ giorni dell'anno, ritenute IRPEF ≤ IRPEF lorda calcolata con gli scaglioni dell'anno, aliquota INPS, reddito ≈ imponibile INPS − contributi, reddito **mensile** lordo e netto |
| **Pensione** (cedolino INPS o di altre casse, certificato ObisM) | Pensionato, ente, categoria (VO, IO, SO, AS…), numero pensione, rata, lordo, IRPEF, addizionali, **cessione del quinto, prestiti, pignoramenti**, netto | CF valido ed età coerente con la categoria, netto = lordo − trattenute, IRPEF del mese entro il massimo possibile, prestazioni assistenziali (assegno sociale, invalidità civile) segnalate, importo mensile e annuo (13 mensilità) |
| **Documento d'identità** (CIE, carta, patente, passaporto, tessera sanitaria) | Cognome, nome, nascita, sesso, numero, rilascio, scadenza, CF | CF valido e coerente con cognome/nome/data/sesso, documento scaduto o in scadenza |

Per i **PDF** viene inoltre esaminato il file stesso alla ricerca di **segni di alterazione** (vedi sotto).

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

## Sintesi: regime e importo mensile in evidenza

Per ogni documento di reddito il programma mostra in alto, a caratteri grandi:

| Documento | Cosa evidenzia |
|---|---|
| Modello Redditi PF | **Regime fiscale** (forfettario, semplificato, ordinario, professionista, dipendente, **pensionato**…) e **reddito mensile lordo e netto** |
| CU | Tipo di reddito (lavoro dipendente / pensione) e reddito mensile lordo e netto |
| Cedolino pensione / ObisM | Tipo di pensione e rata mensile lorda e netta |
| Busta paga | Lordo e netto del mese |

Il netto mensile compare anche nell'elenco dei documenti, nella stampa da riga di comando e nel report esportato.

![Pensione](docs/pensione.png)

## Cessione del quinto, deleghe e pignoramenti

Su **buste paga** e **cedolini della pensione** il programma individua le trattenute per
cessione del quinto, delegazione di pagamento (prestito con delega) e pignoramento, e calcola
il **quinto cedibile** e quanto è **ancora disponibile** per un nuovo finanziamento:

| Controllo | Regola (DPR 180/1950) |
|---|---|
| Rata di cessione | al massimo 1/5 del netto (lordo − contributi − IRPEF − addizionali) |
| Cessione + delegazione | al massimo 2/5 |
| Cessione + pignoramento | al massimo metà del netto |
| Confronto tra mesi | la rata è fissa: rate diverse, cessioni iniziate o estinte vengono segnalate |

Una rata oltre i limiti di legge è segnalata come **errore** (documento da verificare).
Per le pensioni la quota cedibile deve inoltre lasciare almeno il trattamento minimo INPS.

![Cessione del quinto](docs/cessione.png)

## Controllo autenticità dei PDF

Oltre a verificare che i calcoli tornino, il programma esamina il file PDF e assegna un
**indice di rischio di alterazione** (BASSO / MEDIO / ALTO):

| Indizio | Punti |
|---|---|
| Creato o salvato con un editor PDF online (iLovePDF, Smallpdf, Sejda, Canva…) | 3 |
| Importo scritto con un carattere diverso dal resto del documento | 3 |
| Testo scritto sopra altro testo (es. «6» coperto da «9») | 3 |
| Annotazioni/caselle di testo aggiunte sopra la pagina | 3 |
| File creato prima del periodo a cui si riferisce | 3 |
| Programma di modifica PDF (Acrobat Pro, Foxit, PDF-XChange…) o Word/LibreOffice | 2 |
| Data di modifica diversa dalla creazione / salvataggi successivi | 2 |
| Stampante virtuale PDF, metadati assenti, campi compilabili, solo scansione | 1 |
| Importo isolato in grassetto/corsivo (spesso normale per il netto) | 1 |

0 punti = basso, 1–2 = medio, 3 o più = alto (chiedere il documento originale).

![Controllo autenticità](docs/autenticita.png)

> Nessun controllo automatico può **certificare** l'originalità: lo strumento segnala anomalie
> che un operatore deve valutare. Un indice basso non garantisce che il documento sia autentico.

## Confronto tra documenti dello stesso cliente

Caricando più documenti (es. 3 buste paga consecutive + carta d'identità + Modello Redditi) e premendo
**⇄ Confronta documenti** (o con `--confronta` da riga di comando) il programma verifica:

| Controllo | Cosa scopre |
|---|---|
| Stesso codice fiscale su tutti i documenti | Documenti di persone diverse mescolati |
| Stessa P.IVA e stessa data di assunzione | Busta paga presa da un'altra azienda o alterata |
| **Progressivi annui**: progressivo del mese = progressivo precedente + imponibile del mese | Busta gonfiata ricalcolando tutto in modo coerente (da sola sembra regolare!) |
| Arrotondamento "precedente" = arrotondamento "attuale" del mese prima | Netto ritoccato |
| Rapporto netto/lordo e netto simili agli altri mesi | Netto alterato senza ricalcolare il lordo |
| Mesi doppi (con netto diverso) o mancanti | Due versioni dello stesso cedolino |
| Buste paga ↔ **CU** dello stesso anno: reddito e IRPEF = progressivi di dicembre, stesso datore e data di assunzione | CU o buste paga alterate |
| **CU ↔ Modello Redditi**: reddito da lavoro dipendente e pensione dichiarato = somma delle CU | Reddito dichiarato gonfiato o CU mancante |
| **Pensione**: stessa categoria per lo stesso numero di pensione, rata lorda costante nell'anno, netto stabile | Cedolino alterato |
| **Pensione ↔ CU**: reddito di pensione della CU = rata lorda × 13 | CU o cedolini non compatibili |
| Buste paga ↔ reddito da lavoro dipendente del Modello Redditi dello stesso anno | Redditi dichiarati diversi da quelli delle buste |
| Più anni di Modello Redditi | Cambi di regime, variazioni di reddito molto forti |

![Confronto tra documenti](docs/confronto.png)

Prova con i documenti di esempio:

```bash
python -m verify_document esempi/confronto/*.txt --confronta
python -m verify_document esempi/pensionato/*.txt --confronta
```

## Report PDF

Il pulsante **📄 Report PDF** (o `--pdf report.pdf` da riga di comando) crea un PDF da consegnare
al cliente o alla finanziaria con:

1. intestazione con **logo e dati dello studio** (da **⚙ Impostazioni**, salvati una volta sola)
2. cliente (nome e codice fiscale), data, operatore
3. **esito complessivo** e rischio di alterazione dei file
4. **sintesi dei redditi**: per ogni documento regime/tipo di reddito e importo mensile lordo e netto
5. **confronto tra i documenti** e andamento mese per mese (se i documenti sono più di uno)
6. dettaglio di ogni documento con dati e controlli
7. nota sui limiti dello strumento, spazio per la firma, numeri di pagina

Esempio completo: [docs/report_esempio.pdf](docs/report_esempio.pdf)

![Report PDF](docs/report_pdf.png)

```bash
python -m verify_document esempi/pensionato/*.txt --pdf report.pdf
```

Le impostazioni dello studio sono salvate in `~/.verify_document/impostazioni.json`
(Windows: `C:\Users\<nome>\.verify_document\impostazioni.json`).

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
- **📄 Report PDF** e **💾 Esporta ▾** (PDF, .txt, .json); **⚙ Impostazioni** per logo e dati dello studio
- **Rianalizza** dopo aver cambiato il tipo di documento
- per trascinare i file nella finestra: `pip install tkinterdnd2`
- si apre a tutto schermo; **F11** schermo intero senza bordi, **Esc** per tornare indietro
- **⏻ Esci** (o **Ctrl+Q**, o la X della finestra) chiede conferma se ci sono documenti analizzati

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
pip install -r requirements-dev.txt     # pypdf, per generare i PDF falsificati di prova
python -m unittest discover -s tests -v
```

## Struttura

```
verify_document/
  estrazione.py       testo da PDF / OCR
  validators.py       codice fiscale, partita IVA, importi, date
  busta_paga.py       analisi cedolino
  modello_redditi.py  analisi Modello Redditi PF
  pensione.py         analisi cedolino pensione e certificato ObisM
  impegni.py          cessione del quinto, deleghe, pignoramenti, quinto cedibile
  report_pdf.py       report PDF con logo e dati dello studio
  impostazioni.py     dati dello studio (impostazioni.json)
  cu.py               analisi Certificazione Unica (scaglioni IRPEF per anno in SCAGLIONI_IRPEF)
  anagrafica.py       analisi documenti d'identità
  autenticita.py      esame del file PDF (segni di alterazione)
  confronto.py        confronto tra più documenti dello stesso cliente
  report.py           esiti dei controlli
  cli.py              riga di comando
  gui.py              interfaccia grafica (Tkinter)
esempi/               documenti FITTIZI di prova (esempi/confronto: 3 buste + carta d'identità;
                      esempi/pensionato: cedolini, ObisM, CU INPS e Modello Redditi di un pensionato)
tests/                test automatici
```

## Limiti attuali (da sapere prima di vendere)

- Ogni software paghe (Zucchetti, TeamSystem, INAZ, ADP…) impagina il cedolino in modo diverso:
  le diciture cercate sono nelle liste `ETICHETTE` dei moduli e vanno tarate su **documenti reali anonimizzati**.
- La numerazione dei righi del Modello Redditi e dei punti della CU può cambiare: la ricerca avviene per descrizione.
- Gli scaglioni IRPEF sono in `cu.py` (`SCAGLIONI_IRPEF`): vanno aggiornati a ogni legge di bilancio.
- Il programma segnala incongruenze, **non sostituisce** la verifica di un professionista.

> ⚠ Non salvare mai documenti reali dei clienti nel repository (le cartelle `documenti/` e `clienti/` sono già escluse in `.gitignore`).
