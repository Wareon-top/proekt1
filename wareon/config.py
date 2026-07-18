from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    bot_token: str = ""
    database_path: str = "wareon.db"
    # Полный адрес БД. Пусто — берётся SQLite по database_path.
    # Для продакшена: postgresql+asyncpg://user:pass@host/db
    database_url: str = ""
    # HTTPS-адрес мини-приложения (Web App). Пусто — кнопка дашборда не показывается.
    webapp_url: str = ""
    # Разрешённые источники для API (CORS). Обычно — адрес дашборда.
    cors_origins: str = "*"
    # Ключ Anthropic для ИИ-функций (сводка, ассистент). Пусто — ИИ выключен.
    anthropic_api_key: str = ""
    ai_model: str = "claude-opus-4-8"

    @property
    def webapp_enabled(self) -> bool:
        return self.webapp_url.startswith("https://")

    @property
    def ai_enabled(self) -> bool:
        return bool(self.anthropic_api_key)

    @property
    def sqlalchemy_url(self) -> str:
        return self.database_url or f"sqlite+aiosqlite:///{self.database_path}"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
