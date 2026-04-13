from pathlib import Path
import tomllib


REPO_ROOT = Path(__file__).resolve().parents[1]


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
