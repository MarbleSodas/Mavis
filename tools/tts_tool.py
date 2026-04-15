#!/usr/bin/env python3
"""
Text-to-Speech Tool Module

Supports six TTS providers:
- Piper (default, local): On-device TTS via the Piper CLI
- Edge TTS: Microsoft Edge neural voices
- ElevenLabs (premium): High-quality voices, needs ELEVENLABS_API_KEY
- OpenAI TTS: Good quality, needs OPENAI_API_KEY
- MiniMax TTS: High-quality with voice cloning, needs MINIMAX_API_KEY
- NeuTTS (local, free, no API key): On-device TTS via neutts_cli, needs neutts installed

Output formats:
- Opus (.ogg) for Telegram voice bubbles (requires ffmpeg for Edge TTS)
- MP3 (.mp3) for everything else (CLI, Discord, WhatsApp)

Configuration is loaded from ~/.mavis/config.yaml under the 'tts:' key.
The user chooses the provider and voice; the model just sends text.

Usage:
    from tools.tts_tool import text_to_speech_tool, check_tts_requirements

    result = text_to_speech_tool(text="Hello world")
"""

import asyncio
import datetime
import json
import logging
import os
import queue
import re
import shutil
import subprocess
import tempfile
import threading
import uuid
from pathlib import Path
from typing import Callable, Dict, Any, Optional
from urllib.parse import urljoin

logger = logging.getLogger(__name__)
from tools.managed_tool_gateway import resolve_managed_tool_gateway
from tools.tool_backend_helpers import managed_nous_tools_enabled, resolve_openai_audio_api_key
from hermes_constants import display_hermes_home

# ---------------------------------------------------------------------------
# Lazy imports -- providers are imported only when actually used to avoid
# crashing in headless environments (SSH, Docker, WSL, no PortAudio).
# ---------------------------------------------------------------------------

def _import_edge_tts():
    """Lazy import edge_tts. Returns the module or raises ImportError."""
    import edge_tts
    return edge_tts

def _import_elevenlabs():
    """Lazy import ElevenLabs client. Returns the class or raises ImportError."""
    from elevenlabs.client import ElevenLabs
    return ElevenLabs

def _import_openai_client():
    """Lazy import OpenAI client. Returns the class or raises ImportError."""
    from openai import OpenAI as OpenAIClient
    return OpenAIClient

def _import_sounddevice():
    """Lazy import sounddevice. Returns the module or raises ImportError/OSError."""
    import sounddevice as sd
    return sd


# ===========================================================================
# Defaults
# ===========================================================================
DEFAULT_PROVIDER = "piper"
DEFAULT_PIPER_VOICE = "en_US-lessac-medium"
DEFAULT_EDGE_VOICE = "en-US-AriaNeural"
DEFAULT_ELEVENLABS_VOICE_ID = "pNInz6obpgDQGcFmaJgB"  # Adam
DEFAULT_ELEVENLABS_MODEL_ID = "eleven_multilingual_v2"
DEFAULT_ELEVENLABS_STREAMING_MODEL_ID = "eleven_flash_v2_5"
DEFAULT_OPENAI_MODEL = "gpt-4o-mini-tts"
DEFAULT_OPENAI_VOICE = "alloy"
DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
DEFAULT_MINIMAX_MODEL = "speech-2.8-hd"
DEFAULT_MINIMAX_VOICE_ID = "English_Graceful_Lady"
DEFAULT_MINIMAX_BASE_URL = "https://api.minimax.io/v1/t2a_v2"

def _get_default_output_dir() -> str:
    from hermes_constants import get_hermes_dir
    return str(get_hermes_dir("cache/audio", "audio_cache"))

DEFAULT_OUTPUT_DIR = _get_default_output_dir()
MAX_TEXT_LENGTH = 4000


# ===========================================================================
# Config loader -- reads tts: section from ~/.mavis/config.yaml
# ===========================================================================
def _load_tts_config() -> Dict[str, Any]:
    """
    Load TTS configuration from ~/.mavis/config.yaml.

    Returns a dict with provider settings. Falls back to defaults
    for any missing fields.
    """
    try:
        from hermes_cli.config import load_config
        config = load_config()
        return config.get("tts", {})
    except ImportError:
        logger.debug("hermes_cli.config not available, using default TTS config")
        return {}
    except Exception as e:
        logger.warning("Failed to load TTS config: %s", e, exc_info=True)
        return {}


def _get_provider(tts_config: Dict[str, Any]) -> str:
    """Get the configured TTS provider name."""
    return (tts_config.get("provider") or DEFAULT_PROVIDER).lower().strip()


def _get_piper_cache_dirs() -> list[Path]:
    """Return likely voice asset directories for Piper models."""
    home = Path.home()
    return [
        home / ".cache" / "piper",
        home / ".cache" / "piper" / "voices",
        home / ".local" / "share" / "piper",
        home / ".local" / "share" / "piper" / "voices",
        home / "piper",
    ]


def _piper_binary() -> Optional[str]:
    return shutil.which("piper")


def _default_piper_model_dir() -> Path:
    from hermes_constants import get_hermes_home
    return get_hermes_home() / "voices" / "piper"


