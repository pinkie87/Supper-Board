"""KI-Anbindung: Claude (Anthropic-API) oder ein lokales Modell über Ollama.

Beide liefern strukturiertes JSON nach einem JSON-Schema zurück.
"""
from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from .config import Settings

log = logging.getLogger(__name__)


class LLMError(Exception):
    pass


class LLMUnavailable(LLMError):
    pass


async def generate_json(settings: Settings, system: str, prompt: str, schema: dict[str, Any]) -> dict:
    provider = settings.llm_provider
    if provider == "claude":
        return await _claude(settings, system, prompt, schema)
    if provider == "ollama":
        return await _ollama(settings, system, prompt, schema)
    raise LLMUnavailable("Keine KI eingerichtet (LLM_PROVIDER ist 'none').")


async def _claude(settings: Settings, system: str, prompt: str, schema: dict[str, Any]) -> dict:
    import anthropic

    if not settings.anthropic_api_key:
        raise LLMUnavailable("ANTHROPIC_API_KEY fehlt.")
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    try:
        async with client.beta.messages.stream(
            model=settings.claude_model,
            max_tokens=64000,
            system=system,
            messages=[{"role": "user", "content": prompt}],
            thinking={"type": "adaptive"},
            output_config={
                "effort": settings.claude_effort,
                "format": {"type": "json_schema", "schema": schema},
            },
            # Lehnt das Modell eine Anfrage ab, übernimmt serverseitig ein passendes Ersatzmodell.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        ) as stream:
            message = await stream.get_final_message()
    except anthropic.AuthenticationError as e:
        raise LLMError("Claude: API-Schlüssel ungültig.") from e
    except anthropic.RateLimitError as e:
        raise LLMError("Claude: Ratenlimit erreicht, bitte später erneut versuchen.") from e
    except anthropic.APIStatusError as e:
        raise LLMError(f"Claude: Fehler {e.status_code}: {e.message}") from e
    except anthropic.APIConnectionError as e:
        raise LLMError("Claude: keine Verbindung zur Anthropic-API.") from e

    if message.stop_reason == "refusal":
        raise LLMError("Claude hat die Anfrage abgelehnt.")
    if message.stop_reason == "max_tokens":
        raise LLMError("Claude: Antwort wurde abgeschnitten (zu lang).")
    text = next((b.text for b in message.content if b.type == "text"), "")
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise LLMError("Claude: Antwort war kein gültiges JSON.") from e


async def _ollama(settings: Settings, system: str, prompt: str, schema: dict[str, Any]) -> dict:
    body = {
        "model": settings.ollama_model,
        "stream": False,
        "format": schema,
        "options": {"temperature": 0.7},
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt + "\n\nAntworte ausschließlich mit JSON nach dem vorgegebenen Schema."},
        ],
    }
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(900.0, connect=10.0)) as client:
            r = await client.post(f"{settings.ollama_url}/api/chat", json=body)
    except httpx.HTTPError as e:
        raise LLMError(f"Ollama nicht erreichbar unter {settings.ollama_url}.") from e
    if r.status_code != 200:
        raise LLMError(f"Ollama: Fehler {r.status_code}: {r.text[:200]}")
    content = r.json().get("message", {}).get("content", "")
    try:
        return json.loads(content)
    except json.JSONDecodeError as e:
        raise LLMError("Ollama: Antwort war kein gültiges JSON.") from e
