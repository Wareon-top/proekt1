# Деплой Wareon

## Варианты запуска

| Команда | Что запускает |
|---|---|
| `python -m wareon.main` | Только бот (для bothost.ru и подобных «бот-хостингов») |
| `python -m wareon.run` | **Бот + API в одном процессе** (общая БД) — для Render/Railway/VPS |

Дашборд и CRM берут данные через **API**, а бот пишет в **ту же БД**. Поэтому,
если бот и API на разных хостах, у них должна быть **одна база** (общий
`DATABASE_URL`). Проще всего — запускать всё одним процессом (`wareon.run`).

## Render (рекомендуется, ~10 минут, бесплатно)

1. Форкни/подключи репозиторий на [render.com](https://render.com) → **New → Blueprint**.
2. Render прочитает `render.yaml`: создаст веб-сервис (`python -m wareon.run`) и
   бесплатную базу Postgres, свяжет их через `DATABASE_URL`.
3. Задай секреты в настройках сервиса:
   - `BOT_TOKEN` — от @BotFather
   - `ANTHROPIC_API_KEY` — для ИИ (иначе ассистент выключен)
   - `WEBAPP_URL` — адрес дашборда на GitHub Pages (напр. `https://<user>.github.io/proekt1/`)
   - `API_PUBLIC_URL` — публичный адрес этого сервиса на Render (`https://wareon.onrender.com`)
   - `CORS_ORIGINS` — домен дашборда (`https://<user>.github.io`)
4. Deploy. Проверка: `https://<сервис>.onrender.com/api/health` → `{"status":"ok"}`.

После этого дашборд, CRM-синхронизация, напоминания и ИИ работают на одном URL.

## Docker / VPS

```bash
docker build -t wareon .
docker run -e BOT_TOKEN=… -e ANTHROPIC_API_KEY=… -e DATABASE_URL=… \
  -e WEBAPP_URL=… -e API_PUBLIC_URL=… -e CORS_ORIGINS=… -p 8080:8080 wareon
```

Или напрямую: `python -m wareon.run` (порт из переменной `PORT`, по умолчанию 8080).

## База данных

- Без `DATABASE_URL` — SQLite в `data/` (для локали и простого старта).
- `DATABASE_URL=postgres://…` (Render/Railway дают такой) подхватывается
  автоматически — драйвер приводится к `postgresql+asyncpg://`.