def _resolve_piper_asset_path(path_value: str) -> Optional[Path]:
    raw = (path_value or "").strip()
    if not raw:
        return None
    path = Path(raw).expanduser()
    return path if path.exists() else None


def _resolve_piper_paths(tts_config: Dict[str, Any]) -> tuple[Optional[Path], Optional[Path]]:
    """Resolve Piper voice asset paths from config and common cache locations."""
    piper_cfg = tts_config.get("piper", {})
    explicit_model = _resolve_piper_asset_path(piper_cfg.get("model_path", ""))
    explicit_config = _resolve_piper_asset_path(piper_cfg.get("config_path", ""))
    if explicit_model:
        if explicit_config:
            return explicit_model, explicit_config
        sidecar = Path(str(explicit_model) + ".json")
        if sidecar.exists():
            return explicit_model, sidecar
        alt_sidecar = explicit_model.with_suffix(explicit_model.suffix + ".json")
        if alt_sidecar.exists():
            return explicit_model, alt_sidecar
        return explicit_model, None

    voice = (piper_cfg.get("voice") or DEFAULT_PIPER_VOICE).strip()
    if not voice:
        return None, None

    candidates = []
    if voice.endswith(".onnx"):
        candidates.append(voice)
    else:
        candidates.extend([voice, f"{voice}.onnx"])

    search_roots = [_default_piper_model_dir(), *_get_piper_cache_dirs()]
    for root in search_roots:
        for candidate in candidates:
            model_path = root / candidate
            if model_path.exists():
                config_path = Path(str(model_path) + ".json")
                if not config_path.exists():
                    config_path = model_path.with_suffix(model_path.suffix + ".json")
                return model_path, config_path if config_path.exists() else None
    return None, None


# ===========================================================================
# ffmpeg Opus conversion (Edge TTS MP3 -> OGG Opus for Telegram)
# ===========================================================================
def _has_ffmpeg() -> bool:
    """Check if ffmpeg is available on the system."""
    return shutil.which("ffmpeg") is not None


def _convert_to_opus(mp3_path: str) -> Optional[str]:
    """
    Convert an MP3 file to OGG Opus format for Telegram voice bubbles.

    Args:
        mp3_path: Path to the input MP3 file.

    Returns:
        Path to the .ogg file, or None if conversion fails.
    """
    if not _has_ffmpeg():
        return None

    ogg_path = mp3_path.rsplit(".", 1)[0] + ".ogg"
    try:
        result = subprocess.run(
            ["ffmpeg", "-i", mp3_path, "-acodec", "libopus",
             "-ac", "1", "-b:a", "64k", "-vbr", "off", ogg_path, "-y"],
            capture_output=True, timeout=30,
        )
        if result.returncode != 0:
            logger.warning("ffmpeg conversion failed with return code %d: %s", 
                          result.returncode, result.stderr.decode('utf-8', errors='ignore')[:200])
            return None
        if os.path.exists(ogg_path) and os.path.getsize(ogg_path) > 0:
            return ogg_path
    except subprocess.TimeoutExpired:
        logger.warning("ffmpeg OGG conversion timed out after 30s")
    except FileNotFoundError:
        logger.warning("ffmpeg not found in PATH")
    except Exception as e:
        logger.warning("ffmpeg OGG conversion failed: %s", e, exc_info=True)
    return None


# ===========================================================================
# Provider: Piper (local)
# ===========================================================================
def _generate_piper_tts(text: str, output_path: str, tts_config: Dict[str, Any]) -> str:
    """Generate audio using the local Piper CLI."""
    binary = _piper_binary()
    if not binary:
        raise FileNotFoundError(
            "piper CLI not found. Install the Piper runtime and make sure 'piper' is in PATH."
        )

    model_path, config_path = _resolve_piper_paths(tts_config)
    if model_path is None:
        piper_cfg = tts_config.get("piper", {})
        voice_name = piper_cfg.get("voice") or DEFAULT_PIPER_VOICE
        raise FileNotFoundError(
            f"Piper voice assets not found for '{voice_name}'. "
            "Set tts.piper.model_path/config_path or download the voice locally."
        )

    piper_cfg = tts_config.get("piper", {})
    wav_output = output_path
    needs_conversion = not output_path.lower().endswith(".wav")
    if needs_conversion:
        wav_output = output_path.rsplit(".", 1)[0] + ".wav"

    command = [binary, "--model", str(model_path), "--output_file", wav_output]
    if config_path:
        command.extend(["--config", str(config_path)])

    speaker = str(piper_cfg.get("speaker", "")).strip()
    if speaker:
        command.extend(["--speaker", speaker])

    length_scale = piper_cfg.get("length_scale")
    if length_scale not in (None, ""):
        command.extend(["--length_scale", str(length_scale)])

    noise_scale = piper_cfg.get("noise_scale")
    if noise_scale not in (None, ""):
        command.extend(["--noise_scale", str(noise_scale)])

    result = subprocess.run(
        command,
        input=text.encode("utf-8"),
        capture_output=True,
        timeout=90,
    )
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", errors="ignore").strip()
        raise RuntimeError(stderr or f"Piper exited with status {result.returncode}")

    if not os.path.exists(wav_output) or os.path.getsize(wav_output) == 0:
        raise RuntimeError("Piper completed without creating audio output")

    if not needs_conversion:
        return wav_output

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise FileNotFoundError(
            "ffmpeg is required to convert Piper WAV output to MP3/OGG"
        )

    conv = subprocess.run(
        [ffmpeg, "-i", wav_output, "-y", "-loglevel", "error", output_path],
        capture_output=True,
        timeout=30,
    )
    if conv.returncode != 0:
        stderr = conv.stderr.decode("utf-8", errors="ignore").strip()
        raise RuntimeError(stderr or "ffmpeg failed to convert Piper output")

    try:
        os.unlink(wav_output)
    except OSError:
        pass
    return output_path


# ===========================================================================
# Provider: Edge TTS (free)
# ===========================================================================
async def _generate_edge_tts(text: str, output_path: str, tts_config: Dict[str, Any]) -> str:
    """
    Generate audio using Edge TTS.

    Args:
        text: Text to convert.
        output_path: Where to save the MP3 file.
        tts_config: TTS config dict.

    Returns:
        Path to the saved audio file.
    """
    _edge_tts = _import_edge_tts()
    edge_config = tts_config.get("edge", {})
    voice = edge_config.get("voice", DEFAULT_EDGE_VOICE)

    communicate = _edge_tts.Communicate(text, voice)
    await communicate.save(output_path)
    return output_path


# ===========================================================================
# Provider: ElevenLabs (premium)
# ===========================================================================
def _generate_elevenlabs(text: str, output_path: str, tts_config: Dict[str, Any]) -> str:
    """
    Generate audio using ElevenLabs.

    Args:
        text: Text to convert.
        output_path: Where to save the audio file.
        tts_config: TTS config dict.

    Returns:
        Path to the saved audio file.
    """
    api_key = os.getenv("ELEVENLABS_API_KEY", "")
    if not api_key:
        raise ValueError("ELEVENLABS_API_KEY not set. Get one at https://elevenlabs.io/")

    el_config = tts_config.get("elevenlabs", {})
    voice_id = el_config.get("voice_id", DEFAULT_ELEVENLABS_VOICE_ID)
    model_id = el_config.get("model_id", DEFAULT_ELEVENLABS_MODEL_ID)

    # Determine output format based on file extension
    if output_path.endswith(".ogg"):
        output_format = "opus_48000_64"
    else:
        output_format = "mp3_44100_128"

    ElevenLabs = _import_elevenlabs()
    client = ElevenLabs(api_key=api_key)
    audio_generator = client.text_to_speech.convert(
        text=text,
        voice_id=voice_id,
        model_id=model_id,
        output_format=output_format,
    )

    # audio_generator yields chunks -- write them all
    with open(output_path, "wb") as f:
        for chunk in audio_generator:
            f.write(chunk)

    return output_path


# ===========================================================================
# Provider: OpenAI TTS
# ===========================================================================
def _generate_openai_tts(text: str, output_path: str, tts_config: Dict[str, Any]) -> str:
    """
    Generate audio using OpenAI TTS.

    Args:
        text: Text to convert.
        output_path: Where to save the audio file.
        tts_config: TTS config dict.

    Returns:
        Path to the saved audio file.
    """
    api_key, base_url = _resolve_openai_audio_client_config()

    oai_config = tts_config.get("openai", {})
    model = oai_config.get("model", DEFAULT_OPENAI_MODEL)
    voice = oai_config.get("voice", DEFAULT_OPENAI_VOICE)
    base_url = oai_config.get("base_url", base_url)

    # Determine response format from extension
    if output_path.endswith(".ogg"):
        response_format = "opus"
    else:
        response_format = "mp3"

    OpenAIClient = _import_openai_client()
    client = OpenAIClient(api_key=api_key, base_url=base_url)
    try:
        response = client.audio.speech.create(
            model=model,
            voice=voice,
            input=text,
            response_format=response_format,
            extra_headers={"x-idempotency-key": str(uuid.uuid4())},
        )

        response.stream_to_file(output_path)
        return output_path
    finally:
        close = getattr(client, "close", None)
        if callable(close):
            close()


