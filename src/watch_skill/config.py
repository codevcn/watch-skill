"""Single typed configuration for the whole engine.

Precedence (highest wins): CLI flag (surfaces pass overrides explicitly) >
process environment > ``.env`` in the current working directory > defaults.
All environment variables use the ``WATCHSKILL_`` prefix, e.g.
``WATCHSKILL_FRAME_WIDTH=1024``.
"""
from __future__ import annotations

import os
import re
import sys
import tempfile
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


def global_env_file() -> Path:
    """Return the global user environment file (~/.watch-skill/.env or override)."""
    override = os.environ.get("WATCHSKILL_GLOBAL_ENV_FILE")
    if override:
        return Path(override)
    return Path.home() / ".watch-skill" / ".env"


def _default_env_files() -> tuple[str, ...]:
    """Default env files in precedence order: (global, cwd).

    pydantic-settings loads the files in sequence where the last file in the tuple
    overrides the earlier ones, establishing:
    defaults < global ~/.watch-skill/.env < CWD/.env < process environment.
    """
    return (str(global_env_file()), ".env")


class Settings(BaseSettings):
    """Typed settings for Watch Skill. See module docstring for precedence."""

    model_config = SettingsConfigDict(
        env_prefix="WATCHSKILL_",
        env_file=_default_env_files(),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    def __init__(self, **values: Any) -> None:
        if "_env_file" not in values:
            values["_env_file"] = _default_env_files()
        super().__init__(**values)

    # --- storage ---------------------------------------------------------
    data_dir: Path = Field(
        default_factory=lambda: Path.home() / ".watch-skill",
        description="Root for cache, index, loops, health log, managed binaries.",
    )
    bin_dir: Path | None = Field(
        default=None,
        description="Managed portable-binaries dir. Default: <data_dir>/bin.",
    )
    cache_max_bytes: int = Field(
        default=20 * 1024**3,
        description="Download-cache size cap; LRU eviction beyond this.",
    )

    # --- perception (defaults inherited from the reference project) ------
    frame_width: int = Field(default=512, description="Extracted frame width in px.")
    max_video_height: int = Field(
        default=720,
        ge=144,
        le=1080,
        description="Ceiling for downloaded video height. 720p answers almost "
        "every question a video can answer; 4K costs minutes of transfer and "
        "gigabytes of disk to answer it no better. Hard-capped at 1080.",
    )
    frame_cap: int = Field(default=100, description="Hard cap on frames per analysis.")
    max_fps: float = Field(default=2.0, description="Universal sampling rate cap.")
    phash_distance: int = Field(
        default=6, description="Max Hamming distance for perceptual-hash dedup."
    )
    ocr_enabled: bool = Field(default=True, description="Run OCR on kept frames.")

    # --- transcription ----------------------------------------------------
    subtitle_langs: str = Field(
        default="en.*", description="yt-dlp --sub-langs pattern for captions."
    )
    local_whisper_enabled: bool = Field(
        default=True, description="Use local faster-whisper as the default fallback."
    )
    whisper_model: str = Field(
        default="auto", description="faster-whisper model size, or 'auto' by RAM/VRAM."
    )
    cloud_stt_enabled: bool = Field(
        default=False,
        description="OPT-IN: allow sending extracted audio to a cloud STT API. "
        "The video file itself NEVER leaves the machine regardless.",
    )
    diarization_enabled: bool = Field(
        default=False,
        description="Label transcript segments by speaker (needs the diarize extra + HF token).",
    )
    huggingface_token: SecretStr | None = Field(
        default=None, description="Hugging Face token for gated pyannote diarization models."
    )

    # --- API keys (provider-scoped; never logged) -------------------------
    anthropic_api_key: SecretStr | None = None
    openai_api_key: SecretStr | None = None
    gemini_api_key: SecretStr | None = None
    mcp_inline_ui: bool = Field(
        default=False,
        description="Attach the viewer page to MCP tool results as a ui:// "
        "resource. Clients that render it (Goose, LibreChat, mcp-ui "
        "inspectors) show a scrubbable timeline inline; the rest ignore the "
        "block. Off by default because it is a large payload most clients "
        "cannot use yet.",
    )

    openrouter_api_key: SecretStr | None = None

    # OpenAI-compatible vendors. Each pairs a key with a base URL so the same
    # entry reaches a regional host, a proxy, or a self-hosted server; the
    # defaults mirror registry.PROVIDERS and a blank value falls back to them.
    groq_api_key: SecretStr | None = None
    groq_base_url: str = ""
    minimax_api_key: SecretStr | None = None
    minimax_base_url: str = ""
    together_api_key: SecretStr | None = None
    together_base_url: str = ""
    fireworks_api_key: SecretStr | None = None
    fireworks_base_url: str = ""
    deepseek_api_key: SecretStr | None = None
    deepseek_base_url: str = ""
    xai_api_key: SecretStr | None = None
    xai_base_url: str = ""
    mistral_api_key: SecretStr | None = None
    mistral_base_url: str = ""
    moonshot_api_key: SecretStr | None = None
    moonshot_base_url: str = ""
    zai_api_key: SecretStr | None = None
    zai_base_url: str = ""
    qwen_api_key: SecretStr | None = None
    qwen_base_url: str = ""
    # `custom` is the escape hatch: any OpenAI-compatible server — vLLM,
    # LM Studio, llama.cpp, LiteLLM, Azure OpenAI, a company gateway.
    custom_api_key: SecretStr | None = None
    custom_base_url: str = ""
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_num_ctx: int = Field(
        default=2048,
        description="Context window for local Ollama vision calls. The compute "
        "buffer scales with it — lower (1024-1536) so small models load on a "
        "low-RAM machine instead of OOMing.",
    )
    ollama_num_gpu: int | None = Field(
        default=None,
        description="GPU layers for Ollama (None = let Ollama auto-detect; 0 = force CPU).",
    )

    # --- vision tiers ------------------------------------------------------
    vision_cheap_provider: str = Field(
        default="anthropic", description="Provider for bulk scene descriptions."
    )
    vision_cheap_model: str = Field(default="claude-haiku-4-5-20251001")
    vision_strong_provider: str = Field(
        default="anthropic", description="Provider for final answers and critiques."
    )
    vision_strong_model: str = Field(default="claude-sonnet-5")
    # --- execution / egress policy -----------------------------------------
    offline: bool = Field(
        default=False,
        description="Hard offline mode: zero outbound network calls, including "
        "source acquisition. A remote URL becomes a structured error unless "
        "the content is already cached locally. Separate from cost_policy, "
        "which governs money rather than data leaving the machine.",
    )
    scene_descriptions: str = Field(
        default="auto",
        description="Where indexing-time scene descriptions run: 'off', "
        "'local', 'cloud', or 'auto'. 'auto' never upgrades to cloud on its "
        "own — a configured API key is not consent to upload every frame.",
    )
    provider_allowlist: str = Field(
        default="",
        description="Comma-separated providers that may be called at all. "
        "Empty = any configured provider.",
    )
    cost_ceiling_usd: float = Field(
        default=1.0, description="Warn/abort ceiling for a single cloud vision call."
    )
    cost_ceiling_run_usd: float = Field(
        default=5.0,
        description="Ceiling for everything ONE run spends — indexing "
        "descriptions, answers, loop critics, library synthesis, extraction "
        "and verification together, not just follow-up questions.",
    )
    cost_policy: str = Field(
        default="cheapest",
        description="THE COST POLICY for answer verify passes: 'cheapest' "
        "(cheapest path that clears confidence wins), 'quality_first' "
        "(straight to the strong tier), or 'offline_only' (only keyless/"
        "local providers — cloud never sees a frame).",
    )
    ocr_backend: str = Field(
        default="auto",
        description="OCR backend policy: 'auto' (RapidOCR, with tesseract "
        "auto-routed only for scripts RapidOCR cannot read — Lao/Khmer/"
        "Myanmar/Tibetan), or force 'rapidocr' / 'tesseract' / 'surya'.",
    )
    embedding_model: str | None = Field(
        default=None,
        description="Opt-in retrieval upgrade for NEW indexes: a fastembed "
        "model name (e.g. 'BAAI/bge-m3' or 'intfloat/multilingual-e5-large'). "
        "Existing indexes keep the model pinned in their meta — vectors from "
        "two models never mix. The big models want ~2 GB+ RAM: not for the "
        "8 GB reference machine.",
    )
    webhook_url: str | None = Field(
        default=None,
        description="POST every monitor event here as JSON (n8n/Zapier/your "
        "endpoint). At-least-once, 3 attempts with backoff; events.jsonl is "
        "written regardless.",
    )
    webhook_secret: SecretStr | None = Field(
        default=None,
        description="When set, events carry X-WatchSkill-Signature: "
        "sha256=<HMAC-SHA256 of the body> for receiver-side verification.",
    )
    vision_batch_size: int = Field(
        default=8,
        description="Frames per describe_frames call. Lower (2-4) for small local models.",
    )
    vision_timeout_seconds: float = Field(
        default=180.0, description="HTTP timeout for cloud vision calls."
    )
    vision_local_timeout_seconds: float = Field(
        default=900.0,
        description="Timeout for local (Ollama) vision calls — CPU model loads take minutes.",
    )
    critic_frame_cap: int = Field(
        default=10,
        description="Max frames sent to the loop critic in one call. Lower (4) for local models.",
    )

    retrieval_ocr_dedup_enabled: bool = Field(
        default=True,
        description="Collapse runs of near-identical OCR from one persistent "
        "on-screen text into a single representative hit before evidence is "
        "selected. Without it a static caption read on a dozen adjacent "
        "frames competes for a dozen top-K slots and crowds out transcript.",
    )
    retrieval_ocr_dedup_window_seconds: float = Field(
        default=10.0,
        description="Gap tolerance when chaining OCR readings into one "
        "occurrence. Consecutive readings closer than this continue the same "
        "run, so a caption held for a minute is one cluster while the same "
        "text recurring later stays a separate occurrence.",
    )
    retrieval_ocr_dedup_similarity: float = Field(
        default=0.88,
        description="How alike two normalized OCR reads must be to count as "
        "the same text. Below 1.0 so recognition noise ('decislon' for "
        "'decision') clusters, high enough that different nearby captions "
        "stay distinct.",
    )

    # --- self-healing answers (v0.6) ----------------------------------------
    answer_confidence_floor: float = Field(
        default=0.35,
        description="Below this after the full escalation ladder, the answer "
        "states plainly that the video does not clearly show it (honest floor).",
    )
    answer_confidence_target: float = Field(
        default=0.6,
        description="Escalation stops as soon as confidence clears this bar.",
    )
    answer_verify_enabled: bool = Field(
        default=True,
        description="When a vision provider is configured, show the model the "
        "frames it is about to cite and require confirmation before answering.",
    )
    answer_token_budget: int = Field(
        default=8000,
        description="Per-question token ceiling; the escalation ladder stops "
        "(and says so) rather than exceed it.",
    )
    answer_deadline_seconds: float = Field(
        default=25.0,
        description="Wall-clock ceiling for one ask. The model-free escalation "
        "rungs cost 0 tokens, so the token budget cannot bound them — this "
        "does. A rung is skipped (and the answer says `deadline_stopped`) "
        "rather than overrun an interactive MCP client's timeout. Raise it "
        "for batch/offline use where latency does not matter.",
    )
    answer_step_reserve_seconds: float = Field(
        default=6.0,
        description="Headroom a single escalation rung must have left before "
        "it may start, so a rung cannot begin a unit of work it has no time "
        "to finish. Sized from a measured zoom-crop re-OCR frame.",
    )
    answer_resample_seconds_per_frame: float = Field(
        default=2.5,
        description="Starting estimate for one dense-resample frame (ffmpeg "
        "extract + OCR + indexing) on a CPU box. Used to size a resample "
        "window to the time actually left, so one window cannot overrun the "
        "deadline it was checked against; refined per process from what "
        "windows actually cost on this machine.",
    )
    answer_escalation_warmup_seconds: float = Field(
        default=40.0,
        description="One-off cost of the FIRST escalation in a process: the "
        "OCR engine is a per-process singleton, so window one pays a model "
        "load later windows do not. Counted against the deadline, which is "
        "why a fresh server's first ask answers from the index alone.",
    )
    answer_resample_width: float = Field(
        default=8.0,
        description="Window (seconds) around a candidate timestamp for the "
        "dense re-sampling escalation step.",
    )
    answer_resample_resolution: int = Field(
        default=1024,
        description="Frame width (px) for escalation re-sampling — higher than "
        "the indexing default so zoom crops have pixels to work with.",
    )
    answer_cache_enabled: bool = Field(
        default=True, description="Semantic answer cache (per video)."
    )
    answer_cache_similarity: float = Field(
        default=0.92,
        description="Cosine similarity above which a cached question counts as "
        "a repeat and its answer is returned at zero model cost.",
    )
    lessons_enabled: bool = Field(
        default=True,
        description="Local lessons store: learn from reported mistakes and "
        "inject relevant guidance into future asks. Never uploaded anywhere.",
    )
    lessons_injection_token_cap: int = Field(
        default=300,
        description="Max prompt tokens the injected 'learned corrections' "
        "section may consume.",
    )
    lessons_max_count: int = Field(
        default=500,
        description="Global cap on stored lessons; least-recently-used pruned.",
    )

    # --- surfaces ----------------------------------------------------------
    response_frame_cap: int = Field(
        default=12, description="Max image blocks per MCP/REST response."
    )
    api_bearer_token: SecretStr | None = Field(
        default=None, description="Bearer token for the REST API. None = local only."
    )

    # --- derived paths ------------------------------------------------------
    @property
    def resolved_bin_dir(self) -> Path:
        """Managed binaries dir (created on demand by health.binaries)."""
        return self.bin_dir if self.bin_dir is not None else self.data_dir / "bin"

    @property
    def cache_dir(self) -> Path:
        return self.data_dir / "cache"

    @property
    def index_path(self) -> Path:
        return self.data_dir / "index.db"

    @property
    def loops_dir(self) -> Path:
        return self.data_dir / "loops"

    @property
    def health_log_path(self) -> Path:
        return self.data_dir / "health.jsonl"

    @property
    def lessons_path(self) -> Path:
        return self.data_dir / "lessons.db"

    @property
    def evals_dir(self) -> Path:
        return self.data_dir / "evals"


def _migrate_legacy_data_dir(settings: Settings) -> None:
    """One-time move of a pre-rename ``~/.agentvision/`` dir to ``~/.watch-skill/``.

    Only fires for the default data dir: an explicit WATCHSKILL_DATA_DIR (or
    an already-populated new dir) is never touched.
    """
    if settings.data_dir != Path.home() / ".watch-skill":
        return
    legacy = Path.home() / ".agentvision"
    if legacy.is_dir() and not settings.data_dir.exists():
        import shutil  # noqa: PLC0415

        shutil.move(str(legacy), str(settings.data_dir))


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Process-wide settings singleton. Tests call :func:`reset_settings`."""
    settings = Settings()
    _migrate_legacy_data_dir(settings)
    return settings


def reset_settings() -> None:
    """Clear the cached settings (tests / after env mutation)."""
    get_settings.cache_clear()
    # The effective policy is derived from settings, so a stale policy after a
    # settings change would be a security bug, not a caching quirk.
    from watch_skill.policy import reset_policy  # noqa: PLC0415

    reset_policy()


def redact_secret_value(key: str, val: str) -> str:
    """Mask secret strings (e.g. gsk_****abcd) to avoid accidental leakage."""
    upper = key.upper()
    if any(secret_term in upper for secret_term in ("KEY", "TOKEN", "SECRET", "PASSWORD")):
        if not val:
            return ""
        if len(val) > 8:
            return f"{val[:4]}****{val[-4:]}"
        return "****"
    return val


def set_config_value(
    key: str,
    value: str,
    target_file: Path | None = None,
) -> tuple[str, str | None]:
    """Set a configuration key/value in the global environment file.

    Returns (normalized_key, override_source | None).
    override_source is populated if process environment or CWD/.env currently shadows this key.
    """
    raw_key = key.strip()
    if not re.match(r"^[A-Za-z0-9_]+$", raw_key):
        from watch_skill.errors import ConfigError

        raise ConfigError(
            f"invalid config key: '{key}'",
            code="config.invalid_key",
            fix="keys must contain only letters, numbers, and underscores (e.g. GROQ_API_KEY)",
        )

    norm_key = raw_key.upper()
    if not norm_key.startswith("WATCHSKILL_"):
        norm_key = f"WATCHSKILL_{norm_key}"

    dest = target_file if target_file is not None else global_env_file()
    dest.parent.mkdir(parents=True, exist_ok=True)

    clean_val = value.replace("\r", "")
    if any(c in clean_val for c in (' ', '\t', '\n', '"', "'", '=', '#')):
        escaped = clean_val.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
        line_to_write = f'{norm_key}="{escaped}"\n'
    else:
        line_to_write = f'{norm_key}={clean_val}\n'

    lines: list[str] = []
    if dest.is_file():
        try:
            lines = dest.read_text(encoding="utf-8").splitlines(keepends=True)
        except OSError:
            lines = []

    replaced = False
    key_pattern = re.compile(rf"^\s*(?:export\s+)?{re.escape(norm_key)}\s*=", re.IGNORECASE)
    new_lines: list[str] = []
    for line in lines:
        if key_pattern.match(line):
            new_lines.append(line_to_write)
            replaced = True
        else:
            new_lines.append(line)

    if not replaced:
        if new_lines and not new_lines[-1].endswith("\n"):
            new_lines[-1] += "\n"
        new_lines.append(line_to_write)

    # Atomic write
    tmp_fd, tmp_path_str = tempfile.mkstemp(dir=dest.parent, prefix=".env_tmp_")
    tmp_path = Path(tmp_path_str)
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as fh:
            fh.writelines(new_lines)
        if sys.platform != "win32":
            try:
                os.chmod(tmp_path, 0o600)
            except OSError:
                pass
        tmp_path.replace(dest)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise

    reset_settings()

    # Precedence check: is it shadowed?
    short_key = norm_key.removeprefix("WATCHSKILL_")
    if norm_key in os.environ:
        return norm_key, f"process environment (${norm_key})"
    if short_key in os.environ:
        return norm_key, f"process environment (${short_key})"

    cwd_env = Path.cwd() / ".env"
    if cwd_env.is_file() and cwd_env.resolve() != dest.resolve():
        try:
            cwd_text = cwd_env.read_text(encoding="utf-8")
            if re.search(
                rf"^\s*(?:export\s+)?(?:WATCHSKILL_)?{re.escape(short_key)}\s*=",
                cwd_text,
                re.MULTILINE | re.IGNORECASE,
            ):
                return norm_key, "CWD/.env"
        except OSError:
            pass

    return norm_key, None


def _read_env_file_kv(path: Path) -> dict[str, str]:
    """Parse key-value pairs from an env file."""
    res: dict[str, str] = {}
    if not path.is_file():
        return res
    try:
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            m = re.match(r"^(?:export\s+)?([A-Za-z0-9_]+)\s*=\s*(.*)$", line)
            if m:
                k = m.group(1).upper()
                v = m.group(2).strip()
                if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
                    v = v[1:-1]
                res[k] = v
    except OSError:
        pass
    return res


def get_config_value(key: str) -> str | None:
    """Return the effective merged value for a configuration key.

    Settings is the single runtime source of truth. Canonical prefix is WATCHSKILL_.
    """
    clean_key = key.strip().upper()
    short_key = clean_key.removeprefix("WATCHSKILL_")
    canonical_key = f"WATCHSKILL_{short_key}"

    # 1. Check Settings model fields (the engine's runtime source of truth)
    settings = get_settings()
    field_name = short_key.lower()
    if hasattr(settings, field_name):
        val = getattr(settings, field_name)
        if isinstance(val, SecretStr):
            return val.get_secret_value()
        if val is not None:
            return str(val)

    # 2. Check process environment for canonical key
    if canonical_key in os.environ:
        return os.environ[canonical_key]

    # 3. Check CWD/.env
    cwd_kv = _read_env_file_kv(Path.cwd() / ".env")
    if canonical_key in cwd_kv:
        return cwd_kv[canonical_key]

    # 4. Check global env file
    global_kv = _read_env_file_kv(global_env_file())
    if canonical_key in global_kv:
        return global_kv[canonical_key]

    return None


def list_config_values(redact: bool = True) -> list[dict[str, Any]]:
    """List effective config items with key, value, and source (env | cwd | global | default)."""
    settings = get_settings()
    fields = Settings.model_fields

    cwd_keys: set[str] = set()
    cwd_env = Path.cwd() / ".env"
    if cwd_env.is_file():
        try:
            for line in cwd_env.read_text(encoding="utf-8").splitlines():
                m = re.match(r"^\s*(?:export\s+)?(WATCHSKILL_[A-Za-z0-9_]+)\s*=", line, re.IGNORECASE)
                if m:
                    cwd_keys.add(m.group(1).upper())
        except OSError:
            pass

    global_keys: set[str] = set()
    g_env = global_env_file()
    if g_env.is_file():
        try:
            for line in g_env.read_text(encoding="utf-8").splitlines():
                m = re.match(r"^\s*(?:export\s+)?(WATCHSKILL_[A-Za-z0-9_]+)\s*=", line, re.IGNORECASE)
                if m:
                    global_keys.add(m.group(1).upper())
        except OSError:
            pass

    items: list[dict[str, Any]] = []
    for field_name, _field_info in fields.items():
        env_key = f"WATCHSKILL_{field_name.upper()}"

        val = getattr(settings, field_name)
        raw_val = (
            val.get_secret_value()
            if isinstance(val, SecretStr)
            else ("" if val is None else str(val))
        )

        if env_key in os.environ:
            source = "env"
        elif env_key in cwd_keys:
            source = "cwd"
        elif env_key in global_keys:
            source = "global"
        else:
            source = "default"

        display_val = redact_secret_value(env_key, raw_val) if redact else raw_val
        items.append({
            "key": env_key,
            "field": field_name,
            "value": display_val,
            "source": source,
        })
    return sorted(items, key=lambda x: x["key"])
