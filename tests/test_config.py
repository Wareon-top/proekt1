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
