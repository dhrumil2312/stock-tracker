"""Application settings, loaded from environment / .env file."""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- News cache freshness ---
    news_recent_ttl_hours: int = 12  # re-fetch news for a recent move only after this TTL
    news_recent_days: int = 3  # a move within this many days counts as "recent"
    news_error_ttl_hours: int = 1  # retry after a provider failure
    news_max_moves_with_news: int = 6  # new company fetches per ticker request
    news_max_articles_per_scope: int = 3  # articles per company/industry/macro query
    news_max_articles_per_movement: int = 5  # kept for older env files; unused by cache

    # --- Movement detection ---
    default_movement_threshold: float = 2.0  # percent, single-day |Δ|

    # --- News provider ---
    # "exa" (semantic, historical) | "newsapi" (keyword, ~30 days) | "mock".
    # If the chosen provider has no key, falls through to any available key, then mock.
    news_provider: str = "exa"
    newsapi_api_key: str | None = None
    exa_api_key: str | None = None

    # --- Chat (OpenRouter — OpenAI-compatible API) ---
    openrouter_api_key: str | None = None
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    # Default model; MUST be one of CHAT_MODELS ids below.
    chat_model: str = "deepseek/deepseek-v4.1-flash"
    chat_max_tokens: int = 1024
    chat_temperature: float = 0.5  # fresh phrasing; chat replies are never stored
    # Optional attribution headers OpenRouter uses for its rankings (safe to leave as-is).
    openrouter_referer: str = "http://localhost:5173"
    openrouter_title: str = "Stock Movement Explainer"

    # --- CORS ---
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()

# Curated chat-model allow-list for the frontend selector. The client may ONLY
# pick from these ids — we never forward an arbitrary model string to OpenRouter
# on our key (prevents abuse / runaway cost when the repo is shared).
CHAT_MODELS: list[dict[str, str]] = [
    {"id": "deepseek/deepseek-v4.1-flash", "label": "DeepSeek v4.1 Flash", "short": "DeepSeek v4.1"},
    {"id": "google/gemini-3.6-flash", "label": "Gemini 3.6 Flash", "short": "Gemini 3.6"},
    {"id": "anthropic/claude-3-haiku", "label": "Claude 3 Haiku", "short": "Haiku 3"},
]
CHAT_MODEL_IDS: frozenset[str] = frozenset(m["id"] for m in CHAT_MODELS)


def resolve_chat_model(requested: str | None) -> str:
    """Return a validated model id from the allow-list, or raise ValueError."""
    if requested is None:
        return settings.chat_model
    if requested not in CHAT_MODEL_IDS:
        raise ValueError(f"Unsupported model '{requested}'.")
    return requested
