; Inno Setup Script for LotusLamp X Windows Controller

[Setup]
AppId={{8E7A2D41-3C9B-4F12-9A55-7D21B3E60A19}
AppName=LotusLamp X
AppVersion=1.0.0
AppPublisher=overlordJ
AppPublisherURL=https://github.com/overlordJ/Windows-App-for-LotusLamp-X
DefaultDirName={localappdata}\Programs\LotusLamp X
DefaultGroupName=LotusLamp X
AllowNoIcons=yes
PrivilegesRequired=lowest
OutputDir=dist_installer
OutputBaseFilename=LotusLampX_Setup
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\LotusLamp X.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "dist_onedir\LotusLamp X\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\LotusLamp X"; Filename: "{app}\LotusLamp X.exe"
Name: "{group}\{cm:UninstallProgram,LotusLamp X}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\LotusLamp X"; Filename: "{app}\LotusLamp X.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\LotusLamp X.exe"; Description: "{cm:LaunchProgram,LotusLamp X}"; Flags: nowait postinstall skipifsilent
