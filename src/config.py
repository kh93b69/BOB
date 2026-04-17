from pathlib import Path
from typing import Annotated
from zoneinfo import ZoneInfo

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    telegram_bot_token: str = Field(..., description="Токен от BotFather")
    admin_user_ids: Annotated[list[int], NoDecode] = Field(default_factory=list)
    default_timezone: str = "Asia/Almaty"
    schedule_file: Path = Path("schedule.yaml")
    log_level: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    @field_validator("admin_user_ids", mode="before")
    @classmethod
    def _parse_admin_ids(cls, v):
        if v is None or v == "":
            return []
        if isinstance(v, int):
            return [v]
        if isinstance(v, str):
            return [int(x.strip()) for x in v.split(",") if x.strip()]
        return v

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.default_timezone)


settings = Settings()
