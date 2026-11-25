from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "ReelReverse"
    app_username: str = "admin"
    app_password: str = ""
    data_dir: Path = Field(default_factory=lambda: PROJECT_ROOT / "data")
    database_url: str = ""

    llm_provider: str = "mock"
    llm_api_key: str = ""
    llm_base_url: str = ""
    llm_model: str = "gpt-4o-mini"
    vision_model: str = ""
    llm_input_price_per_million: float = Field(default=0.0, ge=0)
    llm_output_price_per_million: float = Field(default=0.0, ge=0)
    cost_currency: str = "USD"

    asr_provider: str = "none"
    asr_api_key: str = ""
    asr_base_url: str = "https://api.openai.com/v1"
    asr_model: str = "whisper-1"

    ffmpeg_bin: str = "ffmpeg"
    ffprobe_bin: str = "ffprobe"
    max_upload_mb: int = 500
    max_shots: int = 24
    scene_threshold: float = 0.32
    min_shot_seconds: float = 0.8
    llm_concurrency: int = 2
    request_timeout_s: int = 90
    max_active_jobs: int = Field(default=4, ge=1, le=32)
    retry_max_attempts: int = Field(default=3, ge=1, le=8)
    retry_base_delay_s: float = Field(default=0.8, ge=0.0, le=30.0)
    retry_max_delay_s: float = Field(default=8.0, ge=0.0, le=120.0)
    prompt_catalog_file: str = ""
    mock_scenario: str = "success"
    mock_fail_shot: int = Field(default=0, ge=0)
    sse_heartbeat_s: float = Field(default=15.0, ge=2.0, le=120.0)
    sse_max_seconds: float = Field(default=900.0, ge=30.0, le=86400.0)
    sse_max_connections: int = Field(default=32, ge=1, le=1000)

    @field_validator("data_dir")
    @classmethod
    def _resolve_data_dir(cls, value: Path) -> Path:
        return value if value.is_absolute() else (PROJECT_ROOT / value).resolve()

    @property
    def db_url(self) -> str:
        if self.database_url:
            return self.database_url
        return f"sqlite:///{(self.data_dir / 'app.db').as_posix()}"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    return settings
