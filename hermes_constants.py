"""Shared constants for Mavis.

Import-safe module with no dependencies — can be imported from anywhere
without risk of circular imports.
"""

import os
import shutil
from pathlib import Path

APP_NAME = "Mavis"
CLI_NAME = "mavis"
HOME_ENV_VAR = "MAVIS_HOME"
LEGACY_HOME_ENV_VAR = "HERMES_HOME"
OPTIONAL_SKILLS_ENV_VAR = "MAVIS_OPTIONAL_SKILLS"
LEGACY_OPTIONAL_SKILLS_ENV_VAR = "HERMES_OPTIONAL_SKILLS"
DEFAULT_HOME_DIRNAME = ".mavis"
LEGACY_HOME_DIRNAME = ".hermes"
HOME_IMPORT_SENTINEL = ".imported_from_hermes"


def _default_home() -> Path:
    return Path.home() / DEFAULT_HOME_DIRNAME


def _legacy_home() -> Path:
    return Path.home() / LEGACY_HOME_DIRNAME


def _sync_home_env(home: Path) -> None:
    os.environ[HOME_ENV_VAR] = str(home)
    os.environ.setdefault(LEGACY_HOME_ENV_VAR, str(home))


def _import_legacy_home(default_home: Path) -> None:
    legacy_home = _legacy_home()
    if default_home.exists() or not legacy_home.exists():
        return

    try:
        shutil.copytree(legacy_home, default_home, dirs_exist_ok=True)
        (default_home / HOME_IMPORT_SENTINEL).write_text(
            f"Imported from {legacy_home}\n",
            encoding="utf-8",
        )
    except OSError:
        # Migration is best-effort; the caller still gets ~/.mavis as the
        # canonical path and can initialize a fresh home there if needed.
        pass


_profile_fallback_warned: bool = False


def get_hermes_home() -> Path:
    """Return the Mavis home directory (default: ~/.mavis).

    Resolution order:
    1. ``MAVIS_HOME``
    2. ``HERMES_HOME`` (legacy compatibility)
    3. ``~/.mavis`` default, with a one-time import from ``~/.hermes`` when
       the new directory does not exist yet.

    The resolved path is mirrored back into both env vars so older modules
    that still read ``HERMES_HOME`` continue to behave correctly.
    """
    explicit_mavis_home = os.getenv(HOME_ENV_VAR, "").strip()
    explicit_legacy_home = os.getenv(LEGACY_HOME_ENV_VAR, "").strip()
    default_home = _default_home()

    if explicit_mavis_home and explicit_legacy_home:
        mavis_home = Path(explicit_mavis_home).expanduser()
        legacy_home = Path(explicit_legacy_home).expanduser()
        # If MAVIS_HOME only contains the auto-default while the legacy env var
        # was explicitly pointed elsewhere, prefer the explicit legacy override.
        home = legacy_home if mavis_home == default_home and legacy_home != default_home else mavis_home
        _sync_home_env(home)
        return home

    explicit_home = explicit_mavis_home or explicit_legacy_home
    if explicit_home:
        home = Path(explicit_home).expanduser()
        _sync_home_env(home)
        return home

    home = default_home
    _import_legacy_home(home)
    _sync_home_env(home)
    return home
