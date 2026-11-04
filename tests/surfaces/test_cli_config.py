"""Unit tests for watch-skill config command and precedence rules."""
from pathlib import Path

from typer.testing import CliRunner

from watch_skill.config import (
    redact_secret_value,
    reset_settings,
    set_config_value,
)
from watch_skill.surfaces.cli.main import app

runner = CliRunner()


def test_redact_secret_value():
    assert redact_secret_value("WATCHSKILL_GROQ_API_KEY", "gsk_1234567890abcdef") == "gsk_****cdef"
    assert redact_secret_value("WATCHSKILL_OPENAI_API_KEY", "short") == "****"
    assert redact_secret_value("WATCHSKILL_DATA_DIR", "/path/to/data") == "/path/to/data"
    assert redact_secret_value("WATCHSKILL_FRAME_WIDTH", "512") == "512"


def test_config_set_and_get(tmp_path: Path):
    target = tmp_path / "global.env"
    norm_key, override = set_config_value("TEST_CUSTOM_KEY", "test_value_123", target_file=target)
    assert norm_key == "WATCHSKILL_TEST_CUSTOM_KEY"
    assert target.is_file()
    content = target.read_text(encoding="utf-8")
    assert "WATCHSKILL_TEST_CUSTOM_KEY=test_value_123" in content


def test_config_set_special_characters(tmp_path: Path):
    target = tmp_path / "global.env"
    norm_key, _ = set_config_value("SPACE_KEY", "value with spaces and = sign and \"quotes\"", target_file=target)
    content = target.read_text(encoding="utf-8")
    assert norm_key == "WATCHSKILL_SPACE_KEY"
    assert 'WATCHSKILL_SPACE_KEY="value with spaces and = sign and \\"quotes\\""' in content


def test_config_override_warning(tmp_path: Path, monkeypatch):
    target = tmp_path / "global.env"
    monkeypatch.setenv("WATCHSKILL_OVERRIDDEN_KEY", "from_process_env")
    norm_key, override = set_config_value("OVERRIDDEN_KEY", "from_file", target_file=target)
    assert override is not None
    assert "process environment" in override


def test_config_cli_commands(tmp_path: Path, monkeypatch):
    target = tmp_path / "global.env"
    monkeypatch.setenv("WATCHSKILL_GLOBAL_ENV_FILE", str(target))
    reset_settings()

    # config set
    res = runner.invoke(app, ["config", "set", "MY_SECRET_KEY", "gsk_supersecretvalue99", "--json"])
    assert res.exit_code == 0
    assert '"ok": true' in res.stdout
    assert '"command": "config.set"' in res.stdout

    # config get
    res_get = runner.invoke(app, ["config", "get", "MY_SECRET_KEY"])
    assert res_get.exit_code == 0
    assert "gsk_supersecretvalue99" in res_get.stdout

    # config list --json (secrets redacted)
    res_list = runner.invoke(app, ["config", "list", "--json"])
    assert res_list.exit_code == 0
    assert "gsk_supersecretvalue99" not in res_list.stdout

    # config path
    res_path = runner.invoke(app, ["config", "path"])
    assert res_path.exit_code == 0
    assert str(target) in res_path.stdout
