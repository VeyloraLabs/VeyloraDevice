#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif
#ifndef SourceDir
  #error SourceDir is required
#endif
#ifndef RepoRoot
  #error RepoRoot is required
#endif
#ifndef OutputDir
  #define OutputDir "."
#endif
#ifndef OutputName
  #define OutputName "VeyloraDevice-Setup"
#endif

[Setup]
AppId={{8F3C2B1E-5A47-4D1B-9C6E-2D7A4B9E1F30}
AppName=VeyloraDevice
AppVersion={#AppVersion}
AppPublisher=VeyloraLabs
AppPublisherURL=https://github.com/VeyloraLabs/VeyloraDevice
AppSupportURL=https://github.com/VeyloraLabs/VeyloraDevice/issues
AppUpdatesURL=https://github.com/VeyloraLabs/VeyloraDevice/releases
DefaultDirName={autopf}\VeyloraDevice
DefaultGroupName=VeyloraDevice
DisableProgramGroupPage=yes
LicenseFile={#RepoRoot}\LICENSE
SetupIconFile={#RepoRoot}\assets\icon.ico
UninstallDisplayIcon={app}\VeyloraDevice.exe
OutputDir={#OutputDir}
OutputBaseFilename={#OutputName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=dialog

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\VeyloraDevice"; Filename: "{app}\VeyloraDevice.exe"
Name: "{autodesktop}\VeyloraDevice"; Filename: "{app}\VeyloraDevice.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\VeyloraDevice.exe"; Description: "{cm:LaunchProgram,VeyloraDevice}"; Flags: nowait postinstall skipifsilent
