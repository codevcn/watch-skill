; Inno Setup script for Watch Skill Windows Installer
#ifndef MyAppVersion
#define MyAppVersion "1.5.6"
#endif

[Setup]
AppId={{B1884C62-97DE-4B22-8302-3D79DC7BD6F2}}
AppName=Watch Skill
AppVersion={#MyAppVersion}
AppPublisher=CodeVCN
AppPublisherURL=https://github.com/codevcn/watch-skill
AppSupportURL=https://github.com/codevcn/watch-skill/issues
AppUpdatesURL=https://github.com/codevcn/watch-skill/releases
DefaultDirName={localappdata}\Programs\watch-skill
DisableDirPage=no
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\..\dist
OutputBaseFilename=watch-skill-installer
Compression=lzma2/max
SolidCompression=yes
ChangesEnvironment=yes
Uninstallable=yes
UninstallDisplayName=Watch Skill
UninstallDisplayIcon={app}\watch-skill.exe
WizardStyle=modern

[Files]
Source: "..\..\dist\watch-skill-windows-x86_64.exe"; DestDir: "{app}"; DestName: "watch-skill.exe"; Flags: ignoreversion
Source: "..\..\skills\watch-video-cli\SKILL.md"; DestName: "watch-video-cli-SKILL.md"; Flags: dontcopy

#include "common.iss"

[Code]
procedure CurStepChanged(CurStep: TSetupStep);
var
  TempSkillFile, GeminiSkillDir, ClaudeSkillDir: string;
begin
  if CurStep = ssPostInstall then
  begin
    // Add application directory to HKCU Path
    AddPathEntry(ExpandConstant('{app}'));

    // Extract skill file to temporary directory
    ExtractTemporaryFile('watch-video-cli-SKILL.md');
    TempSkillFile := ExpandConstant('{tmp}\watch-video-cli-SKILL.md');

    // Safe deploy to Gemini and Claude skills (respects unmanaged pre-existing skills)
    GeminiSkillDir := ExpandConstant('{%USERPROFILE}\.gemini\config\skills\watch-video-cli');
    ClaudeSkillDir := ExpandConstant('{%USERPROFILE}\.claude\skills\watch-video-cli');
    SafeDeploySkill(TempSkillFile, GeminiSkillDir);
    SafeDeploySkill(TempSkillFile, ClaudeSkillDir);

    // Ensure FFmpeg is present (winget fallback)
    EnsureFFmpeg();
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  GeminiSkillDir, ClaudeSkillDir: string;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    // Remove application directory from HKCU Path
    RemovePathEntry(ExpandConstant('{app}'));

    // Remove managed skills cleanly only if ownership marker exists
    GeminiSkillDir := ExpandConstant('{%USERPROFILE}\.gemini\config\skills\watch-video-cli');
    ClaudeSkillDir := ExpandConstant('{%USERPROFILE}\.claude\skills\watch-video-cli');
    RemoveManagedSkill(GeminiSkillDir);
    RemoveManagedSkill(ClaudeSkillDir);
  end;
end;
