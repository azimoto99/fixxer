; Inno Setup installer script for Fixer.
; Build binaries first with scripts/build_windows.ps1.

#define MyAppName "Fixer"
#define MyAppVersion "0.1.0"
#define MyAppPublisher "Fixer"
#define MyAppURL "https://example.com"
#define MyAppExeTray "FixerTray\\FixerTray.exe"
#define MyAppExeCli "FixerCLI\\FixerCLI.exe"

[Setup]
AppId={{EFAAC5F5-C705-4B19-95B8-C73A3A7E4571}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\Fixer
DefaultGroupName=Fixer
DisableProgramGroupPage=yes
OutputDir=..\release
OutputBaseFilename=Fixer-Setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create desktop shortcut"; GroupDescription: "Additional icons:"; Flags: unchecked
Name: "autorun"; Description: "Launch Fixer tray at user login"; GroupDescription: "Startup options:"; Flags: checkedonce

[Files]
Source: "..\release\Fixer-Windows\FixerTray\*"; DestDir: "{app}\FixerTray"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\release\Fixer-Windows\FixerCLI\*"; DestDir: "{app}\FixerCLI"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\release\Fixer-Windows\config\default.json"; DestDir: "{app}\config"; Flags: ignoreversion
Source: "..\release\Fixer-Windows\README.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\Fixer Tray"; Filename: "{app}\{#MyAppExeTray}"; Parameters: "--config ""{app}\config\default.json"""
Name: "{autoprograms}\Fixer CLI"; Filename: "{app}\{#MyAppExeCli}"
Name: "{autodesktop}\Fixer Tray"; Filename: "{app}\{#MyAppExeTray}"; Parameters: "--config ""{app}\config\default.json"""; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "FixerOptimizer"; ValueData: """{app}\{#MyAppExeTray}"" --config ""{app}\config\default.json"" --dry-run"; Tasks: autorun; Flags: uninsdeletevalue

[Run]
Filename: "{app}\{#MyAppExeTray}"; Parameters: "--config ""{app}\config\default.json"" --dry-run"; Description: "Launch Fixer Tray"; Flags: nowait postinstall skipifsilent
