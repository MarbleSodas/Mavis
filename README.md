# Mavis

Mavis is a voice-first agent harness with local-first speech defaults built in.

This repository ships the agent loop, gateway, sessions, cron, ACP integration, plugins, and tools as its foundation. The earlier Tauri/Vue prototype has been removed.

## What Changed

- Upstream base: pinned to `v2026.4.8`
- Primary commands: `mavis`, `mavis-agent`, `mavis-acp`
- Primary config home: `~/.mavis` with `MAVIS_HOME`
- Legacy import: use `mavis migrate-hermes` to copy an existing `~/.hermes` home into `~/.mavis`
- Voice defaults:
  - STT provider: local `faster-whisper`
  - STT model: `small`
  - TTS provider: `piper`
  - CLI voice loop: `/voice on` hotword mode
  - Auto TTS: enabled by default

## Quick Start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[voice-local]"
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

## Speech Stack

Built-in voice support includes:

- always-listening hotword mode (`Hey Mavis, ...`)
- push-to-talk CLI fallback (`/voice ptt`)
- silence detection and barge-in
- sentence-level streaming TTS
- Whisper hallucination filtering
- gateway voice replies for Telegram and Discord
- Discord voice-channel speech loops

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
