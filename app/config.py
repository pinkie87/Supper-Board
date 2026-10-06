"""Einstellungen aus Umgebungsvariablen (siehe .env.example)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from zoneinfo import ZoneInfo

WEEKDAYS = {"mo": 0, "di": 1, "mi": 2, "do": 3, "fr": 4, "sa": 5, "so": 6}


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _weekday(name: str, default: str) -> int:
    value = _env(name, default).lower()[:2]
    if value not in WEEKDAYS:
        raise ValueError(f"{name}: unbekannter Wochentag '{value}' (erlaubt: {', '.join(WEEKDAYS)})")
    return WEEKDAYS[value]


def _time(name: str, default: str) -> tuple[int, int]:
    value = _env(name, default)
    if not value:
        return (-1, -1)
    hh, mm = value.split(":")
    return (int(hh), int(mm))


@dataclass
class Settings:
    data_dir: Path = field(default_factory=lambda: Path(_env("SB_DATA_DIR", "./data")))
    password: str = field(default_factory=lambda: _env("SB_PASSWORD"))
    timezone: ZoneInfo = field(default_factory=lambda: ZoneInfo(_env("SB_TIMEZONE", "Europe/Berlin")))
    household: str = field(default_factory=lambda: _env("SB_HOUSEHOLD", "ein Haushalt mit zwei Personen"))
    # Standardsprache, bis im Board eine gewählt wird: "de" oder "en"
    language: str = field(default_factory=lambda: _env("SB_LANGUAGE", "de").lower()[:2])
    public_url: str = field(default_factory=lambda: _env("SB_PUBLIC_URL"))

    # KI: "claude", "ollama", "openai" (OpenAI-kompatibler Server) oder "none"
    llm_provider: str = field(default_factory=lambda: _env("LLM_PROVIDER", "none").lower())
    anthropic_api_key: str = field(default_factory=lambda: _env("ANTHROPIC_API_KEY"))
    claude_model: str = field(default_factory=lambda: _env("CLAUDE_MODEL", "claude-opus-5-5"))
    claude_effort: str = field(default_factory=lambda: _env("CLAUDE_EFFORT", "medium"))
    ollama_url: str = field(default_factory=lambda: _env("OLLAMA_URL", "http://localhost:11434").rstrip("/"))
    ollama_model: str = field(default_factory=lambda: _env("OLLAMA_MODEL", "qwen3:14b"))
    # Modell für Fotos von Rezeptseiten; leer = OLLAMA_MODEL
    ollama_vision_model: str = field(default_factory=lambda: _env("OLLAMA_VISION_MODEL"))
    # OpenAI-kompatibler Server (llama.cpp, LM Studio, vLLM), Adresse inklusive /v1
    openai_url: str = field(default_factory=lambda: _env("OPENAI_URL", "http://localhost:8080/v1").rstrip("/"))
    openai_model: str = field(default_factory=lambda: _env("OPENAI_MODEL", "local"))
    openai_vision_model: str = field(default_factory=lambda: _env("OPENAI_VISION_MODEL"))
    openai_api_key: str = field(default_factory=lambda: _env("OPENAI_API_KEY"))

    # Einkauf
    store_name: str = field(default_factory=lambda: _env("SB_STORE_NAME", "REWE"))
    store_url: str = field(default_factory=lambda: _env("SB_STORE_URL", "https://shop.rewe.de/"))
    store_search_url: str = field(default_factory=lambda: _env("SB_STORE_SEARCH_URL", "https://shop.rewe.de/productList?search={q}"))
    shop_weekday: int = field(default_factory=lambda: _weekday("SB_SHOP_DAY", "sa"))
    always_restock: str = field(default_factory=lambda: _env("SB_ALWAYS_RESTOCK", "Eier, Milch, Joghurt"))

    # Zeitplan
    draft_weekday: int = field(default_factory=lambda: _weekday("SB_DRAFT_DAY", "di"))
    draft_time: tuple[int, int] = field(default_factory=lambda: _time("SB_DRAFT_TIME", "06:50"))
    list_weekday: int = field(default_factory=lambda: _weekday("SB_LIST_DAY", "do"))
    list_time: tuple[int, int] = field(default_factory=lambda: _time("SB_LIST_TIME", "17:50"))
    thaw_time: tuple[int, int] = field(default_factory=lambda: _time("SB_THAW_TIME", "20:00"))
    dinner_time: tuple[int, int] = field(default_factory=lambda: _time("SB_DINNER_TIME", ""))

    # Home Assistant
    ha_url: str = field(default_factory=lambda: _env("HA_URL").rstrip("/"))
    ha_token: str = field(default_factory=lambda: _env("HA_TOKEN"))
    ha_notify: list[str] = field(default_factory=lambda: [s.strip() for s in _env("HA_NOTIFY").split(",") if s.strip()])

    @property
    def db_path(self) -> Path:
        return self.data_dir / "supper-board.sqlite3"

    @property
    def llm_enabled(self) -> bool:
        return self.llm_provider in ("claude", "ollama", "openai")


settings = Settings()
