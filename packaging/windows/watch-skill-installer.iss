; Inno Setup script for Watch Skill Windows Installer
#ifndef MyAppVersion
#define MyAppVersion "1.5.9"
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
CloseApplications=force
CloseApplicationsFilter=*.exe,*.dll,*.pyd
RestartApplications=no
WizardStyle=modern

[InstallDelete]
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "..\..\dist\watch-skill\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion
Source: "..\..\skills\watch-video-extra\SKILL.md"; DestName: "watch-video-extra-SKILL.md"; Flags: dontcopy
Source: "..\..\skills\watch-video-cli\SKILL.md"; DestName: "watch-video-cli-SKILL.md"; Flags: dontcopy

#include "common.iss"

[Code]
procedure CurStepChanged(CurStep: TSetupStep);
var
  TempExtraSkill, TempCliSkill, GeminiSkillBase, ClaudeSkillBase: string;
  ResultCode: Integer;
begin
  if CurStep = ssPostInstall then
  begin
    // Add application directory to HKCU Path
    AddPathEntry(ExpandConstant('{app}'));

    // Extract skill files to temporary directory
    ExtractTemporaryFile('watch-video-extra-SKILL.md');
    TempExtraSkill := ExpandConstant('{tmp}\watch-video-extra-SKILL.md');
    ExtractTemporaryFile('watch-video-cli-SKILL.md');
    TempCliSkill := ExpandConstant('{tmp}\watch-video-cli-SKILL.md');

    // Safe deploy to Gemini and Claude skills (respects unmanaged pre-existing skills)
    GeminiSkillBase := ExpandConstant('{%USERPROFILE}\.gemini\config\skills');
    ClaudeSkillBase := ExpandConstant('{%USERPROFILE}\.claude\skills');
    SafeDeploySkill(TempExtraSkill, AddBackslash(GeminiSkillBase) + 'watch-video-extra');
    SafeDeploySkill(TempCliSkill, AddBackslash(GeminiSkillBase) + 'watch-video-cli');
    SafeDeploySkill(TempExtraSkill, AddBackslash(ClaudeSkillBase) + 'watch-video-extra');
    SafeDeploySkill(TempCliSkill, AddBackslash(ClaudeSkillBase) + 'watch-video-cli');

    // Register MCP server (`watch-skill serve`) with detected agents safely
    try
      Exec(ExpandConstant('{app}\watch-skill.exe'), 'setup --yes', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    except
    end;

    // Ensure FFmpeg is present (winget fallback)
    EnsureFFmpeg();
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  GeminiSkillBase, ClaudeSkillBase: string;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    // Remove application directory from HKCU Path
    RemovePathEntry(ExpandConstant('{app}'));

    // Remove managed skills cleanly only if ownership marker exists
    GeminiSkillBase := ExpandConstant('{%USERPROFILE}\.gemini\config\skills');
    ClaudeSkillBase := ExpandConstant('{%USERPROFILE}\.claude\skills');
    RemoveManagedSkill(AddBackslash(GeminiSkillBase) + 'watch-video-extra');
    RemoveManagedSkill(AddBackslash(GeminiSkillBase) + 'watch-video-cli');
    RemoveManagedSkill(AddBackslash(ClaudeSkillBase) + 'watch-video-extra');
    RemoveManagedSkill(AddBackslash(ClaudeSkillBase) + 'watch-video-cli');
  end;
end;
