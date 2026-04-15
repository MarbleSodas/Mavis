from pathlib import Path
import tomllib


REPO_ROOT = Path(__file__).resolve().parents[1]


# Keep this curated and high-signal. The goal is to guard the user-facing/runtime
# cutover surfaces from issues #1-#4 without flagging intentional internal
# compatibility names such as get_hermes_home(), hermes_cli, or hermes-* toolsets.
# If one of these files must intentionally retain a legacy literal, add the
# smallest exact-string exception to that file's allowlist instead of weakening
# the denylist globally.
CURATED_REBRAND_GUARDS = {
    "run_agent.py": {
        "forbidden": (
            "for Hermes-managed OAuth/setup tokens",
        ),
    },
    "tools/mcp_oauth.py": {
        "forbidden": (
            "~/.hermes",
            "HERMES_HOME",
        ),
    },
    "tools/mcp_tool.py": {
        "forbidden": (
            "~/.hermes/config.yaml",
        ),
    },
    "tools/transcription_tools.py": {
        "forbidden": (
            "HERMES_LOCAL_STT_COMMAND",
            "HERMES_LOCAL_STT_LANGUAGE",
        ),
    },
    "tools/tts_tool.py": {
        "forbidden": (
            "~/.hermes/config.yaml",
            "Run hermes setup",
        ),
    },
    "gateway/pairing.py": {
        "forbidden": (
            "~/.hermes/platforms/pairing/",
        ),
    },
    "gateway/sticker_cache.py": {
        "forbidden": (
            "~/.hermes/sticker_cache.json",
        ),
    },
    "plugins/memory/honcho/client.py": {
        "forbidden": (
            "HOST = \"hermes\"",
            "HERMES_HONCHO_HOST",
            "~/.hermes/honcho.json",
            "workspace_id: str = \"hermes\"",
            "ai_peer: str = \"hermes\"",
            "hermes honcho setup",
        ),
    },
    "plugins/memory/honcho/__init__.py": {
        "forbidden": (
            "hermes-default",
            "$HERMES_HOME/honcho.json",
        ),
    },
    "plugins/memory/honcho/session.py": {
        "forbidden": (
            "hermes-assistant",
            "~/.hermes/memories/",
            "Runs alongside hermes' existing SQLite state",
            "Apply Hermes-side char cap before caching",
            "so Hermes knows itself",
        ),
    },
    "plugins/memory/honcho/cli.py": {
        "forbidden": (
            "hermes honcho",
            "hermes update",
            "$HERMES_HOME/honcho.json",
            "Honcho gives Hermes persistent cross-session memory.",
        ),
    },
    "plugins/memory/honcho/README.md": {
        "forbidden": (
            "Hermes",
            "integrations/hermes",
        ),
    },
    ".github/workflows/docker-publish.yml": {
        "forbidden": (
            "NousResearch/hermes-agent",
            "nousresearch/hermes-agent",
            "/tmp/hermes-test",
            "/opt/hermes/docker/entrypoint.sh",
            "Docker Hub",
        ),
    },
    ".github/workflows/deploy-site.yml": {
        "forbidden": (
            "NousResearch/hermes-agent",
            "hermes-agent.nousresearch.com",
            "CNAME",
        ),
    },
    "Dockerfile": {
        "forbidden": (
            "/opt/hermes",
            "ENV HERMES_HOME=/opt/data",
        ),
    },
    "docker/entrypoint.sh": {
        "forbidden": (
            "HERMES_HOME=\"/opt/data\"",
            "/opt/hermes",
            "exec hermes",
        ),
    },
}

CURATED_ALLOWLISTS = {
    # Upstream Honcho docs still publish the integration guide at this legacy URL.
    "plugins/memory/honcho/README.md": (
        "https://docs.honcho.dev/v3/guides/integrations/hermes",
        "historical Hermes integration name",
    ),
}


def _strip_allowed_literals(text: str, allowed: tuple[str, ...]) -> str:
    for literal in allowed:
        text = text.replace(literal, "")
    return text


def test_readme_uses_explicit_migration_not_automatic_compatibility():
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")

    assert "mavis migrate-hermes" in readme
    assert "copied into `~/.mavis` on first run" not in readme
    assert "HERMES_HOME" not in readme


def test_project_description_no_longer_positions_mavis_as_hermes_wrapper():
    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    description = pyproject["project"]["description"]
    assert "Hermes Agent" not in description


def test_public_wrappers_and_packaging_are_mavis_only():
    gateway_wrapper = (REPO_ROOT / "scripts" / "mavis-gateway").read_text(encoding="utf-8")
    install_cmd = (REPO_ROOT / "scripts" / "install.cmd").read_text(encoding="utf-8")
    whatsapp_bridge = (REPO_ROOT / "scripts" / "whatsapp-bridge" / "bridge.js").read_text(encoding="utf-8")
    homebrew_formula = (REPO_ROOT / "packaging" / "homebrew" / "mavis-agent.rb").read_text(encoding="utf-8")
    mcp_server = (REPO_ROOT / "mcp_serve.py").read_text(encoding="utf-8")
    launcher = (REPO_ROOT / "mavis").read_text(encoding="utf-8")

    assert "Hermes Agent" not in gateway_wrapper
    assert "~/.hermes" not in gateway_wrapper
    assert "Hermes Agent" not in install_cmd
    assert "NousResearch/hermes-agent" not in install_cmd
    assert "Hermes Agent" not in whatsapp_bridge
    assert "~/.hermes" not in whatsapp_bridge
    assert "HERMES_OPTIONAL_SKILLS" not in homebrew_formula
    assert "HERMES_MANAGED" not in homebrew_formula
    assert '"hermes"' not in mcp_server
    assert "hermes-agent[mcp]" not in mcp_server
    assert "Hermes Agent CLI launcher" not in launcher

    assert not (REPO_ROOT / "hermes").exists()
    assert not (REPO_ROOT / "packaging" / "homebrew" / "hermes-agent.rb").exists()


def test_curated_rebrand_cutover_files_do_not_regress():
    failures: list[str] = []

    for rel_path, rule in CURATED_REBRAND_GUARDS.items():
        raw_text = (REPO_ROOT / rel_path).read_text(encoding="utf-8")
        text = _strip_allowed_literals(raw_text, CURATED_ALLOWLISTS.get(rel_path, ()))

        for forbidden in rule["forbidden"]:
            if forbidden in text:
                failures.append(f"{rel_path}: found forbidden legacy string {forbidden!r}")

    assert not failures, "Curated rebrand regression(s) detected:\n" + "\n".join(failures)
