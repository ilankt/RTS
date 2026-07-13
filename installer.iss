; Inno Setup script for the RTS game.
;
; Compile:  ISCC installer.iss
;   (or just run build_installer.bat, which builds the app first, then this)
;
; Requires: Inno Setup 6  ->  https://jrsoftware.org/isdl.php
;           and a prior PyInstaller build present in  dist\RTS\
;
; Per-user install (PrivilegesRequired=lowest): no UAC prompt, lands in
; %LOCALAPPDATA%\Programs\RTS. The game writes saves/settings/logs to
; %LOCALAPPDATA%\RTS (see core/app_paths.py), separate from the install dir.

#define MyAppName "RTS"
; build_installer.bat passes the real version via /DMyAppVersion (read from
; core/version.py). This fallback is used only when ISCC is run by hand;
; keep it in sync with core/version.py's GAME_VERSION.
#ifndef MyAppVersion
  #define MyAppVersion "0.9.0-beta"
#endif
#define MyAppPublisher "Ilan Kachler"
#define MyAppExeName "RTS.exe"

[Setup]
; Keep this AppId stable across versions so upgrades replace, not duplicate.
AppId={{A4E8C1F2-6B3D-4E9A-9C57-2F8D1B0A7E43}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=installer_output
OutputBaseFilename={#MyAppName}_Setup_{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
UninstallDisplayName={#MyAppName} {#MyAppVersion}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; Ship the entire one-folder PyInstaller output (exe + _internal payload).
Source: "dist\RTS\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent
