"""Paths and protocol constants for the Doubao web ASR backend."""

from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "voxtype-doubao"
WSS_BASE_URL = "wss://ws-samantha.doubao.com/samantha/audio/asr"

# Fixed query parameters observed in the Doubao web client.
FIXED_QUERY_PARAMS = {
    "version_code": "20800",
    "language": "zh",
    "device_platform": "web",
    "aid": "497858",
    "real_aid": "497858",
    "pkg_type": "release_version",
    "pc_version": "3.12.3",
    "region": "",
    "sys_region": "",
    "samantha_web": "1",
    "use-olympus-account": "1",
    "format": "pcm",
}

ORIGIN = "https://www.doubao.com"
LOGIN_URL = "https://www.doubao.com/chat"

AUDIO_SAMPLE_RATE = 16000
AUDIO_CHANNELS = 1
AUDIO_DTYPE = "int16"
STOP_TRAILING_SILENCE_MS = 200

# The service answers an expired/invalid login with these in-band codes.
AUTH_ERROR_CODES = frozenset({709599054, 710012001, 710022013})
AUTH_ERROR_KEYWORDS = [
    "cookie",
    "auth",
    "login",
    "session",
    "unauthorized",
    "expired",
]

WEBVIEW_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

PARAMS_FILE = "params.json"


def get_config_dir() -> Path:
    """Return the per-user config directory, creating it with mode 0700."""
    override = os.environ.get("VOXTYPE_DOUBAO_CONFIG_DIR")
    if override:
        path = Path(override).expanduser()
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
        path = base / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    try:
        path.chmod(0o700)
    except OSError:
        pass
    return path


def get_params_path() -> Path:
    override = os.environ.get("VOXTYPE_DOUBAO_PARAMS")
    if override:
        return Path(override).expanduser()
    return get_config_dir() / PARAMS_FILE


def get_state_path() -> Path:
    """voxtype's state file (state_file = "auto")."""
    override = os.environ.get("VOXTYPE_STATE_PATH")
    if override:
        return Path(override).expanduser()
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    if runtime:
        return Path(runtime) / "voxtype" / "state"
    return Path(f"/run/user/{os.getuid()}") / "voxtype" / "state"
