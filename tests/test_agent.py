import asyncio
from datetime import datetime

import pytest

from wareon.config import settings
from wareon.services import agent


# ── Мок ответа модели ────────────────────────────────────────────────────────
class Blk:
    def __init__(self, type, **kw):
        self.type = type
        self.__dict__.update(kw)


def txt(t):
    return Blk("text", text=t)


def tool(id, name, input):
    return Blk("tool_use", id=id, name=name, input=input)


class Resp:
    def __init__(self, stop_reason, content):
        self.stop_reason = stop_reason
        self.content = content


def scripted(monkeypatch, responses):
    """Подменяет вызов модели заранее заготовленной последовательностью ответов."""
    seq = iter(responses)

    async def fake_create(messages):
        return next(seq)

    monkeypatch.setattr(agent, "_create_message", fake_create)
    monkeypatch.setattr(settings, "anthropic_api_key", "test-key")  # включает ai_enabled


async def _seed_sale(session_factory_, uid, revenue=1000, cost=300):
    from wareon.db.models import Sale

    async with session_factory_() as s:
        s.add(Sale(user_tg_id=uid, revenue=revenue, cost=cost, created_at=datetime(2026, 7, 18)))
        await s.commit()


# ── Автономия ────────────────────────────────────────────────────────────────
def test_autonomy_default_and_set():
    from wareon.db.base import init_db, session_factory

    async def flow():
        await init_db()
        async with session_factory() as s:
            default = await agent.get_autonomy(s, 810001)
            await agent.set_autonomy(s, 810001, "autopilot")
            after = await agent.get_autonomy(s, 810001)
        return default, after

    default, after = asyncio.run(flow())
    assert default == "semi"
    assert after == "autopilot"


def test_set_autonomy_rejects_unknown():
    from wareon.db.base import init_db, session_factory

    async def flow():
        await init_db()
        async with session_factory() as s:
            with pytest.raises(ValueError):
                await agent.set_autonomy(s, 810002, "turbo")

    asyncio.run(flow())


# ── Цикл оркестратора ────────────────────────────────────────────────────────
def test_agent_disabled_without_key(monkeypatch):
    from wareon.db.base import init_db, session_factory

    monkeypatch.setattr(settings, "anthropic_api_key", "")

    async def flow():
        await init_db()
        async with session_factory() as s:
            return await agent.run_agent(s, 810003, "как дела?")

    result = asyncio.run(flow())
    assert result.text == agent.ai.DISABLED_MSG


def test_agent_reads_panel_then_answers(monkeypatch):
    from wareon.db.base import init_db, session_factory

    scripted(
        monkeypatch,
        [
            Resp("tool_use", [tool("t1", "get_panel", {"days": 7})]),
            Resp("end_turn", [txt("Выручка есть, маржа хорошая.")]),
        ],
    )
    uid = 810010

    async def flow():
        await init_db()
        await _seed_sale(session_factory, uid)
        async with session_factory() as s:
            return await agent.run_agent(s, uid, "как бизнес за неделю?")

    result = asyncio.run(flow())
    assert "маржа" in result.text


def test_agent_adds_metric_on_autopilot(monkeypatch):
    from sqlalchemy import select

    from wareon.db.base import init_db, session_factory
    from wareon.db.models import CustomMetric

    scripted(
        monkeypatch,
        [
            Resp(
                "tool_use",
                [
                    tool(
                        "t1",
                        "add_metric",
                        {
                            "key": "ad_share",
                            "title": "Доля рекламы",
                            "formula": "ad_spend / revenue * 100",
                            "unit": "%",
                            "direction": "down",
                        },
                    )
                ],
            ),
            Resp("end_turn", [txt("Готово, метрика в пульте.")]),
        ],
    )
    uid = 810011

    async def flow():
        await init_db()
        async with session_factory() as s:
            await agent.set_autonomy(s, uid, "autopilot")
        async with session_factory() as s:
            result = await agent.run_agent(s, uid, "заведи долю рекламы")
        async with session_factory() as s:
            cm = await s.scalar(
                select(CustomMetric).where(CustomMetric.user_tg_id == uid)
            )
        return result, cm

    result, cm = asyncio.run(flow())
    assert cm is not None
    assert cm.pending is False
    assert cm.created_by == "ai"
    assert any("завёл метрику" in a for a in result.actions)


