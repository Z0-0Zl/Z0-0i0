"""
handlers/admin.py — Hidden admin dashboard.
Completely independent from all existing handlers/callbacks/keyboards.
Access: only users whose Telegram ID matches ADMIN_ID or OWNER_ID env vars.
Zero impact on existing bot logic.

Features:
  - Full InlineKeyboardMarkup navigation (no text commands listed in messages)
  - FSM-based broadcast flow (button → type message → confirm → send)
  - Persistent audit log: every admin action is recorded in admin_logs table
  - /admin — open panel  |  /stats — quick shortcut  |  /broadcast — shortcut
"""

from __future__ import annotations

import datetime
import logging
import os

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from database import (
    AdminLog,
    AdminLogDAO,
    ConversationMessage,
    User,
    UserDAO,
)
from utils.ai_client import get_system_pulse

logger = logging.getLogger(__name__)
router = Router(name="admin")

_audit = AdminLogDAO()


# ─── FSM States ───────────────────────────────────────────────────────────────

class BroadcastState(StatesGroup):
    waiting_for_text    = State()   # admin types the message
    waiting_for_confirm = State()   # admin confirms or cancels


# ─── Admin ID resolution ──────────────────────────────────────────────────────

def _get_admin_ids() -> set[int]:
    ids: set[int] = set()
    for key in ("ADMIN_ID", "OWNER_ID"):
        raw = os.getenv(key, "").strip()
        if raw.isdigit():
            ids.add(int(raw))
    return ids


def _is_admin(user_id: int) -> bool:
    return user_id in _get_admin_ids()


# ─── Keyboards ────────────────────────────────────────────────────────────────

def _admin_menu_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text="📊 إحصائيات",        callback_data="adm:stats"),
        InlineKeyboardButton(text="💻 الخادم",           callback_data="adm:sys"),
    )
    b.row(
        InlineKeyboardButton(text="🗃 قاعدة البيانات",   callback_data="adm:db"),
        InlineKeyboardButton(text="🔄 تحديث",            callback_data="adm:refresh"),
    )
    b.row(
        InlineKeyboardButton(text="📢 إشعار جماعي",     callback_data="adm:broadcast_prompt"),
        InlineKeyboardButton(text="📜 سجل الأوامر",      callback_data="adm:logs"),
    )
    b.row(
        InlineKeyboardButton(text="✖ إغلاق",             callback_data="adm:close"),
    )
    return b.as_markup()


def _back_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.add(InlineKeyboardButton(text="◀ رجوع", callback_data="adm:menu"))
    return b.as_markup()


def _broadcast_confirm_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text="✅ إرسال",   callback_data="adm:broadcast_send"),
        InlineKeyboardButton(text="❌ إلغاء",   callback_data="adm:broadcast_cancel"),
    )
    return b.as_markup()


# ─── Text builders ────────────────────────────────────────────────────────────

def _menu_text() -> str:
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return f"🔐 <b>لوحة الإدارة</b>\n🕐 {now}\n\nاختر إجراءً:"


async def _stats_text() -> str:
    total_u = await User.all().count()
    total_m = await ConversationMessage.all().count()
    total_a = await AdminLog.all().count()
    return (
        "📊 <b>إحصائيات البوت</b>\n\n"
        f"👤 المستخدمون:      <code>{total_u}</code>\n"
        f"💬 الرسائل:         <code>{total_m}</code>\n"
        f"🔐 أوامر الإدمن:   <code>{total_a}</code>\n"
    )


async def _sys_text() -> str:
    p = await get_system_pulse()
    return (
        "💻 <b>حالة الخادم</b>\n\n"
        f"🖥 CPU:    <code>{p['cpu_pct']}%</code>\n"
        f"💾 RAM:    <code>{p['ram_used']} / {p['ram_total']} MB</code>  ({p['ram_pct']}%)\n"
        f"💿 Disk:   <code>{p['disk_used']} / {p['disk_total']} GB</code>\n"
        f"⏱ Uptime: <code>{p['uptime']}</code>\n"
    )


