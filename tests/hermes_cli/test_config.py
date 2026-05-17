"""Tests for hermes_cli configuration management."""

import os
from pathlib import Path
from unittest.mock import patch, MagicMock

import yaml

from hermes_cli.config import (
    DEFAULT_CONFIG,
    get_hermes_home,
    ensure_hermes_home,
    get_compatible_custom_providers,
    load_config,
    load_env,
    migrate_config,
    remove_env_value,
    save_config,
    save_env_value,
    save_env_value_secure,
    sanitize_env_file,
    _sanitize_env_lines,
)


class TestGetHermesHome:
    def test_default_path(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("MAVIS_HOME", None)
            os.environ.pop("HERMES_HOME", None)
            home = get_hermes_home()
            assert home == Path.home() / ".mavis"

    def test_mavis_home_override(self):
        with patch.dict(os.environ, {"MAVIS_HOME": "/custom/path"}):
            home = get_hermes_home()
            assert home == Path("/custom/path")

    def test_legacy_env_override(self):
        with patch.dict(os.environ, {"HERMES_HOME": "/legacy/path"}, clear=False):
            os.environ.pop("MAVIS_HOME", None)
            home = get_hermes_home()
            assert home == Path("/legacy/path")

    def test_imports_legacy_home_into_mavis(self, tmp_path):
        legacy_home = tmp_path / ".hermes"
        default_home = tmp_path / ".mavis"
        legacy_home.mkdir()
        (legacy_home / "config.yaml").write_text("model: test\n", encoding="utf-8")

        with patch("pathlib.Path.home", return_value=tmp_path), patch.dict(os.environ, {}, clear=True):
            home = get_hermes_home()

        assert home == default_home
        assert (default_home / "config.yaml").read_text(encoding="utf-8") == "model: test\n"
        assert (default_home / ".imported_from_hermes").exists()


class TestEnsureHermesHome:
    def test_creates_subdirs(self, tmp_path):
        with patch.dict(os.environ, {"HERMES_HOME": str(tmp_path)}):
            ensure_hermes_home()
            assert (tmp_path / "cron").is_dir()
            assert (tmp_path / "sessions").is_dir()
            assert (tmp_path / "logs").is_dir()
            assert (tmp_path / "memories").is_dir()

    def test_creates_default_soul_md_if_missing(self, tmp_path):
        with patch.dict(os.environ, {"HERMES_HOME": str(tmp_path)}):
            ensure_hermes_home()
            soul_path = tmp_path / "SOUL.md"
            assert soul_path.exists()
            assert soul_path.read_text(encoding="utf-8").strip() != ""

    def test_does_not_overwrite_existing_soul_md(self, tmp_path):
        with patch.dict(os.environ, {"HERMES_HOME": str(tmp_path)}):
            soul_path = tmp_path / "SOUL.md"
            soul_path.write_text("custom soul", encoding="utf-8")
            ensure_hermes_home()
            assert soul_path.read_text(encoding="utf-8") == "custom soul"


class TestLoadConfigDefaults:
    def test_returns_defaults_when_no_file(self, tmp_path):
        with patch.dict(os.environ, {"HERMES_HOME": str(tmp_path)}):
            config = load_config()
            assert config["model"] == DEFAULT_CONFIG["model"]
            assert config["agent"]["max_turns"] == DEFAULT_CONFIG["agent"]["max_turns"]
            assert "max_turns" not in config
            assert "terminal" in config
            assert config["terminal"]["backend"] == "local"
            assert config["voice"]["auto_tts"] is True
            assert config["voice"]["ready"] is False