def test_agent_proposes_metric_on_semi(monkeypatch):
    from sqlalchemy import select

    from wareon.db.base import init_db, session_factory
    from wareon.db.models import CustomMetric

    scripted(
        monkeypatch,
        [
            Resp(
                "tool_use",
                [
                    tool(
                        "t1",
                        "add_metric",
                        {
                            "key": "roas",
                            "title": "ROAS",
                            "formula": "revenue / ad_spend",
                            "direction": "up",
                        },
                    )
                ],
            ),
            Resp("end_turn", [txt("Предложил метрику, подтверди.")]),
        ],
    )
    uid = 810012  # по умолчанию semi

    async def flow():
        await init_db()
        async with session_factory() as s:
            result = await agent.run_agent(s, uid, "заведи ROAS")
        async with session_factory() as s:
            cm = await s.scalar(
                select(CustomMetric).where(CustomMetric.user_tg_id == uid)
            )
        return result, cm

    result, cm = asyncio.run(flow())
    assert cm is not None
    assert cm.pending is True  # ждёт подтверждения
    assert result.pending and result.pending[0][1] == "ROAS"


def test_agent_rejects_unsafe_formula(monkeypatch):
    from sqlalchemy import select

    from wareon.db.base import init_db, session_factory
    from wareon.db.models import CustomMetric

    scripted(
        monkeypatch,
        [
            Resp(
                "tool_use",
                [
                    tool(
                        "t1",
                        "add_metric",
                        {
                            "key": "evil",
                            "title": "Взлом",
                            "formula": "__import__('os')",
                            "direction": "up",
                        },
                    )
                ],
            ),
            Resp("end_turn", [txt("Не вышло завести — формула небезопасна.")]),
        ],
    )
    uid = 810013

    async def flow():
        await init_db()
        async with session_factory() as s:
            result = await agent.run_agent(s, uid, "заведи взлом")
        async with session_factory() as s:
            cm = await s.scalar(
                select(CustomMetric).where(CustomMetric.user_tg_id == uid)
            )
        return result, cm

    result, cm = asyncio.run(flow())
    assert cm is None  # опасная формула не сохранена
    assert not result.actions


def test_slug_sanitizes():
    assert agent._slug("Доля Рекламы!!!") == "metric"  # кириллица отбрасывается
    assert agent._slug("Ad Share %") == "ad_share"
    assert agent._slug("") == "metric"


# ── Руки ИИ: действия ────────────────────────────────────────────────────────
def _run_with_tool(monkeypatch, uid, tool_name, tool_input):
    from wareon.db.base import init_db, session_factory

    scripted(
        monkeypatch,
        [
            Resp("tool_use", [tool("t1", tool_name, tool_input)]),
            Resp("end_turn", [txt("Готово.")]),
        ],
    )

    async def flow():
        await init_db()
        async with session_factory() as s:
            return await agent.run_agent(s, uid, "сделай")

    return asyncio.run(flow())


def test_agent_sets_reminder(monkeypatch):
    from sqlalchemy import select

    from wareon.db.base import session_factory
    from wareon.db.models import Reminder

    res = _run_with_tool(monkeypatch, 830001, "set_reminder",
                         {"text": "написать клиенту", "hour": 10, "minute": 30})

    async def check():
        async with session_factory() as s:
            return await s.scalar(select(Reminder).where(Reminder.user_tg_id == 830001))

    rem = asyncio.run(check())
    assert rem is not None and rem.text == "написать клиенту"
    assert any("напоминание" in a for a in res.actions)


def test_agent_sets_alert(monkeypatch):
    from sqlalchemy import select

    from wareon.db.base import session_factory
    from wareon.db.models import AlertSetting

    _run_with_tool(monkeypatch, 830002, "set_alert", {"threshold_pct": 25})

    async def check():
        async with session_factory() as s:
            return await s.scalar(select(AlertSetting).where(AlertSetting.user_tg_id == 830002))

    a = asyncio.run(check())
    assert a is not None and a.margin_threshold_pct == 25


def test_agent_schedules_report(monkeypatch):
    from sqlalchemy import select

    from wareon.db.base import session_factory
    from wareon.db.models import ReportSubscription

    _run_with_tool(monkeypatch, 830003, "schedule_report", {"kind": "ai", "hour": 9, "minute": 0})

    async def check():
        async with session_factory() as s:
            return await s.scalar(
                select(ReportSubscription).where(ReportSubscription.user_tg_id == 830003)
            )

    sub = asyncio.run(check())
    assert sub is not None and sub.kind == "ai"


def test_agent_remembers_and_recalls(monkeypatch):
    from wareon.db.base import init_db, session_factory

    res = _run_with_tool(monkeypatch, 830004, "remember", {"fact": "продаёт чехлы на WB"})
    assert any("запомнил" in a for a in res.actions)

    async def recall():
        await init_db()
        async with session_factory() as s:
            return await agent._load_memory(s, 830004)

    mem = asyncio.run(recall())
    assert "чехлы на WB" in mem


