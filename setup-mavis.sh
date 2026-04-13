#!/bin/bash
# ============================================================================
# Mavis Setup Script
# ============================================================================
# Quick setup for developers who cloned the repo manually.
# Uses uv for fast Python provisioning and package management.
#
# Usage:
#   ./setup-mavis.sh
# ============================================================================

set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[0;33m'
CYAN='\033[0;36m'
RED='\033[0;31m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

PYTHON_VERSION="3.11"
MAVIS_HOME="${MAVIS_HOME:-$HOME/.mavis}"

echo ""
echo -e "${CYAN}Mavis Setup${NC}"
echo ""

echo -e "${CYAN}→${NC} Checking for uv..."
if command -v uv >/dev/null 2>&1; then
    UV_CMD="uv"
elif [ -x "$HOME/.local/bin/uv" ]; then
    UV_CMD="$HOME/.local/bin/uv"
elif [ -x "$HOME/.cargo/bin/uv" ]; then
    UV_CMD="$HOME/.cargo/bin/uv"
else
    echo -e "${CYAN}→${NC} Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    if [ -x "$HOME/.local/bin/uv" ]; then
        UV_CMD="$HOME/.local/bin/uv"
    elif [ -x "$HOME/.cargo/bin/uv" ]; then
        UV_CMD="$HOME/.cargo/bin/uv"
    else
        echo -e "${RED}✗${NC} uv installed but was not found on PATH."
        exit 1
    fi
fi
echo -e "${GREEN}✓${NC} Using $($UV_CMD --version)"

echo -e "${CYAN}→${NC} Creating virtual environment..."
rm -rf venv
"$UV_CMD" venv venv --python "$PYTHON_VERSION"
export VIRTUAL_ENV="$SCRIPT_DIR/venv"
echo -e "${GREEN}✓${NC} venv ready"

echo -e "${CYAN}→${NC} Installing package..."
if [ -f "uv.lock" ]; then
    UV_PROJECT_ENVIRONMENT="$SCRIPT_DIR/venv" "$UV_CMD" sync --all-extras --locked \
        || UV_PROJECT_ENVIRONMENT="$SCRIPT_DIR/venv" "$UV_CMD" sync --all-extras
else
    "$UV_CMD" pip install -e ".[all]" || "$UV_CMD" pip install -e "."
fi
echo -e "${GREEN}✓${NC} Dependencies installed"

echo -e "${CYAN}→${NC} Preparing ~/.local/bin..."
mkdir -p "$HOME/.local/bin"
ln -sf "$SCRIPT_DIR/venv/bin/mavis" "$HOME/.local/bin/mavis"
echo -e "${GREEN}✓${NC} Linked mavis → ~/.local/bin/mavis"

if ! echo "$PATH" | tr ':' '\n' | grep -qx "$HOME/.local/bin"; then
    SHELL_CONFIG=""
    if [[ "${SHELL:-}" == *"zsh"* ]]; then
        SHELL_CONFIG="$HOME/.zshrc"
    elif [[ "${SHELL:-}" == *"bash"* ]]; then
        SHELL_CONFIG="$HOME/.bashrc"
    fi
    if [ -n "$SHELL_CONFIG" ]; then
        touch "$SHELL_CONFIG"
        if ! grep -q '\.local/bin' "$SHELL_CONFIG"; then
            {
                echo ""
                echo "# Mavis"
                echo 'export PATH="$HOME/.local/bin:$PATH"'
            } >> "$SHELL_CONFIG"
            echo -e "${GREEN}✓${NC} Added ~/.local/bin to $SHELL_CONFIG"
        fi
    fi
fi

echo -e "${CYAN}→${NC} Creating ~/.mavis..."
mkdir -p "$MAVIS_HOME"/{cron,sessions,logs,memories,skills}
echo -e "${GREEN}✓${NC} Runtime directories ready"

echo ""
echo "Next steps:"
echo "  1. Reload your shell or run: export PATH=\"$HOME/.local/bin:$PATH\""
echo "  2. Run: mavis setup"
echo "  3. Start: mavis"
echo ""

if [ -t 0 ]; then
    read -r -p "Run 'mavis setup' now? [Y/n] " reply
    if [[ -z "$reply" || "$reply" =~ ^[Yy]$ ]]; then
        "$SCRIPT_DIR/venv/bin/python" -m hermes_cli.main setup
    fi
fi
