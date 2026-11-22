; Inno Setup script. Build the PyInstaller bundle first, then:
;   iscc /DAppVersion=0.3.0 packaging\windows\lightdeck.iss

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{6B0E3C7A-4F5D-4C1B-9E1A-7D2F1C3B8A51}
AppName=Lightdeck
AppVersion={#AppVersion}
AppPublisher=MechNoxer
AppPublisherURL=https://github.com/MechNoxer/lightdeck
DefaultDirName={autopf}\Lightdeck
DefaultGroupName=Lightdeck
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\..\dist
OutputBaseFilename=Lightdeck-{#AppVersion}-windows-setup
SetupIconFile=..\icons\lightdeck.ico
UninstallDisplayIcon={app}\Lightdeck.exe
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
LicenseFile=..\..\LICENSE

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\..\dist\Lightdeck\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Lightdeck"; Filename: "{app}\Lightdeck.exe"
Name: "{autodesktop}\Lightdeck"; Filename: "{app}\Lightdeck.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Lightdeck.exe"; Description: "{cm:LaunchProgram,Lightdeck}"; Flags: nowait postinstall skipifsilent
