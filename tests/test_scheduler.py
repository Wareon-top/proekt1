import asyncio
from datetime import datetime, timezone

from wareon.services.scheduler import MSK, next_run


def utc(y, m, d, hh=0, mm=0):
    return datetime(y, m, d, hh, mm, tzinfo=timezone.utc)


class TestNextRunDaily:
    def test_later_today(self):
        # 06:00 UTC = 09:00 МСК; отчёт на 10:00 МСК — сегодня
        run = next_run("daily", 10, 0, utc(2026, 7, 15, 6, 0))
        assert run.astimezone(MSK).strftime("%d %H:%M") == "15 10:00"

    def test_tomorrow_if_passed(self):
        # 12:00 UTC = 15:00 МСК; отчёт на 09:00 МСК — уже прошёл, значит завтра
        run = next_run("daily", 9, 0, utc(2026, 7, 15, 12, 0))
        assert run.astimezone(MSK).strftime("%d %H:%M") == "16 09:00"


class TestNextRunWeekly:
    def test_next_monday(self):
        # 15.07.2026 — среда; еженедельный отчёт — в ближайший понедельник 20.07
        run = next_run("weekly", 10, 0, utc(2026, 7, 15, 6, 0))
        run_msk = run.astimezone(MSK)
        assert run_msk.weekday() == 0
        assert run_msk.strftime("%d %H:%M") == "20 10:00"

    def test_monday_before_time(self):
        # понедельник 20.07, 06:00 МСК, отчёт на 10:00 — сегодня же
        run = next_run("weekly", 10, 0, utc(2026, 7, 20, 3, 0))
        assert run.astimezone(MSK).strftime("%d %H:%M") == "20 10:00"

    def test_monday_after_time(self):
        # понедельник 20.07, 12:00 МСК, отчёт на 10:00 — через неделю
        run = next_run("weekly", 10, 0, utc(2026, 7, 20, 9, 0))
        assert run.astimezone(MSK).strftime("%d %H:%M") == "27 10:00"


class _FakeBot:
    def __init__(self):
        self.sent = []

    async def send_message(self, uid, text):
        self.sent.append((uid, text))

    async def send_photo(self, *a, **k):
        self.sent.append(("photo", None))


def test_scheduler_sends_ai_brief(monkeypatch):
    from wareon.db.base import init_db, session_factory
    from wareon.db.models import ReportSubscription
    from wareon.services import ai, scheduler

    async def fake_brief(session, uid):
        return "СВОДКА ИИ на сегодня"

    monkeypatch.setattr(ai, "daily_brief", fake_brief)
    bot = _FakeBot()

    async def flow():
        await init_db()
        async with session_factory() as s:
            s.add(
                ReportSubscription(
                    user_tg_id=4242, kind="ai", hour=9, minute=0,
                    next_run_at=datetime(2000, 1, 1),
                )
            )
            await s.commit()
        return await scheduler.process_due_subscriptions(bot)

    asyncio.run(flow())
    assert any("СВОДКА ИИ" in t for who, t in bot.sent if who == 4242)
