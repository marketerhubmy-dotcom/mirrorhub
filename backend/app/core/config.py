from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # ── Core ──────────────────────────────────────────────────────────────────
    app_name: str = "MirrorHub"
    host: str = "127.0.0.1"  # loopback only; see app/core/security.py
    allow_remote_bind: bool = False  # env ALLOW_REMOTE_BIND=true — exposes unauthenticated phone control to the LAN
    port: int = 8000
    database_url: str = "sqlite+aiosqlite:///./mirrorhub.db"

    # ── Security ──────────────────────────────────────────────────────────────
    # Comma-separated list of allowed CORS origins.
    # Default restricts to localhost. Override with CORS_ORIGINS=* in .env for open access.
    cors_origins: str = "http://localhost:3000,http://localhost:8000"

    # ── Devices ───────────────────────────────────────────────────────────────
    device_timeout: int = 30  # seconds before declaring a device unreachable

    # ── AI ────────────────────────────────────────────────────────────────────
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    openai_max_tokens: int = 400

    # ── Vision Engine ─────────────────────────────────────────────────────────
    vision_cache_ttl: int = 5          # seconds to cache a screen analysis result
    vision_poll_interval: float = 2.0  # seconds between wait_until polls
    vision_default_timeout: int = 30   # seconds before wait_until gives up
    vision_max_screenshots: int = 20   # max screenshots to retain per device on disk

    # ── Campaign Dispatcher ───────────────────────────────────────────────────
    campaign_poll_interval: float = 5.0   # seconds between dispatcher ticks
    campaign_retry_delay: float = 30.0    # seconds before a RETRY entry is re-queued

    # ── Logging ───────────────────────────────────────────────────────────────
    log_level: str = "INFO"

    model_config = SettingsConfigDict(env_file=".env")


settings = Settings()
