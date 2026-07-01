"""
main.py — Bot entry point.
Wires together routers, DB lifecycle, and starts polling.
No business logic lives here.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys

from dotenv import load_dotenv

# Must be first — loads .env before any os.getenv() call below
load_dotenv()

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from database import init_db, close_db
from handlers import messages as messages_router
from handlers import callbacks as callbacks_router

# ─── Logging ──────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


# ─── Build dispatcher ─────────────────────────────────────────────────────────

def build_dispatcher() -> Dispatcher:
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(messages_router.router)   # FSM states registered here first
    dp.include_router(callbacks_router.router)  # catch-all callbacks last
    return dp


# ─── Lifecycle ────────────────────────────────────────────────────────────────

async def on_startup(bot: Bot) -> None:
    """Called once before polling starts. DB must be ready before any update arrives."""
    await init_db()
    me = await bot.get_me()
    logger.info("✅  Bot live: @%s  (id=%d)", me.username, me.id)
    logger.info("✅  Polling started — Railway deployment healthy.")


async def on_shutdown(bot: Bot) -> None:
    await close_db()
    await bot.session.close()
    logger.info("Bot shut down cleanly.")


# ─── Entry point ──────────────────────────────────────────────────────────────

async def main() -> None:
    # Secret name on Railway / Replit: TOKEN  (not BOT_TOKEN)
    token = os.getenv("TOKEN")
    if not token:
        logger.critical(
            "❌  TOKEN env var is not set. "
            "Set it in Railway → Variables and redeploy."
        )
        sys.exit(1)

    bot = Bot(
        token=token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = build_dispatcher()

    async def _startup() -> None:
        await on_startup(bot)

    async def _shutdown() -> None:
        await on_shutdown(bot)

    dp.startup.register(_startup)
    dp.shutdown.register(_shutdown)

    logger.info("Starting polling (long-poll, no webhook)...")
    await dp.start_polling(
        bot,
        allowed_updates=dp.resolve_used_update_types(),
        drop_pending_updates=True,
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Stopped by operator.")