async def _db_text() -> str:
    total_u = await User.all().count()
    total_m = await ConversationMessage.all().count()
    active  = await (
        ConversationMessage.all().distinct().values_list("user_id", flat=True)
    )
    total_a = await AdminLog.all().count()
    return (
        "🗃 <b>قاعدة البيانات</b>\n\n"
        f"📋 users:                 <code>{total_u}</code>\n"
        f"📋 conversation_messages: <code>{total_m}</code>\n"
        f"📋 admin_logs:            <code>{total_a}</code>\n"
        f"🔗 مستخدمون نشطون:       <code>{len(active)}</code>\n\n"
        "✅ الاتصال يعمل"
    )


async def _logs_text() -> str:
    entries = await _audit.get_recent(15)
    if not entries:
        return "📜 <b>سجل الأوامر</b>\n\nلا توجد سجلات بعد."

    lines = ["📜 <b>سجل أوامر الإدمن</b> (آخر 15)\n"]
    for e in entries:
        ts   = e.executed_at.strftime("%m-%d %H:%M")
        det  = f" — {e.details[:30]}…" if e.details else ""
        lines.append(f"<code>{ts}</code> [{e.admin_id}] <b>{e.command}</b>{det}")
    return "\n".join(lines)


# ─── /admin command ───────────────────────────────────────────────────────────

@router.message(Command("admin"))
async def cmd_admin(message: Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id):
        return
    await state.clear()
    await _audit.log(message.from_user.id, "open_panel")
    await message.answer(_menu_text(), reply_markup=_admin_menu_kb())


# ─── /stats shortcut ─────────────────────────────────────────────────────────

@router.message(Command("stats"))
async def cmd_stats(message: Message) -> None:
    if not _is_admin(message.from_user.id):
        return
    await _audit.log(message.from_user.id, "stats_shortcut")
    text = (await _stats_text()) + "\n" + (await _sys_text()) + "\n" + (await _db_text())
    await message.answer(text, reply_markup=_back_kb())


# ─── /broadcast shortcut (opens FSM, no text parameter needed) ───────────────

@router.message(Command("broadcast"))
async def cmd_broadcast_shortcut(message: Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id):
        return
    # If text passed inline (/broadcast النص) send directly with confirm step
    text_arg = message.text.removeprefix("/broadcast").strip()
    if text_arg:
        await state.update_data(broadcast_text=text_arg)
        await state.set_state(BroadcastState.waiting_for_confirm)
        await _audit.log(message.from_user.id, "broadcast_start", text_arg[:80])
        total_u = await User.all().count()
        await message.answer(
            f"📢 <b>تأكيد الإرسال</b>\n\n"
            f"النص:\n<blockquote>{text_arg}</blockquote>\n\n"
            f"المستلمون: <code>{total_u}</code> مستخدم",
            reply_markup=_broadcast_confirm_kb(),
        )
    else:
        await state.set_state(BroadcastState.waiting_for_text)
        await message.answer(
            "📢 <b>إشعار جماعي</b>\n\nأرسل نص الرسالة:",
            reply_markup=_back_kb(),
        )


# ─── Admin inline callbacks ───────────────────────────────────────────────────

