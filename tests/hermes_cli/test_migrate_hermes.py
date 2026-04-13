from argparse import Namespace

import pytest

from hermes_cli.migrate_hermes import migrate_hermes_command


def _args(**overrides):
    base = {
        "source": None,
        "dry_run": False,
        "overwrite": False,
        "yes": True,
    }
    base.update(overrides)
    return Namespace(**base)


def test_migrate_hermes_dry_run_does_not_copy_payload(tmp_path, monkeypatch, capsys):
    source = tmp_path / ".hermes"
    source.mkdir()
    (source / "config.yaml").write_text("model: legacy\n", encoding="utf-8")
    (source / "skills").mkdir()
    (source / "skills" / "demo").mkdir()

    dest = tmp_path / ".mavis"
    monkeypatch.setenv("MAVIS_HOME", str(dest))

    migrate_hermes_command(_args(source=str(source), dry_run=True))

    assert not (dest / "config.yaml").exists()
    report_root = dest / "migration" / "hermes"
    reports = list(report_root.iterdir())
    assert len(reports) == 1
    assert (reports[0] / "report.md").exists()

    output = capsys.readouterr().out
    assert "preview" in output
    assert "Planned:" in output


def test_migrate_hermes_copies_selected_state(tmp_path, monkeypatch):
    source = tmp_path / ".hermes"
    source.mkdir()
    (source / "config.yaml").write_text("model: legacy\n", encoding="utf-8")
    (source / ".env").write_text("OPENAI_API_KEY=test\n", encoding="utf-8")
    (source / "state.db").write_text("db", encoding="utf-8")
    (source / "skills").mkdir()
    (source / "skills" / "demo").mkdir()
    (source / "skills" / "demo" / "SKILL.md").write_text("# Demo\n", encoding="utf-8")

    dest = tmp_path / ".mavis"
    monkeypatch.setenv("MAVIS_HOME", str(dest))

    migrate_hermes_command(_args(source=str(source)))

    assert (dest / "config.yaml").read_text(encoding="utf-8") == "model: legacy\n"
    assert (dest / ".env").read_text(encoding="utf-8") == "OPENAI_API_KEY=test\n"
    assert (dest / "state.db").read_text(encoding="utf-8") == "db"
    assert (dest / "skills" / "demo" / "SKILL.md").exists()


def test_migrate_hermes_skips_existing_paths_without_overwrite(tmp_path, monkeypatch):
    source = tmp_path / ".hermes"
    source.mkdir()
    (source / "config.yaml").write_text("model: legacy\n", encoding="utf-8")

    dest = tmp_path / ".mavis"
    dest.mkdir()
    (dest / "config.yaml").write_text("model: current\n", encoding="utf-8")
    monkeypatch.setenv("MAVIS_HOME", str(dest))

    migrate_hermes_command(_args(source=str(source)))

    assert (dest / "config.yaml").read_text(encoding="utf-8") == "model: current\n"


def test_migrate_hermes_overwrites_when_requested(tmp_path, monkeypatch):
    source = tmp_path / ".hermes"
    source.mkdir()
    (source / "config.yaml").write_text("model: legacy\n", encoding="utf-8")

    dest = tmp_path / ".mavis"
    dest.mkdir()
    (dest / "config.yaml").write_text("model: current\n", encoding="utf-8")
    monkeypatch.setenv("MAVIS_HOME", str(dest))

    migrate_hermes_command(_args(source=str(source), overwrite=True))

    assert (dest / "config.yaml").read_text(encoding="utf-8") == "model: legacy\n"


def test_migrate_hermes_requires_existing_source(tmp_path, monkeypatch):
    dest = tmp_path / ".mavis"
    monkeypatch.setenv("MAVIS_HOME", str(dest))

    with pytest.raises(SystemExit, match="1"):
        migrate_hermes_command(_args(source=str(tmp_path / ".hermes-missing")))
