#!/bin/bash
# Docker entrypoint: bootstrap config files into the mounted volume, then run Mavis.
set -e

MAVIS_HOME="${MAVIS_HOME:-/opt/data}"
export MAVIS_HOME
INSTALL_DIR="/opt/mavis"

# Create essential directory structure.  Cache and platform directories
# (cache/images, cache/audio, platforms/whatsapp, etc.) are created on
# demand by the application — don't pre-create them here so new installs
# get the consolidated layout from get_hermes_dir().
mkdir -p "$MAVIS_HOME"/{cron,sessions,logs,hooks,memories,skills}

# .env
if [ ! -f "$MAVIS_HOME/.env" ]; then
    cp "$INSTALL_DIR/.env.example" "$MAVIS_HOME/.env"
fi

# config.yaml
if [ ! -f "$MAVIS_HOME/config.yaml" ]; then
    cp "$INSTALL_DIR/cli-config.yaml.example" "$MAVIS_HOME/config.yaml"
fi

# SOUL.md
if [ ! -f "$MAVIS_HOME/SOUL.md" ]; then
    cp "$INSTALL_DIR/docker/SOUL.md" "$MAVIS_HOME/SOUL.md"
fi

# Sync bundled skills (manifest-based so user edits are preserved)
if [ -d "$INSTALL_DIR/skills" ]; then
    python3 "$INSTALL_DIR/tools/skills_sync.py"
fi

exec mavis "$@"
