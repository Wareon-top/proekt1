"""Проверка подлинности запроса из Telegram Web App.

Telegram подписывает данные мини-приложения (initData). Мы пересчитываем
подпись секретом на основе токена бота и сверяем — так сервер точно знает,
какой пользователь обращается, и подделать это нельзя.
Документация: https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
"""

import hashlib
import hmac
import json
from urllib.parse import parse_qsl


def validate_init_data(init_data: str, bot_token: str) -> int | None:
    """Возвращает Telegram id пользователя, если подпись верна, иначе None."""
    if not init_data or not bot_token:
        return None
    try:
        pairs = dict(parse_qsl(init_data, keep_blank_values=True))
    except ValueError:
        return None
    received_hash = pairs.pop("hash", None)
    if not received_hash:
        return None

    data_check_string = "\n".join(f"{k}={pairs[k]}" for k in sorted(pairs))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    computed = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(computed, received_hash):
        return None

    try:
        user = json.loads(pairs.get("user", "{}"))
        return int(user["id"])
    except (json.JSONDecodeError, KeyError, ValueError, TypeError):
        return None
