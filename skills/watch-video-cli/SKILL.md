---
name: watch-video-cli
version: "1.5.2"
description: Complete guide for AI agents (Antigravity, Codex, Claude Code) to interact with watch-skill CLI executable. Covers automatic ffmpeg verification/installation, structured JSON input/output invocation (--json), frame-path visual reasoning, dense temporal inspection (moment), and secret/configuration management.
license: MIT
user-invocable: true
allowed-tools: Bash, Read, Terminal
---

# Watch Skill Agent CLI Guide

`watch-skill` is a local-first video intelligence layer for AI agents. It extracts dense visual frames, OCR text, and audio transcripts into a persistent local vector/BM25 index, returning structured evidence for visual pair-programming and reasoning.

AI agents should ALWAYS pass `--json` to CLI commands for predictable, structured output envelopes with exit codes.

---

## 1. Environment & Dependency Verification

Before processing video, verify system dependencies:

```bash
watch-skill doctor --json
```

### Automatic FFmpeg Setup
`ffmpeg` is required for frame extraction and audio demuxing. If `ffmpeg` is missing, the agent can install it for the user:

- **Windows**:
  ```powershell
  winget install -e --id Gyan.FFmpeg
  # Or via Chocolatey:
  # choco install ffmpeg -y
  # Or Scoop:
  # scoop install ffmpeg
  ```
  *Note: After installing on Windows, ensure ffmpeg is available in PATH.*

- **macOS**:
  ```bash
  brew install ffmpeg
  ```

- **Linux (Ubuntu/Debian)**:
  ```bash
  sudo apt-get update && sudo apt-get install -y ffmpeg
  ```

### yt-dlp Setup
`yt-dlp` handles remote video URLs. If remote downloads are required and `yt-dlp` is not on PATH, install or update:
```bash
watch-skill doctor
```
Or install via package manager (`winget install yt-dlp`, `brew install yt-dlp`, `pip install -U yt-dlp`).

---

## 2. Configuration Management

Agents can configure API keys (e.g. Groq Whisper STT or Vision providers) globally without manually editing hidden `.env` files:

```bash
# Set Groq API key for fast cloud speech-to-text (transcripts)
watch-skill config set WATCHSKILL_GROQ_API_KEY gsk_xxxxxxxxxxxxxxxx

# Set Vision provider / strong model
watch-skill config set WATCHSKILL_ANTHROPIC_API_KEY sk-ant-xxxxxxxx
watch-skill config set WATCHSKILL_VISION_STRONG_MODEL claude-sonnet-5

# List active configurations (secrets are automatically redacted)
watch-skill config list --json

# Inspect active global env file path
watch-skill config path --json
```

**Precedence Order**:
1. Process environment variables (`WATCHSKILL_*`)
2. Current working directory `.env` (`WATCHSKILL_*`)
3. Global user configuration (`~/.watch-skill/.env`)
4. Built-in defaults

---

## 3. Agent Execution Lifecycle

### Step 1: Check Index First
Do NOT re-watch videos already indexed. Query the index first:
```bash
watch-skill list --json
```
If the video source or ID already exists in `data.videos`, jump straight to Step 3 or 4.

### Step 2: Ingest Video
```bash
watch-skill watch "<url_or_path>" --json
```
Options:
- `--max-frames 50`: Limit maximum extracted keyframes.
- `--start 00:30 --end 02:00`: Target a specific time window for dense frame sampling.
- `--transcript-only`: Extract only speech/subtitles (fastest, skips video downloads).

**Response Envelope (`schema_version: "1.0"`):**
```json
{
  "schema_version": "1.0",
  "ok": true,
  "command": "watch",
  "video_id": "d76c0fe5f3193eec",
  "frame_paths": [
    "D:\\cache\\.watch-skill\\cache\\d76c0fe5f3193eec\\f_001.jpg",
    "D:\\cache\\.watch-skill\\cache\\d76c0fe5f3193eec\\f_002.jpg"
  ],
  "data": {
    "duration": 125.4,
    "scenes_detected": 14,
    "transcript_segments": 22
  }
}
```

### Step 3: Ask Questions with Evidence
```bash
watch-skill ask <video_id> "<question>" --json
```
Returns structured answers with timestamped evidence and relevant `frame_paths`.

### Step 4: Temporal Deep Dive (`moment`)
When examining a specific instant in the video (e.g., UI error, animation glitch, code snippet, bug timestamp):
```bash
watch-skill moment <video_id> <timestamp> --window 10.0 --json
```
- `timestamp`: Format in seconds (`75.5`), `MM:SS` (`01:15`), or `HH:MM:SS` (`00:01:15`).
- `--window`: Context radius in seconds (between `0.5` and `120.0`, default `10.0`).

### Step 5: Visual Verification via `frame_paths`
Whenever `frame_paths` are present in the JSON response:
1. Extract the file paths from `response.frame_paths`.
2. Use the agent's file reader (`read_file` or image viewer tool) to inspect the image files directly.
3. Formulate the response incorporating actual visual evidence from the frames (colors, UI layouts, text, error dialogs) combined with the transcript and OCR.

---

## 4. Structured Error Handling

When a command fails (`exit_code != 0`), stdout returns a JSON error envelope:
```json
{
  "schema_version": "1.0",
  "ok": false,
  "command": "moment",
  "video_id": "abc12345",
  "error": {
    "code": "index.invalid_window",
    "message": "Window must be between 0.5 and 120.0 seconds.",
    "fix": "pass a window between 0.5 and 120.0 seconds (e.g. --window 10.0)",
    "details": {}
  }
}
```

**Agent Error Strategy**:
1. Check `error.code`:
   - `acquire.failed`: Check network connection or verify local video file exists.
   - `dependency.missing`: Inspect missing binary (e.g. `ffmpeg`) and run install commands.
   - `index.video_not_found`: Run `watch-skill watch <source> --json` first.
2. Read `error.fix`: Follow the specific remediation recommendation provided in the fix field.
