; Inno Setup 6 script. Build with packaging\build.ps1 (needs build\pyi-dist\MirrorHub populated).
#define AppName "Mirrorhub"
#define AppVersion "1.0.0"
#define SrcDir "..\build\pyi-dist\MirrorHub"

[Setup]
AppId={{B7E0C9F2-3B8A-4F6E-9D41-6D1F5C2A9E10}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Mirrorhub
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist
OutputBaseFilename=Mirrorhub-Setup-{#AppVersion}
SetupIconFile=mirrorhub.ico
UninstallDisplayIcon={app}\MirrorHub.exe
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
LicenseFile=THIRD_PARTY_NOTICES.txt
VersionInfoVersion={#AppVersion}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a Desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: unchecked

[Files]
Source: "{#SrcDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "THIRD_PARTY_NOTICES.txt"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\MirrorHub.exe"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\MirrorHub.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\MirrorHub.exe"; Description: "Launch Mirrorhub"; Flags: nowait postinstall skipifsilent

[UninstallRun]
; adb keeps a background server that locks adb.exe; stop it so the files can be removed.
Filename: "{app}\tools\scrcpy\scrcpy-win64-v4.0\adb.exe"; Parameters: "kill-server"; Flags: runhidden; RunOnceId: "AdbKill"

[Code]
function WebView2Installed(): Boolean;
var v: String;
begin
  Result :=
    RegQueryStringValue(HKLM, 'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', v) or
    RegQueryStringValue(HKLM, 'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', v) or
    RegQueryStringValue(HKCU, 'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', v);
  if Result then Result := (v <> '') and (v <> '0.0.0.0');
end;

procedure StopAdb();
var rc: Integer; adb: String;
begin
  adb := ExpandConstant('{app}\tools\scrcpy\scrcpy-win64-v4.0\adb.exe');
  if FileExists(adb) then Exec(adb, 'kill-server', '', SW_HIDE, ewWaitUntilTerminated, rc);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  StopAdb();   // upgrade: release adb.exe before files are replaced
  Result := '';
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if (CurStep = ssPostInstall) and (not WebView2Installed()) and (not WizardSilent()) then
    MsgBox('Microsoft Edge WebView2 Runtime was not detected. Mirrorhub will open in your default browser instead ' +
           'until WebView2 is installed (https://developer.microsoft.com/microsoft-edge/webview2/).', mbInformation, MB_OK);
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if (CurUninstallStep = usPostUninstall) and (not UninstallSilent()) then
    MsgBox('Your data (database, uploads, backups) is kept in %APPDATA%\Mirrorhub. ' +
           'Delete that folder yourself if you want to remove everything.', mbInformation, MB_OK);
end;
