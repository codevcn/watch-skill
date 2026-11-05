; Inno Setup script for Standalone Watch Skill Uninstaller
#ifndef MyAppVersion
#define MyAppVersion "1.5.4"
#endif

[Setup]
AppId={{B1884C62-97DE-4B22-8302-3D79DC7BD6F2}}-uninstaller
AppName=Watch Skill Uninstaller
AppVersion={#MyAppVersion}
AppPublisher=CodeVCN
AppPublisherURL=https://github.com/codevcn/watch-skill
DefaultDirName={tmp}\watch-skill-cleanup
PrivilegesRequired=lowest
OutputDir=..\..\dist
OutputBaseFilename=watch-skill-uninstaller
Compression=lzma2/max
SolidCompression=yes
Uninstallable=no
CreateUninstallRegKey=no
UpdateUninstallLogAppName=no
WizardStyle=modern

#include "common.iss"

[Code]
function InitializeSetup(): Boolean;
var
  RegKey, UninstStr, AppDir, GeminiSkillDir, ClaudeSkillDir: string;
  ResultCode: Integer;
begin
  RegKey := 'Software\Microsoft\Windows\CurrentVersion\Uninstall\' + WATCHSKILL_APP_ID + '_is1';

  // 1. Try to invoke the standard uninstaller silently if present
  if RegQueryStringValue(HKCU, RegKey, 'QuietUninstallString', UninstStr) then
  begin
    Exec('cmd.exe', '/c ' + UninstStr, '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  end
  else if RegQueryStringValue(HKCU, RegKey, 'UninstallString', UninstStr) then
  begin
    Exec('cmd.exe', '/c ' + UninstStr + ' /SILENT /NORESTART', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  end;

  // 2. Residual cleanup (idempotent, safe fallback)
  AppDir := ExpandConstant('{localappdata}\Programs\watch-skill');
  RemovePathEntry(AppDir);

  GeminiSkillDir := ExpandConstant('{%USERPROFILE}\.gemini\config\skills\watch-video-cli');
  ClaudeSkillDir := ExpandConstant('{%USERPROFILE}\.claude\skills\watch-video-cli');
  RemoveManagedSkill(GeminiSkillDir);
  RemoveManagedSkill(ClaudeSkillDir);

  // Clean remaining files in AppDir if standard uninstaller missed them
  if DirExists(AppDir) then
  begin
    DeleteFile(AddBackslash(AppDir) + 'watch-skill.exe');
    DeleteFile(AddBackslash(AppDir) + 'unins000.exe');
    DeleteFile(AddBackslash(AppDir) + 'unins000.dat');
    RemoveDir(AppDir);
  end;

  // Clean residual registry key
  RegDeleteKeyIncludingSubkeys(HKCU, RegKey);

  // Broadcast environment variable refresh
  BroadcastEnvironmentChange();

  if not WizardSilent then
  begin
    MsgBox('Watch Skill has been successfully uninstalled from your system.', mbInformation, MB_OK);
  end;

  // Return False to exit without displaying unnecessary setup wizard pages
  Result := False;
end;
