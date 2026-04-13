"""Explicit migration from a legacy Hermes home into Mavis."""

from __future__ import annotations

import json
import shutil
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from hermes_constants import (
    APP_NAME,
    CLI_NAME,
    display_hermes_home,
    get_hermes_home,
    get_legacy_hermes_home,
)


@dataclass(frozen=True)
class MigrationItem:
    relative_path: str
    label: str


@dataclass
class MigrationResult:
    relative_path: str
    label: str
    status: str
    detail: str


_MIGRATION_ITEMS: tuple[MigrationItem, ...] = (
    MigrationItem("config.yaml", "Config"),
    MigrationItem(".env", "Environment"),
    MigrationItem("auth.json", "Auth store"),
    MigrationItem("SOUL.md", "Identity"),
    MigrationItem("BOOT.md", "Boot instructions"),
    MigrationItem("state.db", "Session database"),
    MigrationItem("state.db-shm", "Session database shm"),
    MigrationItem("state.db-wal", "Session database wal"),
    MigrationItem("sessions", "Sessions"),
    MigrationItem("memories", "Memories"),
    MigrationItem("skills", "Skills"),
    MigrationItem("plugins", "Plugins"),
    MigrationItem("skins", "Skins"),
    MigrationItem("hooks", "Hooks"),
    MigrationItem("pairing", "Pairing state"),
    MigrationItem("cron", "Cron state"),
    MigrationItem("tts", "Voice assets"),
    MigrationItem("audio_cache", "Audio cache"),
    MigrationItem("gateway_voice_mode.json", "Gateway voice mode"),
    MigrationItem("gateway.pid", "Gateway pid"),
    MigrationItem("gateway_state.json", "Gateway runtime state"),
    MigrationItem("processes.json", "Gateway process state"),
    MigrationItem("whatsapp", "Messaging session state"),
    MigrationItem("mcp-tokens", "MCP OAuth tokens"),
    MigrationItem("sticker_cache.json", "Sticker cache"),
)


def _timestamp_slug() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def _resolve_source_home(raw_source: str | None) -> Path:
    if raw_source:
        return Path(raw_source).expanduser()
    return get_legacy_hermes_home()


def _report_dir(dest_home: Path) -> Path:
    return dest_home / "migration" / "hermes" / _timestamp_slug()


def _paths_match(a: Path, b: Path) -> bool:
    try:
        return a.resolve() == b.resolve()
    except OSError:
        return a.absolute() == b.absolute()


def _copy_path(src: Path, dest: Path, *, overwrite: bool, dry_run: bool) -> tuple[str, str]:
    if not src.exists():
        return "missing", "source not present"

    if dest.exists():
        if not overwrite:
            return "skipped", "destination already exists"
        if dry_run:
            return "would-overwrite", "destination would be replaced"
        if dest.is_dir() and not dest.is_symlink():
            shutil.rmtree(dest)
        else:
            dest.unlink()
    elif dry_run:
        return "would-copy", "destination will be created"

    if dry_run:
        return "would-copy", "destination will be created"

    dest.parent.mkdir(parents=True, exist_ok=True)
    if src.is_dir():
        shutil.copytree(src, dest)
    else:
        shutil.copy2(src, dest)
    return "copied", "copied successfully"


def _write_report(
    report_dir: Path,
    *,
    source_home: Path,
    dest_home: Path,
    overwrite: bool,
    dry_run: bool,
    results: Iterable[MigrationResult],
) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)
    results_list = list(results)
    summary = {
        "app": APP_NAME,
        "source_home": str(source_home),
        "destination_home": str(dest_home),
        "overwrite": overwrite,
        "dry_run": dry_run,
        "results": [asdict(result) for result in results_list],
    }
    (report_dir / "summary.json").write_text(
        json.dumps(summary, indent=2) + "\n",
        encoding="utf-8",
    )

    lines = [
        f"# {APP_NAME} Hermes Migration Report",
        "",
        f"- Source: `{source_home}`",
        f"- Destination: `{dest_home}`",
        f"- Mode: `{'dry-run' if dry_run else 'execute'}`",
        f"- Overwrite: `{'yes' if overwrite else 'no'}`",
        "",
        "| Item | Status | Detail |",
        "| --- | --- | --- |",
    ]
    for result in results_list:
        lines.append(f"| {result.label} | {result.status} | {result.detail} |")
    (report_dir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _confirm_execute(source_home: Path, dest_home: Path, *, dry_run: bool, assume_yes: bool) -> None:
    if dry_run or assume_yes:
        return
    if not sys.stdin.isatty():
        print(
            f"Error: '{CLI_NAME} migrate-hermes' needs confirmation in an interactive terminal.",
            file=sys.stderr,
        )
        print(f"Re-run with '--yes' to skip the prompt.", file=sys.stderr)
        raise SystemExit(1)

    print(f"Source:      {source_home}")
    print(f"Destination: {dest_home}")
    reply = input("Continue importing legacy Hermes data into Mavis? [y/N] ").strip().lower()
    if reply not in {"y", "yes"}:
        print("Migration cancelled.")
        raise SystemExit(0)


def migrate_hermes_command(args) -> None:
    """Run a one-time import from a legacy Hermes home."""
    source_home = _resolve_source_home(getattr(args, "source", None))
    dest_home = get_hermes_home()

    if not source_home.exists():
        print(f"Legacy Hermes home not found: {source_home}", file=sys.stderr)
        raise SystemExit(1)
    if _paths_match(source_home, dest_home):
        print("Refusing to migrate because source and destination are the same path.", file=sys.stderr)
        raise SystemExit(1)

    dry_run = bool(getattr(args, "dry_run", False))
    overwrite = bool(getattr(args, "overwrite", False))
    assume_yes = bool(getattr(args, "yes", False))

    _confirm_execute(source_home, dest_home, dry_run=dry_run, assume_yes=assume_yes)

    dest_home.mkdir(parents=True, exist_ok=True)

    results: list[MigrationResult] = []
    for item in _MIGRATION_ITEMS:
        src = source_home / item.relative_path
        dest = dest_home / item.relative_path
        status, detail = _copy_path(src, dest, overwrite=overwrite, dry_run=dry_run)
        results.append(
            MigrationResult(
                relative_path=item.relative_path,
                label=item.label,
                status=status,
                detail=detail,
            )
        )

    report_dir = _report_dir(dest_home)
    _write_report(
        report_dir,
        source_home=source_home,
        dest_home=dest_home,
        overwrite=overwrite,
        dry_run=dry_run,
        results=results,
    )

    copied = sum(result.status == "copied" for result in results)
    skipped = sum(result.status == "skipped" for result in results)
    missing = sum(result.status == "missing" for result in results)
    planned = sum(result.status.startswith("would-") for result in results)

    print(f"{APP_NAME} legacy import {'preview' if dry_run else 'completed'}.")
    print(f"  Source:      {source_home}")
    print(f"  Destination: {display_hermes_home()}")
    print(f"  Report:      {report_dir}")
    if dry_run:
        print(f"  Planned:     {planned}")
    else:
        print(f"  Copied:      {copied}")
    print(f"  Skipped:     {skipped}")
    print(f"  Missing:     {missing}")
    if dry_run:
        print(f"Run '{CLI_NAME} migrate-hermes --yes{' --overwrite' if overwrite else ''}' to execute.")
