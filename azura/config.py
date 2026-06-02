"""Runtime configuration loaded from .env via pydantic-settings."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All runtime settings."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    tg_api_id: int = Field(alias="TG_API_ID")
    tg_api_hash: str = Field(alias="TG_API_HASH")
    tg_session_name: str = Field(default="session", alias="TG_SESSION_NAME")

    operator_id: int = Field(alias="OPERATOR_ID")
    operator_secret: str = Field(default="changeme", alias="OPERATOR_SECRET")

    onlysq_base_url: str = Field(
        default="https://api.onlysq.ru/ai/openai", alias="ONLYSQ_BASE_URL"
    )
    onlysq_api_key: str = Field(default="", alias="ONLYSQ_API_KEY")

    model_reply: str = Field(default="claude-opus-4-6", alias="MODEL_REPLY")
    model_think: str = Field(default="pplx-gemini-3.1-pro", alias="MODEL_THINK")
    model_embed: str = Field(default="text-embedding-3-small", alias="MODEL_EMBED")
    embed_dim: int = Field(default=1536, alias="EMBED_DIM")
    embeddings_enabled: bool = Field(default=True, alias="EMBEDDINGS_ENABLED")
    model_vision: str = Field(default="", alias="MODEL_VISION")
    model_imagen: str = Field(default="imagen-4", alias="MODEL_IMAGEN")
    vision_enabled: bool = Field(default=False, alias="VISION_ENABLED")
    media_cache_max_mb: int = Field(default=2048, alias="MEDIA_CACHE_MAX_MB")

    db_path: Path = Field(default=Path("data/state.db"), alias="DB_PATH")
    session_path: Path = Field(default=Path("data/session"), alias="SESSION_PATH")
    personality_path: Path = Field(
        default=Path("data/personality.json"), alias="PERSONALITY_PATH"
    )
    personality_lock_path: Path = Field(
        default=Path("data/personality.lock"), alias="PERSONALITY_LOCK_PATH"
    )
    journal_dir: Path = Field(default=Path("data/journal"), alias="JOURNAL_DIR")
    stickers_dir: Path = Field(default=Path("data/stickers"), alias="STICKERS_DIR")
    gifs_dir: Path = Field(default=Path("data/gifs"), alias="GIFS_DIR")
    media_cache_dir: Path = Field(
        default=Path("data/media_cache"), alias="MEDIA_CACHE_DIR"
    )

    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    log_dir: Path = Field(default=Path("logs"), alias="LOG_DIR")

    humanize_min_reply_delay_s: float = Field(
        default=2.5, alias="HUMANIZE_MIN_REPLY_DELAY_S"
    )
    humanize_max_reply_delay_s: float = Field(
        default=900.0, alias="HUMANIZE_MAX_REPLY_DELAY_S"
    )
    humanize_typing_chunk_s: float = Field(
        default=4.5, alias="HUMANIZE_TYPING_CHUNK_S"
    )

    media_max_download_mb: int = Field(default=20, alias="MEDIA_MAX_DOWNLOAD_MB")
    web_fetch_timeout_s: int = Field(default=15, alias="WEB_FETCH_TIMEOUT_S")

    def ensure_dirs(self) -> None:
        """Create every directory the runtime expects."""
        for p in (
            self.db_path.parent,
            self.session_path.parent,
            self.personality_path.parent,
            self.journal_dir,
            self.stickers_dir,
            self.gifs_dir,
            self.media_cache_dir,
            self.log_dir,
        ):
            Path(p).mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached settings singleton."""
    s = Settings()
    s.ensure_dirs()
    return s
