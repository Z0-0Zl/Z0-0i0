"""
handlers/callbacks.py — Centralised CallbackQuery handler.
Uses a single regex-based dispatcher instead of one handler per button.
Pattern: "<namespace>:<action>[:<payload>]"
"""

from __future__ import annotations

import logging
import re
from typing import Callable, Awaitable, Optional

from aiogram import Router
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext

from database import ConversationDAO, get_session_factory
from keyboards import ai_chat_keyboard, system_pulse_keyboard, predictor_keyboard
from utils.ai_client import get_system_pulse, generate_prediction

logger = logging.getLogger(__name__)
router = Router(name="callbacks")

# ─── Callback data pattern ────────────────────────────────────────────────────
# Format: <namespace>:<action>  (optional :<payload>)
_CB_PATTERN = re.compile(r"^(?P<ns>[a-z]+):(?P<action>[a-z]+)(?::(?P<payload>.+))?$")

# Type alias for a handler coroutine
_Handler = Callable[[CallbackQuery, Optional[str], FSMContext], Awaitable[None]]


# ─── Handler implementations ──────────────────────────────────────────────────

async def _ai_clear(cq: CallbackQuery, payload: Optional[str], state: FSMContext) -> None:
    """Wipe user's conversation history."""
    await state.clear()
    session_factory = get_session_factory()
    async with session_factory() as session:
        dao = ConversationDAO(session)
        await dao.clear_history(cq.from_user.id)
    await cq.answer("تم مسح المحادثة ✓", show_alert=False)
    await cq.message.edit_text("🗑 تم مسح سجل المحادثة. ابدأ من جديد.")


async def _ai_retry(cq: CallbackQuery, payload: Optional[str], state: FSMContext) -> None:
    """Inform user to just re-type their question."""
    await cq.answer("أعد كتابة رسالتك وسأرد من جديد.", show_alert=True)


async def _sys_refresh(cq: CallbackQuery, payload: Optional[str], state: FSMContext) -> None:
    """Refresh system pulse stats inline."""
    await cq.answer("جارٍ التحديث...")
    pulse = await get_system_pulse()
    text = (
        f"⧓ *نبض النظام — محدَّث*\n\n"
        f"🖥 CPU: `{pulse['cpu_pct']}%`\n"
        f"💾 RAM: `{pulse['ram_used']} / {pulse['ram_total']} MB` ({pulse['ram_pct']}%)\n"
        f"💿 Disk: `{pulse['disk_used']} / {pulse['disk_total']} GB`\n"
        f"⏱ Uptime: `{pulse['uptime']}`"
    )
    await cq.message.edit_text(text, parse_mode="Markdown", reply_markup=system_pulse_keyboard())


async def _sys_details(cq: CallbackQuery, payload: Optional[str], state: FSMContext) -> None:
    """Show extended system details."""
    await cq.answer()
    pulse = await get_system_pulse()
    text = (
        f"📊 *تفاصيل النظام*\n\n"
        f"• المعالج: `{pulse['cpu_pct']}%` استخدام\n"
        f"• الذاكرة المستخدمة: `{pulse['ram_used']} MB`\n"
        f"• إجمالي الذاكرة: `{pulse['ram_total']} MB`\n"
        f"• المساحة المستخدمة: `{pulse['disk_used']} GB`\n"
        f"• إجمالي المساحة: `{pulse['disk_total']} GB`\n"
        f"• وقت التشغيل: `{pulse['uptime']}`"
    )
    await cq.message.edit_text(text, parse_mode="Markdown", reply_markup=system_pulse_keyboard())


async def _pred_new(cq: CallbackQuery, payload: Optional[str], state: FSMContext) -> None:
    """Generate a fresh (next-day equivalent) prediction by slightly shifting seed."""
    await cq.answer("🔮 توقّع جديد...")
    import time
    # Mix current timestamp minute into seed for variation within the same day
    seed_offset = int(time.time() // 60)
    import hashlib
    from utils.ai_client import _PREDICTIONS
    digest = int(hashlib.sha256(
        f"{cq.from_user.id}:{seed_offset}".encode()
    ).hexdigest(), 16)
    prediction = _PREDICTIONS[digest % len(_PREDICTIONS)]
    await cq.message.edit_text(
        f"🔮 *توقّع جديد:*\n\n_{prediction}_",
        parse_mode="Markdown",
        reply_markup=predictor_keyboard(),
    )


async def _pred_history(cq: CallbackQuery, payload: Optional[str], state: FSMContext) -> None:
    """Placeholder — could later pull from DB."""
    await cq.answer("ميزة السجل قيد التطوير.", show_alert=True)


async def _nav_cancel(cq: CallbackQuery, payload: Optional[str], state: FSMContext) -> None:
    await state.clear()
    await cq.answer("تم الإلغاء.")
    await cq.message.delete()


# ─── Dispatch table — maps "ns:action" → handler ─────────────────────────────
# Adding a new button = one new entry here. No new handler function required
# as long as the namespace:action pattern is unique.

_DISPATCH: dict[str, _Handler] = {
    "ai:clear":    _ai_clear,
    "ai:retry":    _ai_retry,
    "sys:refresh": _sys_refresh,
    "sys:details": _sys_details,
    "pred:new":    _pred_new,
    "pred:history":_pred_history,
    "nav:cancel":  _nav_cancel,
}


# ─── Single centralised handler ───────────────────────────────────────────────

@router.callback_query()
async def centralised_callback_handler(cq: CallbackQuery, state: FSMContext) -> None:
    """
    One handler for ALL callback queries.
    Parses the callback_data with regex and dispatches to the correct function.
    Unknown callbacks are silently acknowledged to avoid Telegram timeout errors.
    """
    data = cq.data or ""
    match = _CB_PATTERN.match(data)

    if not match:
        logger.warning("Unknown callback_data received: %r", data)
        await cq.answer("❓ إجراء غير معروف.")
        return

    ns      = match.group("ns")
    action  = match.group("action")
    payload = match.group("payload")         # may be None
    key     = f"{ns}:{action}"

    handler = _DISPATCH.get(key)
    if handler is None:
        logger.warning("No handler registered for callback key: %r", key)
        await cq.answer("❓ لم يتم تسجيل هذا الإجراء بعد.")
        return

    try:
        await handler(cq, payload, state)
    except Exception as exc:
        logger.exception("Error in callback handler '%s': %s", key, exc)
        await cq.answer("⚠️ حدث خطأ. حاول مرة أخرى.", show_alert=True)
