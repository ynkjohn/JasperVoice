; JasperVoice — Inno Setup installer script
; ---------------------------------------------------------------------------
; Produces a single small bootstrapper EXE (JasperVoice-Setup-<ver>.exe) that
; installs the PyInstaller one-folder bundle like a normal Windows desktop app.
;
; Design decisions:
;   * PER-USER install (PrivilegesRequired=lowest). The app needs no admin to
;     run; installing under %LocalAppData% avoids UAC for both first install and
;     every auto-update. (The global-hotkey hook may still prompt for admin at
;     RUNTIME on some systems — that's unrelated to install location.)
;   * AppMutex matches single_instance.MUTEX_NAME so the installer can detect a
;     running JasperVoice and close it (CloseApplications) before replacing the
;     locked _internal\ files during an update.
;   * In-app updates run this installer with /VERYSILENT plus
;     /JasperVoiceAutoLaunch. That path must not show the wizard and must relaunch
;     JasperVoice after replacing files.
;   * The one-folder bundle is copied wholesale; JasperVoice.exe MUST stay next
;     to its _internal\ folder, which {app} guarantees.
;   * No services, no registry beyond uninstall + per-user Run (optional). No
;     telemetry. No network calls — the in-app updater handles update fetching.
;
; Build:
;   ISCC.exe /DAppVersion=<ver> /DSourceDir=<dist\JasperVoice> installer\JasperVoice.iss
; The build_release.ps1 script passes those defines automatically.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

; Folder containing the built bundle (JasperVoice.exe + _internal\).
#ifndef SourceDir
  #define SourceDir "..\dist\JasperVoice"
#endif

#define AppName "JasperVoice"
#define AppPublisher "JasperVoice"
#define AppExeName "JasperVoice.exe"
#define AppMutexName "JasperVoice_SingleInstance_Mutex"
; Stable GUID identifying this product across versions (required for in-place
; upgrades to find and replace the previous install instead of stacking).
#define AppId "{{B6E6F4C2-3A2E-4F2B-9C1D-7E4A1F2C8D90}"

[Setup]
AppId={#AppId}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
VersionInfoVersion={#AppVersion}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
DisableDirPage=auto
; Per-user install: no admin prompt, updates apply silently under the user.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
; Detect and close a running instance before replacing files (critical for
; in-place auto-update — _internal\*.dll are locked while the app runs).
CloseApplications=yes
CloseApplicationsFilter=*.exe,*.dll
RestartApplications=yes
AppMutex={#AppMutexName}
; Output naming: JasperVoice-Setup-<version>.exe
OutputBaseFilename=JasperVoice-Setup-{#AppVersion}
OutputDir=..\dist\installer
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
; Icon shown for the installer + add/remove programs entry.
SetupIconFile=..\assets\icon.ico
UninstallDisplayIcon={app}\{#AppExeName}
UninstallDisplayName={#AppName}
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"
Name: "startupicon"; Description: "Start JasperVoice automatically when I sign in"; GroupDescription: "Startup:"; Flags: unchecked

[Files]
; Copy the entire one-folder bundle. recursesubdirs picks up _internal\.
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon
; Optional autostart: a Startup-folder shortcut (per-user, no registry).
Name: "{userstartup}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: startupicon

[Run]
; Offer to launch right after install / update. nowait so the wizard closes.
Filename: "{app}\{#AppExeName}"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent
; Silent in-app updater path: no wizard, but relaunch the updated app.
Filename: "{app}\{#AppExeName}"; Flags: nowait; Check: IsAutoUpdateLaunch

[UninstallDelete]
; Remove staged update installers we downloaded; leave config/history/models
; alone so a reinstall keeps the user's settings and downloaded model.
Type: filesandordirs; Name: "{userappdata}\{#AppName}\updates"

[Code]
function HasCommandLineParam(Name: String): Boolean;
var
  I: Integer;
begin
  Result := False;
  for I := 1 to ParamCount do
  begin
    if CompareText(ParamStr(I), Name) = 0 then
    begin
      Result := True;
      Exit;
    end;
  end;
end;

function IsAutoUpdateLaunch: Boolean;
begin
  Result := WizardSilent and HasCommandLineParam('/JasperVoiceAutoLaunch');
end;
