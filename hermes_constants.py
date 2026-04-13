"""Shared constants for Mavis.

Import-safe module with no dependencies — can be imported from anywhere
without risk of circular imports.
"""

import os
from pathlib import Path

APP_NAME = "Mavis"
CLI_NAME = "mavis"
HOME_ENV_VAR = "MAVIS_HOME"
LEGACY_HOME_ENV_VAR = "HERMES_HOME"
OPTIONAL_SKILLS_ENV_VAR = "MAVIS_OPTIONAL_SKILLS"
LEGACY_OPTIONAL_SKILLS_ENV_VAR = "HERMES_OPTIONAL_SKILLS"
DEFAULT_HOME_DIRNAME = ".mavis"
LEGACY_HOME_DIRNAME = ".hermes"


def _default_home() -> Path:
    return Path.home() / DEFAULT_HOME_DIRNAME


def _legacy_home() -> Path:
    return Path.home() / LEGACY_HOME_DIRNAME


def get_legacy_hermes_home() -> Path:
    """Return the legacy Hermes home path used by explicit migration flows."""
    return _legacy_home()


def get_hermes_home() -> Path:
    """Return the Mavis home directory (default: ~/.mavis).

    Resolution order:
    1. ``MAVIS_HOME``
    2. ``~/.mavis``

    Legacy Hermes paths are intentionally ignored here.  Existing Hermes state
    is only imported through the explicit ``mavis migrate-hermes`` command.
    """
    explicit_mavis_home = os.getenv(HOME_ENV_VAR, "").strip()
    if explicit_mavis_home:
        return Path(explicit_mavis_home).expanduser()
    return _default_home()


def get_optional_skills_dir(default: Path | None = None) -> Path:
    """Return the optional-skills directory, honoring package-manager wrappers.

    Packaged installs may ship ``optional-skills`` outside the Python package
    tree and expose it via ``MAVIS_OPTIONAL_SKILLS``.
    """
    override = os.getenv(OPTIONAL_SKILLS_ENV_VAR, "").strip()
    if override:
        return Path(override)
    if default is not None:
        return default
    return get_hermes_home() / "optional-skills"


def get_hermes_dir(new_subpath: str, old_name: str) -> Path:
    """Resolve a Mavis state subdirectory with backward compatibility.

    New installs get the consolidated layout (e.g. ``cache/images``).
    Existing installs that already have the old path (e.g. ``image_cache``)
    keep using it — no migration required.

    Args:
        new_subpath: Preferred path relative to the Mavis home directory
            (e.g. ``"cache/images"``).
        old_name: Legacy path relative to the Mavis home directory
            (e.g. ``"image_cache"``).

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
