from wareon.config import Settings


def test_launch_url_appends_api():
    s = Settings(webapp_url="https://pages.io/app/", api_public_url="https://api.host.ru/")
    assert s.webapp_launch_url == "https://pages.io/app/?api=https://api.host.ru"


def test_launch_url_respects_existing_query():
    s = Settings(webapp_url="https://pages.io/app?v=1", api_public_url="https://api.host.ru")
    assert s.webapp_launch_url == "https://pages.io/app?v=1&api=https://api.host.ru"


def test_launch_url_without_api_is_plain():
    s = Settings(webapp_url="https://pages.io/app/", api_public_url="")
    assert s.webapp_launch_url == "https://pages.io/app/"


def test_webapp_enabled_flag():
    assert Settings(webapp_url="https://pages.io/").webapp_enabled is True
    assert Settings(webapp_url="").webapp_enabled is False


def test_sqlalchemy_url_normalizes_postgres():
    # Render/Railway отдают postgres:// — приводим к async-драйверу
    assert Settings(database_url="postgres://u:p@h/db").sqlalchemy_url == "postgresql+asyncpg://u:p@h/db"
    assert Settings(database_url="postgresql://u:p@h/db").sqlalchemy_url == "postgresql+asyncpg://u:p@h/db"
    # уже с драйвером — не трогаем
    assert Settings(database_url="postgresql+asyncpg://u:p@h/db").sqlalchemy_url == "postgresql+asyncpg://u:p@h/db"
    # пусто — SQLite
    assert Settings(database_url="", database_path="x.db").sqlalchemy_url == "sqlite+aiosqlite:///x.db"


def test_crm_url():
    assert Settings(webapp_url="https://pages.io/app/").crm_url == "https://pages.io/app/crm.html"
    assert Settings(webapp_url="https://pages.io/app").crm_url == "https://pages.io/app/crm.html"
    assert Settings(webapp_url="https://pages.io/app/index.html").crm_url == "https://pages.io/app/crm.html"
    assert Settings(webapp_url="").crm_url == ""
