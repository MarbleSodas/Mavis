"""
Interactive setup wizard for Mavis.

Modular wizard with independently-runnable sections:
  1. Model & Provider — choose your AI provider and model
  2. Terminal Backend — where your agent runs commands
  3. Agent Settings — iterations, compression, session reset
  4. Messaging Platforms — connect Telegram, Discord, etc.
  5. Tools — configure TTS, web search, image generation, etc.

Config files are stored in ~/.mavis/ for easy access.
"""

import importlib.util
import json
import logging
import os
import re
import shutil
import sys
from datetime import datetime, timezone
