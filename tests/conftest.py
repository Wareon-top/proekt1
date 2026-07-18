import os
import tempfile

# Изолируем тесты: пустой токен (разрешает dev_user_id в API) и временная БД.
os.environ["BOT_TOKEN"] = ""
os.environ["DATABASE_URL"] = ""
_fd, _path = tempfile.mkstemp(suffix=".db")
os.close(_fd)
os.environ["DATABASE_PATH"] = _path