# ===========================================================================
# Provider: MiniMax TTS
# ===========================================================================
def _generate_minimax_tts(text: str, output_path: str, tts_config: Dict[str, Any]) -> str:
    """
    Generate audio using MiniMax TTS API.

    MiniMax returns hex-encoded audio data. Supports streaming (SSE) and
    non-streaming modes. This implementation uses non-streaming for simplicity.

    Args:
        text: Text to convert (max 10,000 characters).
        output_path: Where to save the audio file.
        tts_config: TTS config dict.

    Returns:
        Path to the saved audio file.
    """
    import requests

    api_key = os.getenv("MINIMAX_API_KEY", "")
    if not api_key:
        raise ValueError("MINIMAX_API_KEY not set. Get one at https://platform.minimax.io/")

    mm_config = tts_config.get("minimax", {})
    model = mm_config.get("model", DEFAULT_MINIMAX_MODEL)
    voice_id = mm_config.get("voice_id", DEFAULT_MINIMAX_VOICE_ID)
    speed = mm_config.get("speed", 1)
    vol = mm_config.get("vol", 1)
    pitch = mm_config.get("pitch", 0)
    base_url = mm_config.get("base_url", DEFAULT_MINIMAX_BASE_URL)

    # Determine audio format from output extension
    if output_path.endswith(".wav"):
        audio_format = "wav"
    elif output_path.endswith(".flac"):
        audio_format = "flac"
    else:
        audio_format = "mp3"

    payload = {
        "model": model,
        "text": text,
        "stream": False,
        "voice_setting": {
            "voice_id": voice_id,
            "speed": speed,
            "vol": vol,
            "pitch": pitch,
        },
        "audio_setting": {
            "sample_rate": 32000,
            "bitrate": 128000,
            "format": audio_format,
            "channel": 1,
        },
    }

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    response = requests.post(base_url, json=payload, headers=headers, timeout=60)
    response.raise_for_status()

    result = response.json()
    base_resp = result.get("base_resp", {})
    status_code = base_resp.get("status_code", -1)

    if status_code != 0:
        status_msg = base_resp.get("status_msg", "unknown error")
        raise RuntimeError(f"MiniMax TTS API error (code {status_code}): {status_msg}")

    hex_audio = result.get("data", {}).get("audio", "")
    if not hex_audio:
        raise RuntimeError("MiniMax TTS returned empty audio data")

    # MiniMax returns hex-encoded audio (not base64)
    audio_bytes = bytes.fromhex(hex_audio)

    with open(output_path, "wb") as f:
        f.write(audio_bytes)

    return output_path


# ===========================================================================
# NeuTTS (local, on-device TTS via neutts_cli)
# ===========================================================================

def _check_neutts_available() -> bool:
    """Check if the neutts engine is importable (installed locally)."""
    try:
        import importlib.util
        return importlib.util.find_spec("neutts") is not None
    except Exception:
        return False


def _default_neutts_ref_audio() -> str:
    """Return path to the bundled default voice reference audio."""
    return str(Path(__file__).parent / "neutts_samples" / "jo.wav")


def _default_neutts_ref_text() -> str:
    """Return path to the bundled default voice reference transcript."""
    return str(Path(__file__).parent / "neutts_samples" / "jo.txt")


