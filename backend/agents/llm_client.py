from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

LOGGER = logging.getLogger(__name__)
MODEL_NAME = "gemini-3.1-flash-lite-preview"
PROJECT_ROOT = Path(__file__).resolve().parents[2]

try:
    from google import genai
    from google.genai import types
except ImportError:  # pragma: no cover - optional dependency in mock mode
    genai = None
    types = None


def _load_env() -> None:
    env_path = PROJECT_ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def get_gemini_api_key() -> str:
    _load_env()
    return os.getenv("GEMINI_API_KEY", "").strip()


def is_gemini_available() -> bool:
    return bool(get_gemini_api_key()) and genai is not None and types is not None


async def call_gemini(prompt: str, system_instruction: str) -> str:
    api_key = get_gemini_api_key()
    if not api_key:
        LOGGER.warning("No Gemini API key found, using mock mode")
        raise RuntimeError("No Gemini API key found, using mock mode")
    if genai is None or types is None:
        raise RuntimeError("google-genai is not installed")

    client = genai.Client(api_key=api_key)

    async def _invoke() -> str:
        def _sync_call() -> str:
            response = client.models.generate_content(
                model=MODEL_NAME,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=0.1,
                ),
            )
            text = getattr(response, "text", None)
            if not text or not str(text).strip():
                raise RuntimeError("Gemini returned an empty response")
            return str(text).strip()

        return await asyncio.to_thread(_sync_call)

    last_error: Exception | None = None
    for attempt in range(2):
        try:
            return await asyncio.wait_for(_invoke(), timeout=30)
        except Exception as exc:  # pragma: no cover - network dependent
            last_error = exc
            LOGGER.warning("Gemini call attempt %s failed: %s", attempt + 1, exc)
            await asyncio.sleep(1 + attempt)
    raise RuntimeError(f"Gemini call failed: {last_error}")
