// Common Pascal logic and constants for Watch Skill Inno Setup scripts.

[Code]
const
  WM_SETTINGCHANGE = $001A;
  SMTO_ABORTIFHUNG = $0002;
  WATCHSKILL_APP_ID = '{B1884C62-97DE-4B22-8302-3D79DC7BD6F2}';

function SendMessageTimeout(
    hWnd: HWND;
    Msg: Cardinal;
    wParam: Cardinal;
    lParam: String;
    fuFlags: Cardinal;
    uTimeout: Cardinal;
    var lpdwResult: Cardinal
): Cardinal;
external 'SendMessageTimeoutW@user32.dll stdcall';

procedure BroadcastEnvironmentChange();
var
  Res: Cardinal;
begin
  try
    SendMessageTimeout(HWND_BROADCAST, WM_SETTINGCHANGE, 0, 'Environment', SMTO_ABORTIFHUNG, 5000, Res);
  except
  end;
end;

function NormalizePath(P: string): string;
begin
  Result := Trim(P);
  while (Length(Result) > 0) and (Result[Length(Result)] = '\') do
    SetLength(Result, Length(Result) - 1);
end;

procedure AddPathEntry(Entry: string);
var
  CurrentPath, NormEntry, NormToken, NewPath, Token: string;
  P, NextP: Integer;
  Found: Boolean;
begin
  NormEntry := Uppercase(NormalizePath(Entry));
  if NormEntry = '' then Exit;

  if not RegQueryStringValue(HKCU, 'Environment', 'Path', CurrentPath) then
    CurrentPath := '';

  Found := False;
  P := 1;
  while P <= Length(CurrentPath) do
  begin
    NextP := Pos(';', Copy(CurrentPath, P, Length(CurrentPath) - P + 1));
    if NextP = 0 then
      Token := Copy(CurrentPath, P, Length(CurrentPath) - P + 1)
    else
      Token := Copy(CurrentPath, P, NextP - 1);

    NormToken := Uppercase(NormalizePath(Token));
    if NormToken = NormEntry then
    begin
      Found := True;
      Break;
    end;

    if NextP = 0 then
      Break
    else
      P := P + NextP;
  end;

  if not Found then
  begin
    if (CurrentPath <> '') and (CurrentPath[Length(CurrentPath)] <> ';') then
      NewPath := CurrentPath + ';' + Entry
    else
      NewPath := CurrentPath + Entry;

    RegWriteStringValue(HKCU, 'Environment', 'Path', NewPath);
    BroadcastEnvironmentChange();
  end;
end;

procedure RemovePathEntry(Entry: string);
var
  CurrentPath, NormEntry, NormToken, NewPath, Token: string;
  P, NextP: Integer;
  Modified: Boolean;
begin
  NormEntry := Uppercase(NormalizePath(Entry));
  if NormEntry = '' then Exit;

  if not RegQueryStringValue(HKCU, 'Environment', 'Path', CurrentPath) then
    Exit;

  NewPath := '';
  Modified := False;
  P := 1;
  while P <= Length(CurrentPath) do
  begin
    NextP := Pos(';', Copy(CurrentPath, P, Length(CurrentPath) - P + 1));
    if NextP = 0 then
      Token := Copy(CurrentPath, P, Length(CurrentPath) - P + 1)
    else
      Token := Copy(CurrentPath, P, NextP - 1);

    NormToken := Uppercase(NormalizePath(Token));
    if NormToken = NormEntry then
      Modified := True
    else
    begin
      if Trim(Token) <> '' then
      begin
        if NewPath = '' then
          NewPath := Token
        else
          NewPath := NewPath + ';' + Token;
      end;
    end;

    if NextP = 0 then
      Break
    else
      P := P + NextP;
  end;

  if Modified then
  begin
    RegWriteStringValue(HKCU, 'Environment', 'Path', NewPath);
    BroadcastEnvironmentChange();
  end;
end;

procedure SafeDeploySkill(SourceFile, TargetDir: string);
var
  MarkerPath, TargetFile: string;
begin
  try
    TargetFile := AddBackslash(TargetDir) + 'SKILL.md';
    MarkerPath := AddBackslash(TargetDir) + '.watch-skill-managed';

    // Invariant: If directory exists and SKILL.md exists WITHOUT marker,
    // it is a user-owned pre-existing skill -> NEVER overwrite or corrupt!
    if DirExists(TargetDir) and FileExists(TargetFile) and (not FileExists(MarkerPath)) then
    begin
      Exit;
    end;

    // Clean install or managed upgrade -> deploy file and marker
    ForceDirectories(TargetDir);
    CopyFile(SourceFile, TargetFile, False);
    SaveStringToFile(MarkerPath, 'managed-by-watch-skill' + #13#10, False);
  except
  end;
end;

procedure RemoveManagedSkill(SkillDir: string);
var
  MarkerPath, SkillFilePath: string;
begin
  try
    MarkerPath := AddBackslash(SkillDir) + '.watch-skill-managed';
    SkillFilePath := AddBackslash(SkillDir) + 'SKILL.md';

    // Invariant: Only delete if the ownership marker is present!
    if FileExists(MarkerPath) then
    begin
      DeleteFile(MarkerPath);
      if FileExists(SkillFilePath) then
        DeleteFile(SkillFilePath);
      RemoveDir(SkillDir);
    end;
  except
  end;
end;

procedure EnsureFFmpeg();
var
  ResultCode: Integer;
begin
  try
    // Check if ffmpeg exists in PATH
    if not Exec('cmd.exe', '/c where ffmpeg', '', SW_HIDE, ewWaitUntilTerminated, ResultCode) or (ResultCode <> 0) then
    begin
      // Attempt winget installation silently without throwing
      Exec('cmd.exe', '/c winget install --id Gyan.FFmpeg -e --accept-source-agreements --accept-package-agreements --silent', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    end;
  except
  end;
end;
