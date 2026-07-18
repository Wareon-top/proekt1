"""Запуск API: python -m wareon.api"""

import uvicorn

if __name__ == "__main__":
    uvicorn.run("wareon.api.app:app", host="0.0.0.0", port=8000, log_level="info")
