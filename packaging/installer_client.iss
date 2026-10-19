; MultiRegistrator — Client installer (per-user).
#define MyAppName "MultiRegistrator Client"
#define MyAppVersion "1.1.6"
#define MyAppPublisher "MultiRegistrator"
#define MyAppExeName "MultiRegistratorClient.exe"

[Setup]
AppId={{C4F1B6A2-7D3E-4A61-9B2C-2E8F5A1D7C10}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\MultiRegistrator\Client
DefaultGroupName=MultiRegistrator
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\installers
OutputBaseFilename=MultiRegistratorClient-Setup-{#MyAppVersion}
SetupIconFile=icons\client.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "..\dist\MultiRegistratorClient.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Создать ярлык на рабочем столе"; GroupDescription: "Дополнительно:"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Запустить {#MyAppName}"; Flags: nowait postinstall skipifsilent
