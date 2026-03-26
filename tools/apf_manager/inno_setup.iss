; APF Manager — Inno Setup installer script
; Mirrors Archipelago's inno_setup.iss structure
;
; Build steps:
;   1. python setup.py build_exe   (produces build/APFManager/)
;   2. iscc inno_setup.iss          (produces APFManager-Setup.exe)

#define MyAppName "APF Manager"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "AP Framework"
#define MyAppExeName "APFManager.exe"
#define MyAppDebugExeName "APFManagerDebug.exe"
#define BuildDir "build\APFManager"

[Setup]
AppId={{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
OutputBaseFilename=APFManager-Setup-{#MyAppVersion}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesInstallIn64BitMode=x64

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
; Main executables
Source: "{#BuildDir}\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#BuildDir}\{#MyAppDebugExeName}"; DestDir: "{app}"; Flags: ignoreversion

; Python runtime + Kivy dependencies
Source: "{#BuildDir}\*.dll"; DestDir: "{app}"; Flags: ignoreversion

; cx_Freeze lib/ (library.zip + bundled modules, including webview/ package data)
Source: "{#BuildDir}\lib\*"; DestDir: "{app}\lib"; Flags: ignoreversion recursesubdirs createallsubdirs

; Built-in plugins (includes docs_viewer/assets/, html_viewer/, docs_viewer/.github_token)
Source: "{#BuildDir}\plugins\*"; DestDir: "{app}\plugins"; Flags: ignoreversion recursesubdirs createallsubdirs

; Data assets (icons, theme)
Source: "{#BuildDir}\data\*"; DestDir: "{app}\data"; Flags: ignoreversion recursesubdirs createallsubdirs; Check: DataDirExists

; WebView2 bootstrapper — silent install if runtime not already present on target machine
; Download MicrosoftEdgeWebview2Setup.exe from Microsoft and place it next to this .iss file.
Source: "redist\MicrosoftEdgeWebview2Setup.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall; Check: NeedsWebView2

[Dirs]
; Create empty custom_plugins directory for user plugins
Name: "{app}\custom_plugins"

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{#MyAppName} (Debug)"; Filename: "{app}\{#MyAppDebugExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
; Install WebView2 runtime silently before app launches (only if not already present)
Filename: "{tmp}\MicrosoftEdgeWebview2Setup.exe"; Parameters: "/silent /install"; \
  Description: "Installing WebView2 Runtime..."; \
  Flags: runhidden waituntilterminated; Check: NeedsWebView2
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[Code]
function DataDirExists(): Boolean;
begin
  Result := DirExists(ExpandConstant('{src}\{#BuildDir}\data'));
end;

function NeedsWebView2(): Boolean;
var
  Version: String;
begin
  // Returns True if WebView2 runtime is NOT installed.
  // Registry key written by the WebView2 Evergreen installer.
  Result := not RegQueryStringValue(
    HKLM,
    'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}',
    'pv', Version);
end;
