"""
handlers/callbacks.py — Single centralised CallbackQuery handler.
Pattern: "<namespace>:<action>[:<payload>]"
Adding a button = one dict entry. No new handler function needed.
"""

from __future__ import annotations

import hashlib
import logging
import re
import time
from typing import Awaitable, Callable, Optional

from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from database import ConversationDAO
from keyboards import ai_chat_keyboard, predictor_keyboard, system_pulse_keyboard
from utils.ai_client import _PREDICTIONS, generate_prediction, get_system_pulse

logger = logging.getLogger(__name__)
router = Router(name="callbacks")

_CB_PATTERN = re.compile(r"^(?P<ns>[a-z]+):(?P<action>[a-z]+)(?::(?P<payload>.+))?$")
_Handler = Callable[[CallbackQuery, Optional[str], FSMContext], Awaitable[None]]

_conv_dao = ConversationDAO()


# ─── Handler functions ────────────────────────────────────────────────────────

async def _ai_clear(cq: CallbackQuery, _: Optional[str], state: FSMContext) -> None:
    await state.clear()
    await _conv_dao.clear_history(cq.from_user.id)
    await cq.answer("تم مسح المحادثة ✓")
    await cq.message.edit_text("🗑 تم مسح سجل المحادثة. ابدأ من جديد.")


async def _ai_retry(cq: CallbackQuery, _: Optional[str], state: FSMContext) -> None:
    await cq.answer("أعد كتابة رسالتك وسأرد من جديد.", show_alert=True)


async def _sys_refresh(cq: CallbackQuery, _: Optional[str], state: FSMContext) -> None:
    await cq.answer("جارٍ التحديث...")
    pulse = await get_system_pulse()
    await cq.message.edit_text(
        f"⧓ <b>نبض النظام — محدَّث</b>\n\n"
        f"🖥 CPU: <code>{pulse['cpu_pct']}%</code>\n"
        f"💾 RAM: <code>{pulse['ram_used']} / {pulse['ram_total']} MB</code> ({pulse['ram_pct']}%)\n"
        f"💿 Disk: <code>{pulse['disk_used']} / {pulse['disk_total']} GB</code>\n"
        f"⏱ Uptime: <code>{pulse['uptime']}</code>",
        reply_markup=system_pulse_keyboard(),
    )


async def _sys_details(cq: CallbackQuery, _: Optional[str], state: FSMContext) -> None:
    await cq.answer()
    pulse = await get_system_pulse()
    await cq.message.edit_text(
        f"📊 <b>تفاصيل النظام</b>\n\n"
        f"• المعالج: <code>{pulse['cpu_pct']}%</code>\n"
        f"• الذاكرة المستخدمة: <code>{pulse['ram_used']} MB</code>\n"
        f"• إجمالي الذاكرة: <code>{pulse['ram_total']} MB</code>\n"
        f"• المساحة المستخدمة: <code>{pulse['disk_used']} GB</code>\n"
        f"• إجمالي المساحة: <code>{pulse['disk_total']} GB</code>\n"
        f"• وقت التشغيل: <code>{pulse['uptime']}</code>",
        reply_markup=system_pulse_keyboard(),
    )


async def _pred_new(cq: CallbackQuery, _: Optional[str], state: FSMContext) -> None:
    await cq.answer("🔮 توقّع جديد...")
    # Mix minute-level timestamp into seed for intra-day variation
    seed_offset = int(time.time() // 60)
    digest = int(
        hashlib.sha256(f"{cq.from_user.id}:{seed_offset}".encode()).hexdigest(), 16
    )
    prediction = _PREDICTIONS[digest % len(_PREDICTIONS)]
    await cq.message.edit_text(
        f"🔮 <b>توقّع جديد:</b>\n\n<i>{prediction}</i>",
        reply_markup=predictor_keyboard(),
    )


async def _pred_history(cq: CallbackQuery, _: Optional[str], state: FSMContext) -> None:
    await cq.answer("ميزة السجل قيد التطوير.", show_alert=True)


async def _nav_cancel(cq: CallbackQuery, _: Optional[str], state: FSMContext) -> None:
    await state.clear()
    await cq.answer("تم الإلغاء.")
    await cq.message.delete()


# ─── Dispatch table ───────────────────────────────────────────────────────────

_DISPATCH: dict[str, _Handler] = {
    "ai:clear":     _ai_clear,
    "ai:retry":     _ai_retry,
    "sys:refresh":  _sys_refresh,
    "sys:details":  _sys_details,
    "pred:new":     _pred_new,
    "pred:history": _pred_history,
    "nav:cancel":   _nav_cancel,
}


# ─── Single entry point for ALL callbacks ────────────────────────────────────

@router.callback_query()
async def centralised_callback_handler(cq: CallbackQuery, state: FSMContext) -> None:
    """
    Parses callback_data with regex → dispatches to handler via dict lookup.
    Unknown data is acknowledged (prevents Telegram 'query timeout' errors).
    """
    data  = cq.data or ""
    match = _CB_PATTERN.match(data)

    if not match:
        logger.warning("Unrecognised callback_data: %r", data)
        await cq.answer("❓ إجراء غير معروف.")
        return

    key     = f"{match.group('ns')}:{match.group('action')}"
    payload = match.group("payload")
    handler = _DISPATCH.get(key)

    if handler is None:
        logger.warning("No handler for callback key: %r", key)
        await cq.answer("❓ لم يتم تسجيل هذا الإجراء بعد.")
        return

    try:
        await handler(cq, payload, state)
    except Exception as exc:
        logger.exception("Callback '%s' raised: %s", key, exc)
        await cq.answer("⚠️ حدث خطأ. حاول مرة أخرى.", show_alert=True)
