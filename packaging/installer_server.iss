; MultiRegistrator — Server installer (per-machine).
#define MyAppName "MultiRegistrator Server"
#define MyAppVersion "1.1.8"
#define MyAppPublisher "MultiRegistrator"
#define MyAppExeName "MultiRegistratorServer.exe"

[Setup]
AppId={{8A2D5E71-3B94-4C6F-8D1A-6F0E9C4B2A55}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\MultiRegistrator\Server
DefaultGroupName=MultiRegistrator
DisableProgramGroupPage=yes
PrivilegesRequired=admin
OutputDir=..\installers
OutputBaseFilename=MultiRegistratorServer-Setup-{#MyAppVersion}
SetupIconFile=icons\server.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}
Uninstallable=yes
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Dirs]
Name: "{app}\config"
Name: "{app}\archive"
Name: "{app}\logs"

[Files]
Source: "..\dist\MultiRegistratorServer.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "server_config.default.json"; DestDir: "{app}\config"; DestName: "server_config.json"; Flags: onlyifdoesntexist

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"
Name: "{group}\Удалить {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Создать ярлык на рабочем столе"; GroupDescription: "Дополнительно:"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Запустить {#MyAppName}"; Flags: nowait postinstall skipifsilent
