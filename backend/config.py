"""Credentials and model selection, loaded from .env at import time.

uvicorn does not read .env, so without this the backend starts happily and only
discovers the missing key when someone clicks an alert. Loading here means a
misconfigured key is visible at /api/health instead.

The model tiers come from what is actually deployed on this account. Several
Nemotron models are listed by the API but return 404, and the previously used
llama-3.3-nemotron-super-49b-v1.5 reached end of life on 2026-08-26, so these
three are the live set as of 2026-11:

    bolt      1.0s   component agents -- many small, factual reports
    super_vl  4.5s   facility and system agents -- synthesis and tradeoffs
    ultra     5.6s   unused by default; kept for a deliberate quality override
"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Model tiers. Override any of them from the environment.
BOLT = 'nvidia/nemotron-3.5-bolt-e4b'
SUPER_VL = 'nvidia/nemotron-3.5-super-vl-120b-a12b'
ULTRA = 'nvidia/nemotron-3-ultra-550b-a55b'

NVIDIA_URL = 'https://integrate.api.nvidia.com/v1/chat/completions'


def load_env(path: Path | None = None) -> None:
    """Read KEY=value lines from .env without adding a dependency.

    Existing environment variables win, so a real deployment can set them
    properly and ignore the file entirely.
    """
    env = path or ROOT / '.env'
    if not env.is_file():
        return
    for line in env.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, _, value = line.partition('=')
        os.environ.setdefault(key.strip(), value.strip())


load_env()


def api_key() -> str | None:
    return os.getenv('NVIDIA_API_KEY') or None


def component_model() -> str:
    return os.getenv('NVIDIA_COMPONENT_MODEL', BOLT)


def reasoning_model() -> str:
    """Model for facility and system agents, and for /api/investigate."""
    return os.getenv('NVIDIA_MODEL', SUPER_VL)