def _generate_neutts(text: str, output_path: str, tts_config: Dict[str, Any]) -> str:
    """Generate speech using the local NeuTTS engine.

    Runs synthesis in a subprocess via tools/neutts_synth.py to keep the
    ~500MB model in a separate process that exits after synthesis.
    Outputs WAV; the caller handles conversion for Telegram if needed.
    """
    import sys

    neutts_config = tts_config.get("neutts", {})
    ref_audio = neutts_config.get("ref_audio", "") or _default_neutts_ref_audio()
    ref_text = neutts_config.get("ref_text", "") or _default_neutts_ref_text()
    model = neutts_config.get("model", "neuphonic/neutts-air-q4-gguf")
    device = neutts_config.get("device", "cpu")

    # NeuTTS outputs WAV natively — use a .wav path for generation,
    # let the caller convert to the final format afterward.
    wav_path = output_path
    if not output_path.endswith(".wav"):
        wav_path = output_path.rsplit(".", 1)[0] + ".wav"

    synth_script = str(Path(__file__).parent / "neutts_synth.py")
    cmd = [
        sys.executable, synth_script,
        "--text", text,
        "--out", wav_path,
        "--ref-audio", ref_audio,
        "--ref-text", ref_text,
        "--model", model,
        "--device", device,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        stderr = result.stderr.strip()
        # Filter out the "OK:" line from stderr
        error_lines = [l for l in stderr.splitlines() if not l.startswith("OK:")]
        raise RuntimeError(f"NeuTTS synthesis failed: {chr(10).join(error_lines) or 'unknown error'}")

    # If the caller wanted .mp3 or .ogg, convert from WAV
    if wav_path != output_path:
        ffmpeg = shutil.which("ffmpeg")
        if ffmpeg:
            conv_cmd = [ffmpeg, "-i", wav_path, "-y", "-loglevel", "error", output_path]
            subprocess.run(conv_cmd, check=True, timeout=30)
            os.remove(wav_path)
        else:
            # No ffmpeg — just rename the WAV to the expected path
            os.rename(wav_path, output_path)

    return output_path


# ===========================================================================
# Main tool function
# ===========================================================================
def text_to_speech_tool(
    text: str,
    output_path: Optional[str] = None,
) -> str:
    """
    Convert text to speech audio.

    Reads provider/voice config from ~/.mavis/config.yaml (tts: section).
    The model sends text; the user configures voice and provider.

    On messaging platforms, the returned MEDIA:<path> tag is intercepted
    by the send pipeline and delivered as a native voice message.
    In CLI mode, the file is saved to ~/voice-memos/.

    Args:
        text: The text to convert to speech.
        output_path: Optional custom save path. Defaults to ~/voice-memos/<timestamp>.mp3

    Returns:
        str: JSON result with success, file_path, and optionally MEDIA tag.
    """
    if not text or not text.strip():
        return tool_error("Text is required", success=False)

    # Truncate very long text with a warning
    if len(text) > MAX_TEXT_LENGTH:
        logger.warning("TTS text too long (%d chars), truncating to %d", len(text), MAX_TEXT_LENGTH)
        text = text[:MAX_TEXT_LENGTH]

    tts_config = _load_tts_config()
    provider = _get_provider(tts_config)

    # Detect platform from gateway env var to choose the best output format.
    # Telegram voice bubbles require Opus (.ogg); OpenAI and ElevenLabs can
    # produce Opus natively (no ffmpeg needed).  Edge TTS always outputs MP3
    # and needs ffmpeg for conversion.
    platform = os.getenv("HERMES_SESSION_PLATFORM", "").lower()
    want_opus = (platform == "telegram")

    # Determine output path
    if output_path:
        file_path = Path(output_path).expanduser()
    else:
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        out_dir = Path(DEFAULT_OUTPUT_DIR)
        out_dir.mkdir(parents=True, exist_ok=True)
        # Use .ogg for Telegram with providers that support native Opus output,
        # otherwise fall back to .mp3 (Edge TTS will attempt ffmpeg conversion later).
        if want_opus and provider in ("openai", "elevenlabs"):
            file_path = out_dir / f"tts_{timestamp}.ogg"
        else:
            file_path = out_dir / f"tts_{timestamp}.mp3"

    # Ensure parent directory exists
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_str = str(file_path)

    try:
        # Generate audio with the configured provider
        if provider == "piper":
            logger.info("Generating speech with Piper...")
            _generate_piper_tts(text, file_str, tts_config)

        elif provider == "elevenlabs":
            try:
                _import_elevenlabs()
            except ImportError:
                return json.dumps({
                    "success": False,
                    "error": "ElevenLabs provider selected but 'elevenlabs' package not installed. Run: pip install elevenlabs"
                }, ensure_ascii=False)
            logger.info("Generating speech with ElevenLabs...")
            _generate_elevenlabs(text, file_str, tts_config)

        elif provider == "openai":
            try:
                _import_openai_client()
            except ImportError:
                return json.dumps({
                    "success": False,
                    "error": "OpenAI provider selected but 'openai' package not installed."
                }, ensure_ascii=False)
            logger.info("Generating speech with OpenAI TTS...")
            _generate_openai_tts(text, file_str, tts_config)

        elif provider == "minimax":
            logger.info("Generating speech with MiniMax TTS...")
            _generate_minimax_tts(text, file_str, tts_config)

        elif provider == "neutts":
            if not _check_neutts_available():
                return json.dumps({
                    "success": False,
                    "error": "NeuTTS provider selected but neutts is not installed. "
                             "Run mavis setup and choose NeuTTS, or install espeak-ng and run python -m pip install -U neutts[all]."
                }, ensure_ascii=False)
            logger.info("Generating speech with NeuTTS (local)...")
            _generate_neutts(text, file_str, tts_config)

        else:
            # Default: Edge TTS (free), with NeuTTS as local fallback
            edge_available = True
            try:
                _import_edge_tts()
            except ImportError:
                edge_available = False

            if edge_available:
                logger.info("Generating speech with Edge TTS...")
                try:
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                        pool.submit(
                            lambda: asyncio.run(_generate_edge_tts(text, file_str, tts_config))
                        ).result(timeout=60)
                except RuntimeError:
                    asyncio.run(_generate_edge_tts(text, file_str, tts_config))
            elif _check_neutts_available():
                logger.info("Edge TTS not available, falling back to NeuTTS (local)...")
                provider = "neutts"
                _generate_neutts(text, file_str, tts_config)
            else:
                return json.dumps({
                    "success": False,
                    "error": "No TTS provider available. Install edge-tts (pip install edge-tts) "
                             "or set up NeuTTS for local synthesis."
                }, ensure_ascii=False)

        # Check the file was actually created
        if not os.path.exists(file_str) or os.path.getsize(file_str) == 0:
            return json.dumps({
                "success": False,
                "error": f"TTS generation produced no output (provider: {provider})"
            }, ensure_ascii=False)

        # Try Opus conversion for Telegram compatibility
        # Edge TTS outputs MP3, NeuTTS outputs WAV — both need ffmpeg conversion
        voice_compatible = False
        if provider in ("edge", "neutts", "minimax", "piper") and not file_str.endswith(".ogg"):
            opus_path = _convert_to_opus(file_str)
            if opus_path:
                file_str = opus_path
                voice_compatible = True
        elif provider in ("elevenlabs", "openai"):
            # These providers can output Opus natively if the path ends in .ogg
            voice_compatible = file_str.endswith(".ogg")

        file_size = os.path.getsize(file_str)
        logger.info("TTS audio saved: %s (%s bytes, provider: %s)", file_str, f"{file_size:,}", provider)

        # Build response with MEDIA tag for platform delivery
        media_tag = f"MEDIA:{file_str}"
        if voice_compatible:
            media_tag = f"[[audio_as_voice]]\n{media_tag}"

        return json.dumps({
            "success": True,
            "file_path": file_str,
            "media_tag": media_tag,
            "provider": provider,
            "voice_compatible": voice_compatible,
        }, ensure_ascii=False)

    except ValueError as e:
        # Configuration errors (missing API keys, etc.)
        error_msg = f"TTS configuration error ({provider}): {e}"
        logger.error("%s", error_msg)
        return tool_error(error_msg, success=False)
    except FileNotFoundError as e:
        # Missing dependencies or files
        error_msg = f"TTS dependency missing ({provider}): {e}"
        logger.error("%s", error_msg, exc_info=True)
        return tool_error(error_msg, success=False)
    except Exception as e:
        # Unexpected errors
        error_msg = f"TTS generation failed ({provider}): {e}"
        logger.error("%s", error_msg, exc_info=True)
        return tool_error(error_msg, success=False)


# ===========================================================================
# Requirements check
# ===========================================================================
def check_tts_requirements(
    provider: Optional[str] = None,
    *,
    local_only: bool = False,
    tts_config: Optional[Dict[str, Any]] = None,
) -> bool:
    """
    Check whether the configured or requested TTS provider is available.

    When ``local_only`` is True, only on-device providers count.

    Returns:
        bool: True if the requested constraints can be satisfied.
    """
    cfg = tts_config or _load_tts_config()
    requested = (provider or _get_provider(cfg) or DEFAULT_PROVIDER).lower().strip()

    def _provider_available(name: str) -> bool:
        if name == "piper":
            model_path, _ = _resolve_piper_paths(cfg)
            return _piper_binary() is not None and model_path is not None
        if name == "neutts":
            return _check_neutts_available()
        if name == "edge":
            try:
                _import_edge_tts()
                return True
            except ImportError:
                return False
        if name == "elevenlabs":
            try:
                _import_elevenlabs()
                return bool(os.getenv("ELEVENLABS_API_KEY"))
            except ImportError:
                return False
        if name == "openai":
            try:
                _import_openai_client()
                return _has_openai_audio_backend()
            except ImportError:
                return False
        if name == "minimax":
            return bool(os.getenv("MINIMAX_API_KEY"))
        return False

    if provider:
        if local_only and requested not in {"piper", "neutts"}:
            return False
        return _provider_available(requested)

    if local_only:
        return _provider_available(requested) and requested in {"piper", "neutts"}

    if _provider_available(requested):
        return True

    for candidate in ("piper", "edge", "elevenlabs", "openai", "minimax", "neutts"):
        if _provider_available(candidate):
            return True
    return False


def get_piper_status(tts_config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Return detailed Piper readiness information for setup and voice checks."""
    cfg = tts_config or _load_tts_config()
    model_path, config_path = _resolve_piper_paths(cfg)
    return {
        "binary": _piper_binary(),
        "model_path": str(model_path) if model_path else "",
        "config_path": str(config_path) if config_path else "",
        "available": _piper_binary() is not None and model_path is not None,
    }


def _resolve_openai_audio_client_config() -> tuple[str, str]:
    """Return direct OpenAI audio config or a managed gateway fallback."""
    direct_api_key = resolve_openai_audio_api_key()
    if direct_api_key:
        return direct_api_key, DEFAULT_OPENAI_BASE_URL

    managed_gateway = resolve_managed_tool_gateway("openai-audio")
    if managed_gateway is None:
        message = "Neither VOICE_TOOLS_OPENAI_KEY nor OPENAI_API_KEY is set"
        if managed_nous_tools_enabled():
            message += ", and the managed OpenAI audio gateway is unavailable"
        raise ValueError(message)

    return managed_gateway.nous_user_token, urljoin(
        f"{managed_gateway.gateway_origin.rstrip('/')}/", "v1"
    )


def _has_openai_audio_backend() -> bool:
    """Return True when OpenAI audio can use direct credentials or the managed gateway."""
    return bool(resolve_openai_audio_api_key() or resolve_managed_tool_gateway("openai-audio"))


# ===========================================================================
# Streaming TTS: sentence-by-sentence pipeline for ElevenLabs
# ===========================================================================
# Sentence boundary pattern: punctuation followed by space or newline
_SENTENCE_BOUNDARY_RE = re.compile(r'(?<=[.!?])(?:\s|\n)|(?:\n\n)')

# Markdown stripping patterns (same as cli.py _voice_speak_response)
_MD_CODE_BLOCK = re.compile(r'```[\s\S]*?```')
_MD_LINK = re.compile(r'\[([^\]]+)\]\([^)]+\)')
_MD_URL = re.compile(r'https?://\S+')
_MD_BOLD = re.compile(r'\*\*(.+?)\*\*')
_MD_ITALIC = re.compile(r'\*(.+?)\*')
_MD_INLINE_CODE = re.compile(r'`(.+?)`')
_MD_HEADER = re.compile(r'^#+\s*', flags=re.MULTILINE)
_MD_LIST_ITEM = re.compile(r'^\s*[-*]\s+', flags=re.MULTILINE)
_MD_HR = re.compile(r'---+')
_MD_EXCESS_NL = re.compile(r'\n{3,}')


def _strip_markdown_for_tts(text: str) -> str:
    """Remove markdown formatting that shouldn't be spoken aloud."""
    text = _MD_CODE_BLOCK.sub(' ', text)
    text = _MD_LINK.sub(r'\1', text)
    text = _MD_URL.sub('', text)
    text = _MD_BOLD.sub(r'\1', text)
    text = _MD_ITALIC.sub(r'\1', text)
    text = _MD_INLINE_CODE.sub(r'\1', text)
    text = _MD_HEADER.sub('', text)
    text = _MD_LIST_ITEM.sub('', text)
    text = _MD_HR.sub('', text)
    text = _MD_EXCESS_NL.sub('\n\n', text)
    return text.strip()


def stream_tts_to_speaker(
    text_queue: queue.Queue,
    stop_event: threading.Event,
    tts_done_event: threading.Event,
    display_callback: Optional[Callable[[str], None]] = None,
):
    """Consume text deltas from *text_queue*, buffer them into sentences,
    and stream each sentence through ElevenLabs TTS to the speaker in
    real-time.

    Protocol:
        * The producer puts ``str`` deltas onto *text_queue*.
        * A ``None`` sentinel signals end-of-text (flush remaining buffer).
        * *stop_event* can be set to abort early (e.g. user interrupt).
        * *tts_done_event* is **set** in the ``finally`` block so callers
          waiting on it (continuous voice mode) know playback is finished.
    """
    tts_done_event.clear()

    try:
        # --- TTS client setup (optional -- display_callback works without it) ---
        client = None
        output_stream = None
        voice_id = DEFAULT_ELEVENLABS_VOICE_ID
        model_id = DEFAULT_ELEVENLABS_STREAMING_MODEL_ID

        tts_config = _load_tts_config()
        el_config = tts_config.get("elevenlabs", {})
        voice_id = el_config.get("voice_id", voice_id)
        model_id = el_config.get("streaming_model_id",
                                 el_config.get("model_id", model_id))

        api_key = os.getenv("ELEVENLABS_API_KEY", "")
        if not api_key:
            logger.warning("ELEVENLABS_API_KEY not set; streaming TTS audio disabled")
        else:
            try:
                ElevenLabs = _import_elevenlabs()
                client = ElevenLabs(api_key=api_key)
            except ImportError:
                logger.warning("elevenlabs package not installed; streaming TTS disabled")

            # Open a single sounddevice output stream for the lifetime of
            # this function.  ElevenLabs pcm_24000 produces signed 16-bit
            # little-endian mono PCM at 24 kHz.
            if client is not None:
                try:
                    sd = _import_sounddevice()
                    output_stream = sd.OutputStream(
                        samplerate=24000, channels=1, dtype="int16",
                    )
                    output_stream.start()
                except (ImportError, OSError) as exc:
                    logger.debug("sounddevice not available: %s", exc)
                    output_stream = None
                except Exception as exc:
                    logger.warning("sounddevice OutputStream failed: %s", exc)
                    output_stream = None

        sentence_buf = ""
        min_sentence_len = 20
        long_flush_len = 100
        queue_timeout = 0.5
        _spoken_sentences: list[str] = []  # track spoken sentences to skip duplicates
        # Regex to strip complete <think>...</think> blocks from buffer
        _think_block_re = re.compile(r'<think[\s>].*?</think>', flags=re.DOTALL)

        def _speak_sentence(sentence: str):
            """Display sentence and optionally generate + play audio."""
            if stop_event.is_set():
                return
            cleaned = _strip_markdown_for_tts(sentence).strip()
            if not cleaned:
                return
            # Skip duplicate/near-duplicate sentences (LLM repetition)
            cleaned_lower = cleaned.lower().rstrip(".!,")
            for prev in _spoken_sentences:
                if prev.lower().rstrip(".!,") == cleaned_lower:
                    return
            _spoken_sentences.append(cleaned)
            # Display raw sentence on screen before TTS processing
            if display_callback is not None:
                display_callback(sentence)
            # Skip audio generation if no TTS client available
            if client is None:
                return
            # Truncate very long sentences
            if len(cleaned) > MAX_TEXT_LENGTH:
                cleaned = cleaned[:MAX_TEXT_LENGTH]
            try:
                audio_iter = client.text_to_speech.convert(
                    text=cleaned,
                    voice_id=voice_id,
                    model_id=model_id,
                    output_format="pcm_24000",
                )
                if output_stream is not None:
                    for chunk in audio_iter:
                        if stop_event.is_set():
                            break
                        import numpy as _np
                        audio_array = _np.frombuffer(chunk, dtype=_np.int16)
                        output_stream.write(audio_array.reshape(-1, 1))
                else:
                    # Fallback: write chunks to temp file and play via system player
                    _play_via_tempfile(audio_iter, stop_event)
            except Exception as exc:
                logger.warning("Streaming TTS sentence failed: %s", exc)

        def _play_via_tempfile(audio_iter, stop_evt):
            """Write PCM chunks to a temp WAV file and play it."""
            tmp_path = None
            try:
                import wave
                tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
                tmp_path = tmp.name
                with wave.open(tmp, "wb") as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)  # 16-bit
                    wf.setframerate(24000)
                    for chunk in audio_iter:
                        if stop_evt.is_set():
                            break
                        wf.writeframes(chunk)
                from tools.voice_mode import play_audio_file
                play_audio_file(tmp_path)
            except Exception as exc:
                logger.warning("Temp-file TTS fallback failed: %s", exc)
            finally:
                if tmp_path:
                    try:
                        os.unlink(tmp_path)
                    except OSError:
                        pass

        while not stop_event.is_set():
            # Read next delta from queue
            try:
                delta = text_queue.get(timeout=queue_timeout)
            except queue.Empty:
                # Timeout: if we have accumulated a long buffer, flush it
                if len(sentence_buf) > long_flush_len:
                    _speak_sentence(sentence_buf)
                    sentence_buf = ""
                continue

            if delta is None:
                # End-of-text sentinel: strip any remaining think blocks, flush
                sentence_buf = _think_block_re.sub('', sentence_buf)
                if sentence_buf.strip():
                    _speak_sentence(sentence_buf)
                break

            sentence_buf += delta

            # --- Think block filtering ---
            # Strip complete <think>...</think> blocks from buffer.
            # Works correctly even when tags span multiple deltas.
            sentence_buf = _think_block_re.sub('', sentence_buf)

            # If an incomplete <think tag is at the end, wait for more data
            # before extracting sentences (the closing tag may arrive next).
            if '<think' in sentence_buf and '</think>' not in sentence_buf:
                continue

            # Check for sentence boundaries
            while True:
                m = _SENTENCE_BOUNDARY_RE.search(sentence_buf)
                if m is None:
                    break
                end_pos = m.end()
                sentence = sentence_buf[:end_pos]
                sentence_buf = sentence_buf[end_pos:]
                # Merge short fragments into the next sentence
                if len(sentence.strip()) < min_sentence_len:
                    sentence_buf = sentence + sentence_buf
                    break
                _speak_sentence(sentence)

        # Drain any remaining items from the queue
        while True:
            try:
                text_queue.get_nowait()
            except queue.Empty:
                break

        # output_stream is closed in the finally block below

    except Exception as exc:
        logger.warning("Streaming TTS pipeline error: %s", exc)
    finally:
        # Always close the audio output stream to avoid locking the device
        if output_stream is not None:
            try:
                output_stream.stop()
                output_stream.close()
            except Exception:
                pass
        tts_done_event.set()


# ===========================================================================
# Main -- quick diagnostics
# ===========================================================================
if __name__ == "__main__":
    print("🔊 Text-to-Speech Tool Module")
    print("=" * 50)

    def _check(importer, label):
        try:
            importer()
            return True
        except ImportError:
            return False

    print("\nProvider availability:")
    piper_status = get_piper_status()
    print(f"  Piper:      {'ready' if piper_status['available'] else 'not ready'}")
    if piper_status["binary"]:
        print(f"    Binary:   {piper_status['binary']}")
    if piper_status["model_path"]:
        print(f"    Voice:    {piper_status['model_path']}")
    print(f"  Edge TTS:   {'installed' if _check(_import_edge_tts, 'edge') else 'not installed (pip install edge-tts)'}")
    print(f"  ElevenLabs: {'installed' if _check(_import_elevenlabs, 'el') else 'not installed (pip install elevenlabs)'}")
    print(f"    API Key:  {'set' if os.getenv('ELEVENLABS_API_KEY') else 'not set'}")
    print(f"  OpenAI:     {'installed' if _check(_import_openai_client, 'oai') else 'not installed'}")
    print(
        "    API Key:  "
        f"{'set' if resolve_openai_audio_api_key() else 'not set (VOICE_TOOLS_OPENAI_KEY or OPENAI_API_KEY)'}"
    )
    print(f"  MiniMax:    {'API key set' if os.getenv('MINIMAX_API_KEY') else 'not set (MINIMAX_API_KEY)'}")
    print(f"  ffmpeg:     {'✅ found' if _has_ffmpeg() else '❌ not found (needed for Telegram Opus)'}")
    print(f"\n  Output dir: {DEFAULT_OUTPUT_DIR}")

    config = _load_tts_config()
    provider = _get_provider(config)
    print(f"  Configured provider: {provider}")


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------
from tools.registry import registry, tool_error

TTS_SCHEMA = {
    "name": "text_to_speech",
    "description": "Convert text to speech audio. Returns a MEDIA: path that the platform delivers as a voice message. On Telegram it plays as a voice bubble, on Discord/WhatsApp as an audio attachment. In CLI mode, saves to ~/voice-memos/. Voice and provider are user-configured, not model-selected.",
    "parameters": {
        "type": "object",
        "properties": {
            "text": {
                "type": "string",
                "description": "The text to convert to speech. Keep under 4000 characters."
            },
            "output_path": {
                "type": "string",
                "description": f"Optional custom file path to save the audio. Defaults to {display_hermes_home()}/cache/audio/<timestamp>.mp3"
            }
        },
        "required": ["text"]
    }
}

registry.register(
    name="text_to_speech",
    toolset="tts",
    schema=TTS_SCHEMA,
    handler=lambda args, **kw: text_to_speech_tool(
        text=args.get("text", ""),
        output_path=args.get("output_path")),
    check_fn=check_tts_requirements,
    emoji="🔊",
)