@router.callback_query(lambda cq: (cq.data or "").startswith("adm:"))
async def admin_callback(cq: CallbackQuery, state: FSMContext) -> None:
    if not _is_admin(cq.from_user.id):
        await cq.answer()
        return

    action = (cq.data or "").removeprefix("adm:")

    # ── Main menu / refresh ──
    if action in ("menu", "refresh"):
        await state.clear()
        notice = "تم التحديث ✓" if action == "refresh" else ""
        await _audit.log(cq.from_user.id, action)
        await cq.answer(notice)
        await cq.message.edit_text(_menu_text(), reply_markup=_admin_menu_kb())

    # ── Statistics ──
    elif action == "stats":
        await cq.answer()
        await _audit.log(cq.from_user.id, "stats")
        await cq.message.edit_text(await _stats_text(), reply_markup=_back_kb())

    # ── Server info ──
    elif action == "sys":
        await cq.answer("جارٍ القراءة…")
        await _audit.log(cq.from_user.id, "sys")
        await cq.message.edit_text(await _sys_text(), reply_markup=_back_kb())

    # ── Database info ──
    elif action == "db":
        await cq.answer()
        await _audit.log(cq.from_user.id, "db")
        await cq.message.edit_text(await _db_text(), reply_markup=_back_kb())

    # ── Audit log ──
    elif action == "logs":
        await cq.answer()
        await _audit.log(cq.from_user.id, "view_logs")
        await cq.message.edit_text(await _logs_text(), reply_markup=_back_kb())

    # ── Broadcast: open prompt ──
    elif action == "broadcast_prompt":
        await cq.answer()
        await state.set_state(BroadcastState.waiting_for_text)
        await cq.message.edit_text(
            "📢 <b>إشعار جماعي</b>\n\nأرسل نص الرسالة التي تريد إرسالها:",
            reply_markup=_back_kb(),
        )

    # ── Broadcast: confirm & send ──
    elif action == "broadcast_send":
        data = await state.get_data()
        broadcast_text = data.get("broadcast_text", "")
        if not broadcast_text:
            await cq.answer("لم يُحدَّد نص.", show_alert=True)
            return

        await state.clear()
        await cq.answer("جارٍ الإرسال…")
        await _audit.log(cq.from_user.id, "broadcast_send", broadcast_text[:120])

        all_ids = await User.all().values_list("id", flat=True)
        await cq.message.edit_text(
            f"📢 جارٍ الإرسال إلى <code>{len(all_ids)}</code> مستخدم…"
        )

        sent = failed = 0
        for uid in all_ids:
            try:
                await cq.message.bot.send_message(uid, broadcast_text)
                sent += 1
            except Exception:
                failed += 1

        await _audit.log(
            cq.from_user.id, "broadcast_done",
            f"sent={sent} failed={failed}",
        )
        await cq.message.edit_text(
            f"📢 <b>اكتمل الإرسال</b>\n\n"
            f"✅ نجح: <code>{sent}</code>\n"
            f"❌ فشل: <code>{failed}</code>",
            reply_markup=_back_kb(),
        )

    # ── Broadcast: cancel ──
    elif action == "broadcast_cancel":
        await state.clear()
        await cq.answer("تم الإلغاء.")
        await _audit.log(cq.from_user.id, "broadcast_cancel")
        await cq.message.edit_text(_menu_text(), reply_markup=_admin_menu_kb())

    # ── Close ──
    elif action == "close":
        await state.clear()
        await cq.answer("تم الإغلاق.")
        await _audit.log(cq.from_user.id, "close_panel")
        await cq.message.delete()

    else:
        await cq.answer("إجراء غير معروف.")


# ─── FSM: receive broadcast text ─────────────────────────────────────────────

@router.message(BroadcastState.waiting_for_text)
async def broadcast_text_received(message: Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id):
        await state.clear()
        return

    text = message.text or ""
    if not text.strip():
        await message.answer("⚠️ النص فارغ. أرسل نصاً صحيحاً:", reply_markup=_back_kb())
        return

    await state.update_data(broadcast_text=text)
    await state.set_state(BroadcastState.waiting_for_confirm)
    await _audit.log(message.from_user.id, "broadcast_text_set", text[:80])

    total_u = await User.all().count()
    await message.answer(
        f"📢 <b>تأكيد الإرسال</b>\n\n"
        f"النص:\n<blockquote>{text}</blockquote>\n\n"
        f"المستلمون: <code>{total_u}</code> مستخدم\n\n"
        "هل تريد الإرسال؟",
        reply_markup=_broadcast_confirm_kb(),
    )


# ─── FSM: guard — while in broadcast state, ignore non-admin or stray text ───

@router.message(BroadcastState.waiting_for_confirm)
async def broadcast_confirm_guard(message: Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id):
        await state.clear()
        return
    await message.answer(
        "اضغط ✅ إرسال أو ❌ إلغاء من الأزرار أعلاه.",
        reply_markup=_broadcast_confirm_kb(),
    )
