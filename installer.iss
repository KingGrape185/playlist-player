; Needs Inno Setup 6 (free): https://jrsoftware.org/isdl.php
#define MyAppName "Playlist Player"
#define MyAppVersion "1.0.0"
[Setup]
AppId={{B7D2A6C4-5E1F-4B8A-9C3D-2F6A1E0D7C11}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
OutputDir=installer
OutputBaseFilename=PlaylistPlayer-Setup
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\PlaylistPlayer.exe
Compression=lzma2
SolidCompression=yes
PrivilegesRequired=lowest
CloseApplications=yes
[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"
[Files]
Source: "dist\PlaylistPlayer.exe"; DestDir: "{app}"; Flags: ignoreversion
[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\PlaylistPlayer.exe"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\PlaylistPlayer.exe"; Tasks: desktopicon
[Run]
Filename: "{app}\PlaylistPlayer.exe"; Description: "Launch Playlist Player"; Flags: nowait postinstall skipifsilent
