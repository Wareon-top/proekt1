from aiogram import Dispatcher

from wareon.handlers import business, marketplace, reports, social, start, tables


def setup_routers(dp: Dispatcher) -> None:
    dp.include_router(start.router)
    dp.include_router(business.router)
    dp.include_router(marketplace.router)
    dp.include_router(social.router)
    dp.include_router(tables.router)
    dp.include_router(reports.router)