# ── Публикация в канал ───────────────────────────────────────────────────────
async def _seed_channel(session_factory_, uid, chat_id=-100500, title="Мой канал"):
    from wareon.db.models import TrackedChat

    async with session_factory_() as s:
        s.add(
            TrackedChat(
                chat_id=chat_id, title=title, chat_type="channel", added_by_tg_id=uid
            )
        )
        await s.commit()


def test_agent_posts_to_channel_on_autopilot(monkeypatch):
    from sqlalchemy import select

    from wareon.db.base import init_db, session_factory
    from wareon.db.models import OutgoingPost

    scripted(
        monkeypatch,
        [
            Resp(
                "tool_use",
                [tool("t1", "post_to_channel", {"channel": "Мой канал", "text": "Скидка 20%!"})],
            ),
            Resp("end_turn", [txt("Опубликую пост.")]),
        ],
    )
    uid = 840001

    async def flow():
        await init_db()
        await _seed_channel(session_factory, uid, chat_id=-100501)
        async with session_factory() as s:
            await agent.set_autonomy(s, uid, "autopilot")
        async with session_factory() as s:
            result = await agent.run_agent(s, uid, "выложи пост про скидку")
        async with session_factory() as s:
            post = await s.scalar(select(OutgoingPost).where(OutgoingPost.user_tg_id == uid))
        return result, post

    result, post = asyncio.run(flow())
    assert post is not None
    assert post.status == "ready"  # автопилот — сразу в очередь на публикацию
    assert post.text == "Скидка 20%!"
    assert not result.pending_posts  # ничего подтверждать не нужно


def test_agent_proposes_post_on_semi(monkeypatch):
    from sqlalchemy import select

    from wareon.db.base import init_db, session_factory
    from wareon.db.models import OutgoingPost

    scripted(
        monkeypatch,
        [
            Resp(
                "tool_use",
                [tool("t1", "post_to_channel", {"channel": "Мой канал", "text": "Новинка!"})],
            ),
            Resp("end_turn", [txt("Подготовил пост, подтверди.")]),
        ],
    )
    uid = 840002  # semi по умолчанию

    async def flow():
        await init_db()
        await _seed_channel(session_factory, uid, chat_id=-100502)
        async with session_factory() as s:
            result = await agent.run_agent(s, uid, "выложи пост")
        async with session_factory() as s:
            post = await s.scalar(select(OutgoingPost).where(OutgoingPost.user_tg_id == uid))
        return result, post

    result, post = asyncio.run(flow())
    assert post is not None
    assert post.status == "pending"  # ждёт подтверждения
    assert result.pending_posts and result.pending_posts[0][1] == "Мой канал"


def test_agent_sets_voice(monkeypatch):
    from wareon.db.base import init_db, session_factory

    res = _run_with_tool(
        monkeypatch, 850001, "set_voice",
        {"description": "дружелюбно, на ты, с эмодзи, коротко"},
    )
    assert any("стиль" in a for a in res.actions)

    async def check():
        await init_db()
        async with session_factory() as s:
            return await agent.get_voice(s, 850001)

    voice = asyncio.run(check())
    assert voice is not None and "эмодзи" in voice


def test_voice_injected_into_context(monkeypatch):
    """Голос бренда попадает в первое сообщение, которое видит модель."""
    from wareon.db.base import init_db, session_factory

    captured = {}

    async def fake_create(messages):
        captured["first"] = messages[0]["content"]
        return Resp("end_turn", [txt("ок")])

    monkeypatch.setattr(agent, "_create_message", fake_create)
    monkeypatch.setattr(settings, "anthropic_api_key", "test-key")
    uid = 850002

    async def flow():
        await init_db()
        async with session_factory() as s:
            await agent.set_voice(s, uid, "строго и официально, на вы")
        async with session_factory() as s:
            await agent.run_agent(s, uid, "напиши пост")

    asyncio.run(flow())
    assert "Голос бренда" in captured["first"]
    assert "официально" in captured["first"]


def test_agent_post_without_channel(monkeypatch):
    from wareon.db.base import init_db, session_factory

    scripted(
        monkeypatch,
        [
            Resp(
                "tool_use",
                [tool("t1", "post_to_channel", {"channel": "Канал", "text": "Привет"})],
            ),
            Resp("end_turn", [txt("Каналов нет.")]),
        ],
    )
    uid = 840003

    async def flow():
        await init_db()
        async with session_factory() as s:
            return await agent.run_agent(s, uid, "выложи пост")

    result = asyncio.run(flow())
    assert not result.pending_posts
    assert not result.actions
