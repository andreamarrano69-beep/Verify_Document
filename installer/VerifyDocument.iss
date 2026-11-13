; =====================================================================================================
;  Setup di Verify Document per i PC dell'ufficio  ->  VerifyDocument-Setup-<versione>.exe
;
;  Si crea con Inno Setup 6 (https://jrsoftware.org/isinfo.php) dopo aver creato il programma:
;     crea_exe.bat                                         (crea dist\VerifyDocument\)
;     "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" /DVersione=0.13.0 installer\VerifyDocument.iss
;  oppure in automatico su GitHub (Actions → "Crea exe Windows" → Artifacts).
;
;  Durante l'installazione chiede:
;   - la CARTELLA CONDIVISA dell'ufficio (es. \\SERVER\Condivisa\VerifyDocument): archivio dei clienti,
;     regole Compass e documenti per l'assistente AI; viene scritta in config_ufficio.json accanto al programma
;   - se installare anche OLLAMA (assistente AI, facoltativo): viene scaricato dal sito ufficiale
;     https://ollama.com e installato; i modelli si scaricano poi dal programma (circa 1-2 GB)
;
;  Installazione senza domande su più PC (dalla cartella dove si trova il setup):
;     VerifyDocument-Setup-0.13.0.exe /SILENT /CARTELLA="\\SERVER\Condivisa\VerifyDocument" /MODELLO=qwen2.5:1.5b
;  aggiungere  /TASKS="ollama"  per installare anche l'assistente AI.
; =====================================================================================================

#ifndef Versione
  #define Versione "0.0.0"
#endif

[Setup]
AppId={{6F0B8C52-3E7A-4C1B-9F7E-VERIFYDOC001}
AppName=Verify Document
AppVersion={#Versione}
AppPublisher=Verify Document
DefaultDirName={autopf}\Verify Document
DefaultGroupName=Verify Document
UninstallDisplayIcon={app}\VerifyDocument.exe
OutputDir=..\dist
OutputBaseFilename=VerifyDocument-Setup-{#Versione}
SetupIconFile=..\assets\icona.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; installazione per l'utente (come Ollama): non servono i permessi di amministratore;
; chi li ha può scegliere "per tutti gli utenti"
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
DisableProgramGroupPage=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "italiano"; MessagesFile: "compiler:Languages\Italian.isl"

[Tasks]
Name: "desktop"; Description: "Crea un'icona sul desktop"; GroupDescription: "Icone:"
Name: "ollama"; Description: "Installa anche l'assistente AI (Ollama, circa 1 GB + 1-2 GB di modelli; consigliati 8 GB di RAM)"; GroupDescription: "Facoltativo:"; Flags: unchecked

[Files]
Source: "..\dist\VerifyDocument\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Verify Document"; Filename: "{app}\VerifyDocument.exe"
Name: "{autodesktop}\Verify Document"; Filename: "{app}\VerifyDocument.exe"; Tasks: desktop

[Run]
Filename: "{tmp}\OllamaSetup.exe"; Parameters: "/VERYSILENT /NORESTART /SUPPRESSMSGBOXES"; StatusMsg: "Installazione di Ollama (assistente AI)..."; Tasks: ollama; Check: OllamaScaricato; Flags: waituntilterminated
Filename: "{app}\VerifyDocument.exe"; Description: "Avvia Verify Document"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: files; Name: "{app}\config_ufficio.json"

[Code]
var
  PaginaUfficio: TInputQueryWizardPage;
  PaginaDownload: TDownloadWizardPage;
  ScaricatoOllama: Boolean;

function OllamaScaricato(): Boolean;
begin
  Result := ScaricatoOllama;
end;

{ testo JSON: le barre rovesciate (\\SERVER\...) e le virgolette vanno raddoppiate/protette }
function JsonTesto(const S: String): String;
var
  R: String;
begin
  R := S;
  StringChangeEx(R, '\', '\\', True);
  StringChangeEx(R, '"', '\"', True);
  Result := '"' + R + '"';
end;

procedure InitializeWizard();
begin
  PaginaUfficio := CreateInputQueryPage(wpSelectTasks,
    'Cartella condivisa dell''ufficio',
    'Dove si trovano l''archivio dei clienti, le regole Compass e i documenti per l''assistente AI?',
    'Indica la cartella condivisa del server che tutti i PC dell''ufficio vedono, ad esempio ' +
    '\\SERVER\Condivisa\VerifyDocument  (lascia vuoto per lavorare solo su questo PC).' + #13#10 +
    'Si può cambiare in seguito da Impostazioni → Ufficio e assistente AI.');
  PaginaUfficio.Add('Cartella condivisa:', False);
  PaginaUfficio.Add('Modello AI (8 GB di RAM: qwen2.5:1.5b · 16 GB: qwen2.5:3b):', False);
  PaginaUfficio.Values[0] := ExpandConstant('{param:CARTELLA|}');
  PaginaUfficio.Values[1] := ExpandConstant('{param:MODELLO|qwen2.5:1.5b}');

  PaginaDownload := CreateDownloadPage('Assistente AI', 'Scarico Ollama dal sito ufficiale...', nil);
  ScaricatoOllama := False;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if (CurPageID = wpReady) and WizardIsTaskSelected('ollama') then
  begin
    PaginaDownload.Clear;
    PaginaDownload.Add('https://ollama.com/download/OllamaSetup.exe', 'OllamaSetup.exe', '');
    PaginaDownload.Show;
    try
      try
        PaginaDownload.Download;
        ScaricatoOllama := True;
      except
        ScaricatoOllama := False;
        if not WizardSilent then
          MsgBox('Non sono riuscito a scaricare Ollama (' + GetExceptionMessage + ').' + #13#10 +
                 'Verify Document viene installato lo stesso: l''assistente AI si può aggiungere dopo ' +
                 'installando Ollama da https://ollama.com', mbInformation, MB_OK);
      end;
    finally
      PaginaDownload.Hide;
    end;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  Json: String;
begin
  if CurStep = ssPostInstall then
  begin
    { impostazioni dell'ufficio lette dal programma all'avvio (config_ufficio.json) }
    Json := '{' + #13#10 +
            '  "cartella_condivisa": ' + JsonTesto(Trim(PaginaUfficio.Values[0])) + ',' + #13#10 +
            '  "modello_ai": ' + JsonTesto(Trim(PaginaUfficio.Values[1])) + #13#10 +
            '}' + #13#10;
    SaveStringToFile(ExpandConstant('{app}\config_ufficio.json'), Json, False);
    if (Trim(PaginaUfficio.Values[0]) <> '') and (not DirExists(Trim(PaginaUfficio.Values[0]))) and
       (not WizardSilent) then
      MsgBox('Attenzione: la cartella condivisa' + #13#10 + Trim(PaginaUfficio.Values[0]) + #13#10 +
             'non è raggiungibile adesso (server spento o rete assente?). Il programma la userà appena ' +
             'sarà disponibile.', mbInformation, MB_OK);
  end;
end;
