from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Переменные и токены кладём в data/.env (папка data — в .gitignore, секреты не
    # утекут). Корневой .env поддерживается для совместимости; data/.env приоритетнее.
    model_config = SettingsConfigDict(
        env_file=(".env", "data/.env"), env_file_encoding="utf-8", extra="ignore"
    )

    bot_token: str = ""
    database_path: str = "data/wareon.db"
    # Полный адрес БД. Пусто — берётся SQLite по database_path.
    # Для продакшена: postgresql+asyncpg://user:pass@host/db
    database_url: str = ""
    # HTTPS-адрес мини-приложения (Web App). Пусто — кнопка дашборда не показывается.
    webapp_url: str = ""
    # Публичный HTTPS-адрес этого API (бот-хост). Если задан — бот добавит его в
    # адрес дашборда как ?api=..., чтобы Web App знал, откуда брать данные.
    api_public_url: str = ""
    # Разрешённые источники для API (CORS). Обычно — адрес дашборда.
    cors_origins: str = "*"
    # Ключ Anthropic для ИИ-функций (сводка, ассистент). Пусто — ИИ выключен.
    anthropic_api_key: str = ""
    ai_model: str = "claude-opus-4-8"

    @property
    def webapp_enabled(self) -> bool:
        return self.webapp_url.startswith("https://")

    @property
    def crm_url(self) -> str:
        """Адрес CRM-таблицы (webapp/crm.html) рядом с дашбордом."""
        base = self.webapp_url.rstrip()
        if not base:
            return ""
        if base.endswith(".html"):
            base = base.rsplit("/", 1)[0] + "/"
        elif not base.endswith("/"):
            base += "/"
        return base + "crm.html"

    @property
    def webapp_launch_url(self) -> str:
        """Адрес дашборда с приклеенным ?api=<api_public_url>, если тот задан."""
        base = self.webapp_url.rstrip()
        api = self.api_public_url.rstrip().rstrip("/")
        if base and api:
            sep = "&" if "?" in base else "?"
            return f"{base}{sep}api={api}"
        return base

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
