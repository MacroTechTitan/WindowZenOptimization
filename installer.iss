[Setup]
AppName=SystemOptimizer Pro
AppVersion=1.0.0
AppPublisher=SystemOptimizer
AppPublisherURL=https://systemoptimizer.app
DefaultDirName={autopf}\SystemOptimizer Pro
DefaultGroupName=SystemOptimizer Pro
OutputDir=installer_output
OutputBaseFilename=SystemOptimizerPro_Setup_v1.0.0
Compression=lzma2
SolidCompression=yes
SetupIconFile=static\icon.ico
UninstallDisplayIcon={app}\SystemOptimizer Pro.exe
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
Source: "dist\SystemOptimizer Pro\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\SystemOptimizer Pro"; Filename: "{app}\SystemOptimizer Pro.exe"
Name: "{group}\Uninstall SystemOptimizer Pro"; Filename: "{uninstallexe}"
Name: "{autodesktop}\SystemOptimizer Pro"; Filename: "{app}\SystemOptimizer Pro.exe"; Tasks: desktopicon
Name: "{userstartup}\SystemOptimizer Pro"; Filename: "{app}\SystemOptimizer Pro.exe"; Tasks: startupicon

[Run]
Filename: "{app}\SystemOptimizer Pro.exe"; Description: "Launch SystemOptimizer Pro"; Flags: nowait postinstall skipifsilent
