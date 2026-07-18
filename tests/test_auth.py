import hashlib
import hmac
import json
from urllib.parse import urlencode

from wareon.api.auth import validate_init_data

BOT_TOKEN = "123456:TEST-token"


def make_init_data(user_id: int, token: str = BOT_TOKEN) -> str:
    user = json.dumps({"id": user_id, "first_name": "Тест"}, separators=(",", ":"))
    data = {"auth_date": "1700000000", "query_id": "AAA", "user": user}
    dcs = "\n".join(f"{k}={data[k]}" for k in sorted(data))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    data["hash"] = hmac.new(secret, dcs.encode(), hashlib.sha256).hexdigest()
    return urlencode(data)


def test_valid_signature_returns_user_id():
    assert validate_init_data(make_init_data(42), BOT_TOKEN) == 42


def test_tampered_data_rejected():
    init = make_init_data(42)
    tampered = init.replace("first_name", "first_xame")
    assert validate_init_data(tampered, BOT_TOKEN) is None


def test_wrong_token_rejected():
    assert validate_init_data(make_init_data(42), "999:other") is None


def test_empty_inputs():
    assert validate_init_data("", BOT_TOKEN) is None
    assert validate_init_data("x=1", "") is None
