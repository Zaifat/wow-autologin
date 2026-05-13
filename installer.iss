; Inno Setup script — wraps the Nuitka folder build in an installer.
; A signed installer trips far fewer AV heuristics than a self-extracting
; onefile binary, and Windows SmartScreen learns to trust it after a few
; downloads.

#define MyAppName    "Менеджер персонажей WOW"
#define MyAppVersion "1.3.4"
#define MyAppPublisher "Zaifat"
#define MyAppExeName "Manager_WOW.exe"

[Setup]
AppId={{A8F9C2D1-3E47-4B6A-9F8E-2C5D7E1F4A82}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL=https://t.me/Zaifat_DK
; {autopf} resolves to "Program Files" (x64) since ArchitecturesInstallIn64BitMode
; is x64compatible — that's the standard install location for system-wide apps.
DefaultDirName={autopf}\WowManager
DefaultGroupName=Менеджер персонажей WOW
DisableProgramGroupPage=yes
; Admin rights required to write under Program Files. The user can still
; override via the dialog (e.g. install per-user under AppData) if they
; prefer a no-elevation install.
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=dist\installer
OutputBaseFilename=Manager_WOW
SetupIconFile=wow.ico
Compression=lzma2/ultra
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\{#MyAppExeName}
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
VersionInfoCompany={#MyAppPublisher}
VersionInfoProductName={#MyAppName}
VersionInfoVersion={#MyAppVersion}.0
VersionInfoProductVersion={#MyAppVersion}.0

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

[Tasks]
Name: "desktopicon"; Description: "Создать ярлык на рабочем столе"; \
    GroupDescription: "Дополнительно:"
Name: "autostart";   Description: "Запускать при старте Windows (свернётся в трей)"; \
    GroupDescription: "Дополнительно:"; Flags: unchecked

[Files]
; Take the whole Nuitka standalone output. The exe ends up at the root.
Source: "dist\launcher.dist\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Удалить {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{userdesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; \
    ValueType: string; ValueName: "WowManager"; \
    ValueData: """{app}\{#MyAppExeName}"""; Tasks: autostart; Flags: uninsdeletevalue

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Запустить {#MyAppName}"; \
    Flags: nowait postinstall skipifsilent
