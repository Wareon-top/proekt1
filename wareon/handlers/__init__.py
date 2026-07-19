from aiogram import Dispatcher

from wareon.handlers import (
    agent,
    ai,
    business,
    calc,
    marketplace,
    pulse,
    qa,
    reports,
    schedule,
    social,
    start,
    tables,
)


def setup_routers(dp: Dispatcher) -> None:
    dp.include_router(start.router)
    dp.include_router(business.router)
    dp.include_router(marketplace.router)
    dp.include_router(social.router)
    dp.include_router(tables.router)
    dp.include_router(reports.router)
    dp.include_router(schedule.router)
    dp.include_router(pulse.router)
    dp.include_router(agent.router)
    dp.include_router(calc.router)
    dp.include_router(ai.router)
    # qa — последним: перехватывает весь прочий текст в личке как вопрос к таблице
    dp.include_router(qa.router)
