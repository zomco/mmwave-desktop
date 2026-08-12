#ifndef TraceCueVersion
  #define TraceCueVersion "0.1.0"
#endif

[Setup]
AppId={{5AD41338-833D-4DC3-A65C-C80EA7375C44}
AppName=TraceCue
AppVersion={#TraceCueVersion}
AppPublisher=TraceCue
DefaultDirName={localappdata}\Programs\TraceCue
DefaultGroupName=TraceCue
OutputDir=..\..\artifacts
OutputBaseFilename=TraceCue-{#TraceCueVersion}-win-x64
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\TraceCue.exe

[Files]
Source: "..\..\artifacts\package\TraceCue\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\TraceCue"; Filename: "{app}\TraceCue.exe"
Name: "{autodesktop}\TraceCue"; Filename: "{app}\TraceCue.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Run]
Filename: "{app}\TraceCue.exe"; Description: "Open TraceCue"; Flags: nowait postinstall skipifsilent

[Code]
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  RemoveData: Integer;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    RemoveData := MsgBox(
      'Remove TraceCue settings, bookmark metadata, and locally generated clips? NVR recordings are never deleted.',
      mbConfirmation, MB_YESNO);
    if RemoveData = IDYES then
    begin
      DelTree(ExpandConstant('{localappdata}\TraceCue'), True, True, True);
      DelTree(GetEnv('USERPROFILE') + '\Videos\TraceCue', True, True, True);
    end;
  end;
end;

