#!/usr/bin/env python3
"""
Mavis CLI - Main entry point.

Usage:
    mavis                     # Interactive chat (default)
    mavis chat                # Interactive chat
    mavis gateway             # Run gateway in foreground
    mavis gateway start       # Start gateway as service
    mavis gateway stop        # Stop gateway service
    mavis gateway status      # Show gateway status
    mavis gateway install     # Install gateway service
    mavis gateway uninstall   # Uninstall gateway service
    mavis setup               # Interactive setup wizard
    mavis logout              # Clear stored authentication
    mavis status              # Show status of all components
    mavis cron                # Manage cron jobs
    mavis cron list           # List cron jobs
    mavis cron status         # Check if cron scheduler is running
    mavis doctor              # Check configuration and dependencies
    mavis honcho setup                    # Configure Honcho AI memory integration
    mavis honcho status                   # Show Honcho config and connection status
    mavis honcho sessions                 # List directory → session name mappings
    mavis honcho map <name>               # Map current directory to a session name
    mavis honcho peer                     # Show peer names and dialectic settings
    mavis honcho peer --user NAME         # Set user peer name
    mavis honcho peer --ai NAME           # Set AI peer name
    mavis honcho peer --reasoning LEVEL   # Set dialectic reasoning level
    mavis honcho mode                     # Show current memory mode
    mavis honcho mode [hybrid|honcho|local]  # Set memory mode
    mavis honcho tokens                   # Show token budget settings
    mavis honcho tokens --context N       # Set session.context() token cap
    mavis honcho tokens --dialectic N     # Set dialectic result char cap
    mavis honcho identity                 # Show AI peer identity representation
    mavis honcho identity <file>          # Seed AI peer identity from a file (SOUL.md etc.)
    mavis honcho migrate                  # Step-by-step migration guide: OpenClaw native → Mavis + Honcho
    mavis version             Show version
    mavis update              Update to latest version
    mavis uninstall           Uninstall Mavis
    mavis acp                 Run as an ACP server for editor integration
    mavis sessions browse     Interactive session picker with search

    mavis claw migrate --dry-run  # Preview migration without changes
"""

# IMPORTANT: hermes_bootstrap must be the very first import — it sets up
# UTF-8 stdio on Windows so print()/subprocess children don't hit
# UnicodeEncodeError with non-ASCII characters.  No-op on POSIX.
#
# Guarded against ModuleNotFoundError because ``hermes_bootstrap`` is a
# top-level module registered via pyproject.toml's ``py-modules`` list.
# When the user upgrades code via ``git pull`` (or ``hermes update``
# crashes between ``git reset --hard`` and ``uv pip install -e .``), the
# new code references ``hermes_bootstrap`` but the editable install's
# ``.pth`` file still points at the old set of top-level modules.  Without
# this guard, hermes crashes on import and the user can't run
# ``hermes update`` to recover.  Missing the bootstrap means UTF-8 stdio
# setup is skipped on Windows — degraded, not broken.  POSIX is unaffected.
try:
    import hermes_bootstrap  # noqa: F401
except ModuleNotFoundError:
    pass

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

from hermes_constants import (
    APP_NAME,
    CLI_NAME,
    HOME_ENV_VAR,
    LEGACY_HOME_ENV_VAR,
    OPENROUTER_BASE_URL,
)
