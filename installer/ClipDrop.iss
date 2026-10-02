; ClipDrop installer. build.bat compiles this into ClipDrop-Setup.exe.
; Installs per-user (no admin prompt) to %LOCALAPPDATA%\Programs\ClipDrop.

#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif

[Setup]
AppId={{6C1E2F4A-8B57-4D0E-9A3C-C11FD7A0B2E5}
AppName=ClipDrop
AppVersion={#AppVersion}
AppVerName=ClipDrop {#AppVersion}
AppPublisher=ClipDrop
DefaultDirName={localappdata}\Programs\ClipDrop
DefaultGroupName=ClipDrop
DisableProgramGroupPage=yes
DisableDirPage=yes
DisableReadyPage=yes
PrivilegesRequired=lowest
OutputDir=..
OutputBaseFilename=ClipDrop-Setup
SetupIconFile=..\assets\clipdrop.ico
UninstallDisplayIcon={app}\ClipDrop.exe
UninstallDisplayName=ClipDrop
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
RestartApplications=no

[Tasks]
Name: "desktopicon"; Description: "Put a ClipDrop icon on my desktop"; GroupDescription: "Shortcuts:"

[Files]
Source: "..\release\ClipDrop\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
; clear out the old program files on update (your settings live elsewhere and are kept)
Type: filesandordirs; Name: "{app}\_internal"

[Icons]
Name: "{autoprograms}\ClipDrop"; Filename: "{app}\ClipDrop.exe"
Name: "{autodesktop}\ClipDrop"; Filename: "{app}\ClipDrop.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\ClipDrop.exe"; Description: "Open ClipDrop now"; Flags: nowait postinstall skipifsilent
; in-app updates install silently, then reopen ClipDrop
Filename: "{app}\ClipDrop.exe"; Flags: nowait skipifnotsilent
