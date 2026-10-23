; Inno Setup script for the vpngo Windows installer (vpngo-<version>-windows-setup.exe).
;
; tools/build_release.py builds the Windows archive; the release workflow unpacks it and runs:
;
;   iscc /DAppVersion=1.2.3 /DSourceDir=<unpacked vpngo-1.2.3-windows> /O<output> packaging\windows-setup.iss
;
; The installer puts the same files as install-windows.ps1 in %LOCALAPPDATA%\vpngo\app, runs
; windows\install.ps1 to create the vpngo command, and needs no administrator rights. The
; optional ProxiFyre task runs windows\install-backend.ps1, which asks for administrator
; permission itself. Settings and profiles live outside the app folder and are kept.
;
; The wizard always asks whether to install the graphical interface (VPNGo, the default) or only
; the command line. The interface comes from `vpngo --install-gui` (its own release plus PySide6,
; about 250 MB) and gets a Start menu shortcut.
;
; Silent installs:
;
;   vpngo-1.2.3-windows-setup.exe --silent              vpngo and the interface
;   vpngo-1.2.3-windows-setup.exe --silent --cli-only   only vpngo (the interface's own engine)
;
; --silent is the same as /VERYSILENT /SUPPRESSMSGBOXES /NORESTART. A silent install skips the
; ProxiFyre task unless /TASKS or /MERGETASKS asks for it, so it never shows a UAC prompt by
; surprise. Exit code 0 means installed; besides Inno Setup's own codes, 10 means the vpngo
; command could not be created, 11 means the ProxiFyre setup failed and 12 means the interface
; could not be installed (vpngo is installed in both cases). The setup refuses to run (exit code 1)
; while vpngo's MSI package is installed.

#ifndef AppVersion
  #error Pass /DAppVersion=<version>
#endif
#ifndef SourceDir
  #error Pass /DSourceDir=<unpacked Windows release folder>
#endif

[Setup]
AppId={{6B1E5C7A-3F2D-4B8E-9A61-2C0D7E4F9B13}
AppName=vpngo
AppVersion={#AppVersion}
AppVerName=vpngo {#AppVersion}
AppPublisher=GustavoHSCruz
AppPublisherURL=https://github.com/GustavoHSCruz/VPNGo
AppSupportURL=https://github.com/GustavoHSCruz/VPNGo/issues
AppUpdatesURL=https://github.com/GustavoHSCruz/VPNGo/releases/latest
; vpngo update and the interface expect exactly <prefix>\app, so the folder is fixed.
DefaultDirName={localappdata}\vpngo\app
DisableDirPage=yes
DisableProgramGroupPage=yes
DisableReadyPage=yes
PrivilegesRequired=lowest
; vpngo update swaps the app folder, so the uninstaller lives beside it.
UninstallFilesDir={localappdata}\vpngo\uninstall
UninstallDisplayName=vpngo
UninstallDisplayIcon={localappdata}\vpngo\uninstall\vpngo.ico
SetupIconFile=vpngo.ico
ChangesEnvironment=yes
LicenseFile={#SourceDir}\LICENSE
OutputBaseFilename=vpngo-{#AppVersion}-windows-setup
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
; Pick the language from Windows' display language. The language dialog would also open before
; any [Code] runs, so --silent could not skip it.
ShowLanguageDialog=no
SetupLogging=yes

[Languages]
Name: "en"; MessagesFile: "compiler:Default.isl"
Name: "ptbr"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[CustomMessages]
en.ProxiFyreTask=Install ProxiFyre and Windows Packet Filter (needed for app routing; asks for administrator permission)
ptbr.ProxiFyreTask=Instalar ProxiFyre e Windows Packet Filter (necessários para rotear apps; pede permissão de administrador)
en.CreatingCommand=Creating the vpngo command...
ptbr.CreatingCommand=Criando o comando vpngo...
en.InstallingProxiFyre=Installing ProxiFyre and Windows Packet Filter...
ptbr.InstallingProxiFyre=Instalando ProxiFyre e Windows Packet Filter...
en.CommandFailed=The vpngo command could not be created (exit %1). Run windows\install.ps1 from %2 to try again.
ptbr.CommandFailed=Não foi possível criar o comando vpngo (código %1). Rode windows\install.ps1 em %2 para tentar de novo.
en.ProxiFyreFailed=ProxiFyre setup failed or needs a restart (exit %1). vpngo is installed; run windows\install-backend.ps1 from %2 later.
ptbr.ProxiFyreFailed=A instalação do ProxiFyre falhou ou precisa reiniciar (código %1). O vpngo está instalado; rode windows\install-backend.ps1 em %2 depois.
en.PythonMissing=vpngo is installed, but Python 3 was not found. Install it (step 1 of the Windows guide), then open a new terminal and run vpngo version.
en.ModeTitle=How do you want to use vpngo?
ptbr.ModeTitle=Como você quer usar o vpngo?
en.ModeSubtitle=The graphical interface also includes the vpngo command.
ptbr.ModeSubtitle=A interface gráfica também inclui o comando vpngo.
en.ModePrompt=Choose what to install, then click Next.
ptbr.ModePrompt=Escolha o que instalar e clique em Avançar.
en.ModeGui=VPNGo app with graphical interface (recommended; downloads about 250 MB)
ptbr.ModeGui=Aplicativo VPNGo com interface gráfica (recomendado; baixa cerca de 250 MB)
en.ModeCli=Command line only (the vpngo command in the terminal)
ptbr.ModeCli=Somente linha de comando (o comando vpngo no terminal)
en.InstallingGui=Installing the graphical interface (downloads about 250 MB; this can take a few minutes)...
ptbr.InstallingGui=Instalando a interface gráfica (baixa cerca de 250 MB; pode levar alguns minutos)...
en.GuiFailed=The graphical interface could not be installed (exit %1). vpngo is installed; run vpngo --install-gui later to try again.
ptbr.GuiFailed=Não foi possível instalar a interface gráfica (código %1). O vpngo está instalado; rode vpngo --install-gui depois para tentar de novo.
en.GuiNeedsPython=The graphical interface needs Python 3, which was not found. vpngo is installed; install Python (step 1 of the Windows guide), then run vpngo --install-gui.
ptbr.GuiNeedsPython=A interface gráfica precisa do Python 3, que não foi encontrado. O vpngo está instalado; instale o Python (passo 1 do guia do Windows) e rode vpngo --install-gui.
en.MsiInstalled=vpngo is already installed by its MSI package. Uninstall it in Settings > Apps first, or keep using the MSI.
ptbr.MsiInstalled=O vpngo já está instalado pelo pacote MSI. Desinstale-o em Configurações > Aplicativos primeiro, ou continue usando o MSI.
en.LaunchGui=Open VPNGo
ptbr.LaunchGui=Abrir o VPNGo
ptbr.PythonMissing=O vpngo está instalado, mas o Python 3 não foi encontrado. Instale-o (passo 1 do guia do Windows), abra um terminal novo e rode vpngo version.

[Tasks]
Name: "proxifyre"; Description: "{cm:ProxiFyreTask}"

[InstallDelete]
; Files removed from a newer release must not linger after an upgrade.
Type: filesandordirs; Name: "{app}\shared"
Type: filesandordirs; Name: "{app}\windows"
Type: filesandordirs; Name: "{app}\docs"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "vpngo.ico"; DestDir: "{localappdata}\vpngo\uninstall"; Flags: ignoreversion

[Run]
Filename: "{localappdata}\vpngo-gui\venv\Scripts\pythonw.exe"; Parameters: """{localappdata}\vpngo-gui\app\run.py"""; \
  Description: "{cm:LaunchGui}"; Flags: postinstall nowait skipifsilent; Check: GuiInstalled

[UninstallDelete]
; Python leaves __pycache__ folders behind; the app folder holds no settings.
Type: filesandordirs; Name: "{app}"

[Code]
const
  ExitCommandFailed = 10;
  ExitProxiFyreFailed = 11;
  ExitGuiFailed = 12;

var
  CustomExitCode: Integer;
  ModePage: TInputOptionWizardPage;
  GuiDone: Boolean;

procedure ExitProcess(ExitCode: Cardinal);
  external 'ExitProcess@kernel32.dll stdcall';

function HasParam(const Name: String): Boolean;
var
  I: Integer;
begin
  Result := False;
  for I := 1 to ParamCount do
    if CompareText(ParamStr(I), Name) = 0 then
      Result := True;
end;

function ParamStartsWith(const Prefix: String): Boolean;
var
  I: Integer;
begin
  Result := False;
  for I := 1 to ParamCount do
    if CompareText(Copy(ParamStr(I), 1, Length(Prefix)), Prefix) = 0 then
      Result := True;
end;

function InitializeSetup(): Boolean;
var
  I, Code: Integer;
  Param, Params, ChildLog: String;
  Lines: TArrayOfString;
begin
  // Inno Setup only knows /VERYSILENT, so --silent starts this installer again with it and
  // returns that run's exit code.
  if HasParam('--silent') then begin
    Params := '/VERYSILENT /SUPPRESSMSGBOXES /NORESTART';
    ChildLog := '';
    for I := 1 to ParamCount do begin
      Param := ParamStr(I);
      // /SL5= is the loader's handshake with this process; passing it on hangs the new run.
      if (CompareText(Param, '--silent') = 0) or (CompareText(Copy(Param, 1, 5), '/SL5=') = 0) then
        continue;
      // This run already holds the /LOG= file, so the new run logs elsewhere and its lines
      // are copied here.
      if CompareText(Copy(Param, 1, 5), '/LOG=') = 0 then begin
        ChildLog := ExpandConstant('{tmp}\silent.log');
        Param := '/LOG=' + ChildLog;
      end;
      Params := Params + ' ' + AddQuotes(Param);
    end;
    // Setup's own process may not open or start {srcexe} (access denied), so cmd starts it;
    // cmd returns the new run's exit code.
    Log('--silent: running Setup again with ' + Params);
    if not Exec(ExpandConstant('{cmd}'), '/C "' + AddQuotes(ExpandConstant('{srcexe}')) + ' ' + Params + '"',
                '', SW_HIDE, ewWaitUntilTerminated, Code) then begin
      Log('--silent: could not start Setup again: ' + SysErrorMessage(Code));
      Code := 1;
    end;
    if (ChildLog <> '') and LoadStringsFromFile(ChildLog, Lines) then
      for I := 0 to GetArrayLength(Lines) - 1 do
        Log('| ' + Lines[I]);
    Log(Format('--silent: exit code %d', [Code]));
    DelTree(ExpandConstant('{tmp}'), True, True, True);
    ExitProcess(Code);
  end;
  // One installer at a time: the MSI also adds the vpngo command and the VPNGo shortcut.
  // Checked after the --silent hand-off, so a silent run suppresses the message.
  if RegValueExists(HKCU, 'Software\vpngo\msi', 'path') then begin
    SuppressibleMsgBox(CustomMessage('MsiInstalled'), mbError, MB_OK, IDOK);
    Result := False;
    exit;
  end;
  Result := True;
end;

procedure InitializeWizard();
begin
  ModePage := CreateInputOptionPage(wpLicense, CustomMessage('ModeTitle'), CustomMessage('ModeSubtitle'),
    CustomMessage('ModePrompt'), True, False);
  ModePage.Add(CustomMessage('ModeGui'));
  ModePage.Add(CustomMessage('ModeCli'));
  if GetPreviousData('Mode', 'gui') = 'cli' then
    ModePage.SelectedValueIndex := 1
  else
    ModePage.SelectedValueIndex := 0;
end;

function GuiWanted(): Boolean;
begin
  if WizardSilent() then
    Result := not HasParam('--cli-only')
  else
    Result := ModePage.SelectedValueIndex = 0;
end;

procedure RegisterPreviousData(PreviousDataKey: Integer);
begin
  if GuiWanted() then
    SetPreviousData(PreviousDataKey, 'Mode', 'gui')
  else
    SetPreviousData(PreviousDataKey, 'Mode', 'cli');
end;

function GuiInstalled(): Boolean;
begin
  Result := GuiDone;
end;

function GuiRoot(): String;
begin
  // The same folder as vpngo --install-gui (shared\gui_install.py).
  Result := ExpandConstant('{localappdata}\vpngo-gui');
end;

function PowerShell(const Script, Arguments: String; var Code: Integer): Boolean;
begin
  Result := Exec(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'),
    '-NoProfile -ExecutionPolicy Bypass -File ' + AddQuotes(ExpandConstant('{app}\windows\') + Script) + Arguments,
    ExpandConstant('{app}'), SW_HIDE, ewWaitUntilTerminated, Code) and (Code = 0);
end;

function PythonWorks(): Boolean;
var
  Code: Integer;
  Python: String;
begin
  Python := GetEnv('VPNGO_PYTHON');
  if Python = '' then
    Python := 'python';
  // Through cmd so PATH is searched the same way vpngo.ps1 does.
  Result := Exec(ExpandConstant('{cmd}'),
    '/C "' + AddQuotes(Python) + ' ' + AddQuotes(ExpandConstant('{app}\shared\commands.py')) + ' version"',
    ExpandConstant('{app}'), SW_HIDE, ewWaitUntilTerminated, Code) and (Code = 0);
end;

function ProxiFyreRequested(): Boolean;
begin
  // A silent install never asks for administrator permission unless the caller chose the task.
  Result := WizardIsTaskSelected('proxifyre') and
    (not WizardSilent() or ParamStartsWith('/TASKS=') or ParamStartsWith('/MERGETASKS='));
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  Code: Integer;
begin
  if CurStep <> ssPostInstall then
    exit;
  WizardForm.StatusLabel.Caption := CustomMessage('CreatingCommand');
  if not PowerShell('install.ps1', '', Code) then begin
    CustomExitCode := ExitCommandFailed;
    Log(Format('windows\install.ps1 failed with exit code %d', [Code]));
    SuppressibleMsgBox(FmtMessage(CustomMessage('CommandFailed'), [IntToStr(Code), ExpandConstant('{app}')]),
      mbError, MB_OK, IDOK);
    exit;
  end;
  if not PythonWorks() then begin
    Log('Python 3 was not found; vpngo needs it to run.');
    if GuiWanted() then begin
      CustomExitCode := ExitGuiFailed;
      SuppressibleMsgBox(CustomMessage('GuiNeedsPython'), mbInformation, MB_OK, IDOK);
    end else
      SuppressibleMsgBox(CustomMessage('PythonMissing'), mbInformation, MB_OK, IDOK);
  end else if GuiWanted() then begin
    WizardForm.StatusLabel.Caption := CustomMessage('InstallingGui');
    if not PowerShell('stop-gui.ps1', '', Code) then
      Log(Format('windows\stop-gui.ps1 failed with exit code %d', [Code]));
    if PowerShell('vpngo.ps1', ' --install-gui', Code) then begin
      GuiDone := True;
      CreateShellLink(ExpandConstant('{userprograms}\VPNGo.lnk'), 'VPNGo',
        GuiRoot() + '\venv\Scripts\pythonw.exe', AddQuotes(GuiRoot() + '\app\run.py'), GuiRoot() + '\app',
        ExpandConstant('{localappdata}\vpngo\uninstall\vpngo.ico'), 0, SW_SHOWNORMAL);
    end else begin
      CustomExitCode := ExitGuiFailed;
      Log(Format('vpngo --install-gui failed with exit code %d', [Code]));
      SuppressibleMsgBox(FmtMessage(CustomMessage('GuiFailed'), [IntToStr(Code)]), mbError, MB_OK, IDOK);
    end;
  end;
  if ProxiFyreRequested() then begin
    WizardForm.StatusLabel.Caption := CustomMessage('InstallingProxiFyre');
    if not PowerShell('install-backend.ps1', '', Code) then begin
      CustomExitCode := ExitProxiFyreFailed;
      Log(Format('windows\install-backend.ps1 failed with exit code %d', [Code]));
      SuppressibleMsgBox(FmtMessage(CustomMessage('ProxiFyreFailed'), [IntToStr(Code), ExpandConstant('{app}')]),
        mbError, MB_OK, IDOK);
    end;
  end;
end;

function GetCustomSetupExitCode(): Integer;
begin
  Result := CustomExitCode;
end;

procedure RemoveUserPath(const Folder: String);
var
  Path, Rest, Part, Kept: String;
  Index: Integer;
begin
  if not RegQueryStringValue(HKCU, 'Environment', 'Path', Path) then
    exit;
  Rest := Path;
  Kept := '';
  while Rest <> '' do begin
    Index := Pos(';', Rest);
    if Index = 0 then begin
      Part := Rest;
      Rest := '';
    end else begin
      Part := Copy(Rest, 1, Index - 1);
      Rest := Copy(Rest, Index + 1, Length(Rest));
    end;
    if (Part <> '') and (CompareText(RemoveBackslashUnlessRoot(Part), RemoveBackslashUnlessRoot(Folder)) <> 0) then begin
      if Kept <> '' then
        Kept := Kept + ';';
      Kept := Kept + Part;
    end;
  end;
  if Kept <> Path then
    RegWriteExpandStringValue(HKCU, 'Environment', 'Path', Kept);
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  Bin: String;
  FindRec: TFindRec;
  Empty: Boolean;
  Code: Integer;
begin
  // Close the interface while windows\stop-gui.ps1 is still installed.
  if (CurUninstallStep = usUninstall) and FileExists(ExpandConstant('{userprograms}\VPNGo.lnk')) then
    PowerShell('stop-gui.ps1', '', Code);
  if CurUninstallStep <> usPostUninstall then
    exit;
  // windows\install.ps1 created the command; mihomo.exe and vpngo-gui.cmd may share its folder,
  // so the folder leaves PATH only when nothing else is in it.
  Bin := ExpandConstant('{%USERPROFILE}\bin');
  DeleteFile(Bin + '\vpngo.cmd');
  // The interface this installer added goes too; its history (state) and settings are kept.
  if DeleteFile(ExpandConstant('{userprograms}\VPNGo.lnk')) then begin
    DelTree(GuiRoot() + '\app', True, True, True);
    DelTree(GuiRoot() + '\venv', True, True, True);
    DelTree(GuiRoot() + '\engine', True, True, True);
    DeleteFile(GuiRoot() + '\cli.json');
    DeleteFile(Bin + '\vpngo-gui.cmd');
    RegDeleteValue(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Run', 'VPNGo');
  end;
  DelTree(Bin + '\vpngo.cmd.backup.*', False, True, False);
  Empty := True;
  if FindFirst(Bin + '\*', FindRec) then begin
    try
      repeat
        if (FindRec.Name <> '.') and (FindRec.Name <> '..') then
          Empty := False;
      until not FindNext(FindRec);
    finally
      FindClose(FindRec);
    end;
  end;
  if Empty then
    RemoveUserPath(Bin);
end;
