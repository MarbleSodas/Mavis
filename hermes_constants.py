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


def get_optional_skills_dir(default: Path | None = None) -> Path:
    """Return the optional-skills directory, honoring package-manager wrappers.

    Packaged installs may ship ``optional-skills`` outside the Python package
    tree and expose it via ``MAVIS_OPTIONAL_SKILLS``.
    """
    override = (
        os.getenv(OPTIONAL_SKILLS_ENV_VAR, "").strip()
        or os.getenv(LEGACY_OPTIONAL_SKILLS_ENV_VAR, "").strip()
    )
    if override:
        return Path(override)
    if default is not None:
        return default
    return get_hermes_home() / "optional-skills"


def get_hermes_dir(new_subpath: str, old_name: str) -> Path:
    """Resolve a Hermes subdirectory with backward compatibility.

    New installs get the consolidated layout (e.g. ``cache/images``).
    Existing installs that already have the old path (e.g. ``image_cache``)
    keep using it — no migration required.

    Args:
        new_subpath: Preferred path relative to HERMES_HOME (e.g. ``"cache/images"``).
        old_name: Legacy path relative to HERMES_HOME (e.g. ``"image_cache"``).

    Returns:
        Absolute ``Path`` — old location if it exists on disk, otherwise the new one.
    """
    home = get_hermes_home()
    old_path = home / old_name
    if old_path.exists():
        return old_path
    return home / new_subpath


def display_hermes_home() -> str:
    """Return a user-friendly display string for the current Mavis home.

    Uses ``~/`` shorthand for readability::

        default:  ``~/.mavis``
        profile:  ``~/.mavis/profiles/coder``
        custom:   ``/opt/mavis-custom``

    Use this in **user-facing** print/log messages instead of hardcoding
    ``~/.mavis``.  For code that needs a real ``Path``, use
    :func:`get_hermes_home` instead.
    """
    home = get_hermes_home()
    try:
        return "~/" + str(home.relative_to(Path.home()))
    except ValueError:
        return str(home)


VALID_REASONING_EFFORTS = ("xhigh", "high", "medium", "low", "minimal")


def parse_reasoning_effort(effort: str) -> dict | None:
    """Parse a reasoning effort level into a config dict.

    Valid levels: "xhigh", "high", "medium", "low", "minimal", "none".
    Returns None when the input is empty or unrecognized (caller uses default).
    Returns {"enabled": False} for "none".
    Returns {"enabled": True, "effort": <level>} for valid effort levels.
    """
    if not effort or not effort.strip():
        return None
    effort = effort.strip().lower()
    if effort == "none":
        return {"enabled": False}
    if effort in VALID_REASONING_EFFORTS:
        return {"enabled": True, "effort": effort}
    return None


OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_MODELS_URL = f"{OPENROUTER_BASE_URL}/models"
OPENROUTER_CHAT_URL = f"{OPENROUTER_BASE_URL}/chat/completions"

AI_GATEWAY_BASE_URL = "https://ai-gateway.vercel.sh/v1"
AI_GATEWAY_MODELS_URL = f"{AI_GATEWAY_BASE_URL}/models"
AI_GATEWAY_CHAT_URL = f"{AI_GATEWAY_BASE_URL}/chat/completions"

NOUS_API_BASE_URL = "https://inference-api.nousresearch.com/v1"
NOUS_API_CHAT_URL = f"{NOUS_API_BASE_URL}/chat/completions"
