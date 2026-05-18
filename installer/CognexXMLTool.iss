#define MyAppName "Cognex XML Tool"
#define MyAppVersion "1.1.0"
#define MyAppPublisher "Hemy Gulati"
#define MyAppURL "https://github.com/HemyGulati/CognexXMLTool"
#define MyAppExeName "Cognex XML Tool.exe"

[Setup]
AppId={{F01C2E65-2F36-4CC1-8C09-6DB0485D9E3A}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}/issues
AppUpdatesURL={#MyAppURL}/releases
AppCopyright=Copyright (c) 2026 Hemy Gulati
DefaultDirName={autopf}\Cognex XML Tool
DefaultGroupName=Cognex XML Tool
DisableProgramGroupPage=yes
LicenseFile=..\LICENSE.txt
OutputDir=..\installer_output
OutputBaseFilename=CognexXMLTool_Setup_v{#MyAppVersion}
SetupIconFile=..\assets\cognex_xml_tool.ico
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
Source: "..\dist\Cognex XML Tool.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\CHANGELOG.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\LICENSE"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\LICENSE.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\cognex_xml_tool_config.example.json"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\assets\cognex_xml_tool.ico"; DestDir: "{app}\assets"; Flags: ignoreversion
Source: "..\assets\cognex_xml_tool.png"; DestDir: "{app}\assets"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\Cognex XML Tool"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{autodesktop}\Cognex XML Tool"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch Cognex XML Tool"; Flags: nowait postinstall skipifsilent
