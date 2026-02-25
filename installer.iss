[Setup]
AppName=MTT Windows Infinite Optimizer
AppVersion=1.0.0
AppPublisher=Macro Tech Titan
AppPublisherURL=https://windows.macrotechtitan.com
DefaultDirName={autopf}\MTT Windows Infinite Optimizer
DefaultGroupName=MTT Windows Infinite Optimizer
OutputDir=installer_output
OutputBaseFilename=MTT_InfiniteOptimizer_Setup_v1.0.0
Compression=lzma2
SolidCompression=yes
SetupIconFile=static\icon.ico
UninstallDisplayIcon={app}\MTT Windows Infinite Optimizer.exe
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin
WizardStyle=modern

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "startupicon"; Description: "Start with Windows"; GroupDescription: "Startup:"

[Files]
Source: "dist\MTT Windows Infinite Optimizer\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\MTT Windows Infinite Optimizer"; Filename: "{app}\MTT Windows Infinite Optimizer.exe"
Name: "{group}\Uninstall MTT Windows Infinite Optimizer"; Filename: "{uninstallexe}"
Name: "{autodesktop}\MTT Windows Infinite Optimizer"; Filename: "{app}\MTT Windows Infinite Optimizer.exe"; Tasks: desktopicon
Name: "{userstartup}\MTT Windows Infinite Optimizer"; Filename: "{app}\MTT Windows Infinite Optimizer.exe"; Tasks: startupicon

[Run]
Filename: "{app}\MTT Windows Infinite Optimizer.exe"; Description: "Launch MTT Windows Infinite Optimizer"; Flags: nowait postinstall skipifsilent
