# Mavis

Mavis is a direct fork of Hermes Agent, reworked as a voice-first agent harness with Mavis branding and local-first speech defaults built in.

This repository now ships the Hermes agent loop, gateway, sessions, cron, ACP integration, plugins, and tools as its foundation. The earlier Tauri/Vue prototype has been removed.

## What Changed

- Upstream base: `NousResearch/hermes-agent` tag `v2026.4.8`
- Primary commands: `mavis`, `mavis-agent`, `mavis-acp`
- Primary config home: `~/.mavis` with `MAVIS_HOME`
- Legacy import: existing `~/.hermes` state is copied into `~/.mavis` on first run
- Voice defaults:
  - STT provider: local `faster-whisper`
  - STT model: `base`
  - TTS provider: `edge`
  - CLI voice loop: `/voice`
  - Auto TTS: enabled by default

## Quick Start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
mavis setup
mavis
```

## Voice-First Setup

`mavis setup` now performs a first-run voice readiness check for:

- microphone access
- local STT model availability
- TTS dependency availability
- required system binaries such as `ffmpeg`

The result is recorded in `~/.mavis/config.yaml` under `voice.ready` and `voice.last_validation`.

## Core Commands

```bash
mavis                 # interactive CLI
mavis setup           # setup wizard with voice validation
mavis model           # choose provider and model
mavis gateway         # messaging gateway
mavis update          # update this fork
mavis status          # system and config status
mavis-acp             # ACP server for editor integrations
```

## Home Directory

Mavis stores its runtime state in `~/.mavis/` by default:

- `config.yaml`
- `.env`
- `sessions/`
- `logs/`
- `cron/`
- `skills/`

You can override the location with `MAVIS_HOME=/custom/path`.

For compatibility, internal code still understands legacy `HERMES_HOME`, but the public Mavis path is `~/.mavis`.

## Speech Stack

Built-in voice support comes from the upstream Hermes voice pipeline, including:

- push-to-talk CLI voice mode
- silence detection and barge-in
- sentence-level streaming TTS
- Whisper hallucination filtering
- gateway voice replies for Telegram and Discord
- Discord voice-channel speech loops

## Upstream Sync

This repo tracks Hermes as an `upstream` remote for future syncs, but Mavis should be rebased from tagged Hermes releases rather than re-implementing upstream internals by hand.

## Development

```bash
pip install -e ".[all]"
pytest
```

Optional docs site:

```bash
cd website
npm install
npm run start
```
