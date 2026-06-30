"""
main.py — Bot entry point.
Wires together middleware, routers, DB, and starts polling.
No business logic lives here.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys

from dotenv import load_dotenv

# Load .env before anything else so all os.getenv() calls see the values
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


# ─── Bot & Dispatcher factory ─────────────────────────────────────────────────

def build_dispatcher() -> Dispatcher:
    """
    Create the dispatcher with FSM storage and register all routers.
    The order of router inclusion matters: more-specific routers first.
    """
    dp = Dispatcher(storage=MemoryStorage())

    # Register routers — messages first (contains FSM states),
    # callbacks second (catch-all callback handler).
    dp.include_router(messages_router.router)
    dp.include_router(callbacks_router.router)

    return dp


# ─── Startup / Shutdown hooks ─────────────────────────────────────────────────

async def on_startup(bot: Bot) -> None:
    """Runs once before polling begins."""
    await init_db()
    me = await bot.get_me()
    logger.info("Bot started: @%s (id=%d)", me.username, me.id)


async def on_shutdown(bot: Bot) -> None:
    """Runs once after polling stops."""
    await close_db()
    await bot.session.close()
    logger.info("Bot shut down cleanly.")


# ─── Main ─────────────────────────────────────────────────────────────────────

async def main() -> None:
    # FIX: env var is TOKEN (not BOT_TOKEN) — matches Railway/Replit secret name
    token = os.environ.get("TOKEN")
    if not token:
        logger.critical(
            "TOKEN is not set. Add it to Railway Variables or .env and restart."
        )
        sys.exit(1)

    bot = Bot(
        token=token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = build_dispatcher()

    # Register lifecycle hooks on the dispatcher
    dp.startup.register(lambda: on_startup(bot))
    dp.shutdown.register(lambda: on_shutdown(bot))

    logger.info("Starting polling (Railway / non-webhook mode)...")
    await dp.start_polling(
        bot,
        allowed_updates=dp.resolve_used_update_types(),
        drop_pending_updates=True,   # ignore messages sent while bot was offline
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped by operator.")
