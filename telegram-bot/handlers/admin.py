"""
handlers/admin.py — Hidden admin dashboard.
Completely independent from all existing handlers/callbacks/keyboards.
Access: only users whose Telegram ID matches ADMIN_ID or OWNER_ID env vars.
Zero impact on existing bot logic.
"""

from __future__ import annotations

import datetime
import logging
import os
import time

from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    Message,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    CallbackQuery,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from database import ConversationDAO, ConversationMessage, User, UserDAO
from utils.ai_client import get_system_pulse

logger = logging.getLogger(__name__)
router = Router(name="admin")

# ─── Admin ID resolution ──────────────────────────────────────────────────────

def _get_admin_ids() -> set[int]:
    """Return set of authorised admin Telegram IDs from env vars."""
    ids: set[int] = set()
    for key in ("ADMIN_ID", "OWNER_ID"):
        raw = os.getenv(key, "").strip()
        if raw.isdigit():
            ids.add(int(raw))
    return ids


def _is_admin(user_id: int) -> bool:
    return user_id in _get_admin_ids()


# ─── Admin keyboards ──────────────────────────────────────────────────────────

def _admin_menu_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📊 إحصائيات",   callback_data="adm:stats"),
        InlineKeyboardButton(text="💻 النظام",      callback_data="adm:sys"),
    )
    builder.row(
        InlineKeyboardButton(text="🗃 قاعدة البيانات", callback_data="adm:db"),
        InlineKeyboardButton(text="🔄 تحديث",         callback_data="adm:refresh"),
    )
    builder.row(
        InlineKeyboardButton(text="📢 إشعار جماعي",  callback_data="adm:broadcast_prompt"),
    )
    builder.row(
        InlineKeyboardButton(text="✖ إغلاق",         callback_data="adm:close"),
    )
    return builder.as_markup()


def _back_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="◀ رجوع", callback_data="adm:menu"))
    return builder.as_markup()


# ─── Dashboard text builders ──────────────────────────────────────────────────

async def _stats_text() -> str:
    total_users    = await User.all().count()
    total_messages = await ConversationMessage.all().count()
    return (
        "📊 <b>إحصائيات البوت</b>\n\n"
        f"👤 إجمالي المستخدمين:  <code>{total_users}</code>\n"
        f"💬 إجمالي الرسائل:     <code>{total_messages}</code>\n"
    )


async def _sys_text() -> str:
    p = await get_system_pulse()
    return (
        "💻 <b>حالة الخادم</b>\n\n"
        f"🖥 CPU:   <code>{p['cpu_pct']}%</code>\n"
        f"💾 RAM:   <code>{p['ram_used']} / {p['ram_total']} MB</code> ({p['ram_pct']}%)\n"
        f"💿 Disk:  <code>{p['disk_used']} / {p['disk_total']} GB</code>\n"
        f"⏱ Uptime: <code>{p['uptime']}</code>\n"
    )


async def _db_text() -> str:
    total_users    = await User.all().count()
    total_messages = await ConversationMessage.all().count()
    active_convs   = (
        await ConversationMessage.all()
        .distinct()
        .values_list("user_id", flat=True)
    )
    return (
        "🗃 <b>قاعدة البيانات</b>\n\n"
        f"📋 جدول users:                 <code>{total_users}</code> سجل\n"
        f"📋 جدول conversation_messages: <code>{total_messages}</code> سجل\n"
        f"🔗 مستخدمون لديهم محادثات:    <code>{len(active_convs)}</code>\n\n"
        "✅ الاتصال بقاعدة البيانات يعمل"
    )


def _menu_text() -> str:
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return (
        "🔐 <b>لوحة الإدارة</b>\n\n"
        f"🕐 {now}\n\n"
        "اختر إجراءً:"
    )


# ─── /admin command ───────────────────────────────────────────────────────────

@router.message(Command("admin"))
async def cmd_admin(message: Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id):
        return   # Silently ignore — do NOT reveal existence of admin panel

    await message.answer(_menu_text(), reply_markup=_admin_menu_keyboard())


# ─── Admin callback handler ───────────────────────────────────────────────────

@router.callback_query(lambda cq: (cq.data or "").startswith("adm:"))
async def admin_callback(cq: CallbackQuery, state: FSMContext) -> None:
    if not _is_admin(cq.from_user.id):
        await cq.answer()
        return

    action = (cq.data or "").removeprefix("adm:")

    if action == "menu" or action == "refresh":
        await cq.answer("تم التحديث ✓" if action == "refresh" else "")
        await cq.message.edit_text(_menu_text(), reply_markup=_admin_menu_keyboard())

    elif action == "stats":
        await cq.answer()
        text = await _stats_text()
        await cq.message.edit_text(text, reply_markup=_back_keyboard())

    elif action == "sys":
        await cq.answer("جارٍ القراءة...")
        text = await _sys_text()
        await cq.message.edit_text(text, reply_markup=_back_keyboard())

    elif action == "db":
        await cq.answer()
        text = await _db_text()
        await cq.message.edit_text(text, reply_markup=_back_keyboard())

    elif action == "broadcast_prompt":
        await cq.answer()
        await cq.message.edit_text(
            "📢 <b>إشعار جماعي</b>\n\n"
            "أرسل الرسالة مباشرة بعد هذا الأمر:\n"
            "<code>/broadcast نص الرسالة هنا</code>",
            reply_markup=_back_keyboard(),
        )

    elif action == "close":
        await cq.answer("تم الإغلاق.")
        await cq.message.delete()

    else:
        await cq.answer("إجراء غير معروف.")


# ─── /broadcast command ───────────────────────────────────────────────────────

@router.message(Command("broadcast"))
async def cmd_broadcast(message: Message) -> None:
    if not _is_admin(message.from_user.id):
        return   # Silently ignore

    text = message.text.removeprefix("/broadcast").strip()
    if not text:
        await message.answer("⚠️ أرسل نصاً بعد /broadcast")
        return

    all_user_ids = await User.all().values_list("id", flat=True)
    if not all_user_ids:
        await message.answer("لا يوجد مستخدمون حتى الآن.")
        return

    status_msg = await message.answer(
        f"📢 جارٍ الإرسال إلى <code>{len(all_user_ids)}</code> مستخدم..."
    )

    sent = 0
    failed = 0
    for uid in all_user_ids:
        try:
            await message.bot.send_message(uid, text)
            sent += 1
        except Exception:
            failed += 1

    await status_msg.edit_text(
        f"📢 <b>انتهى الإرسال</b>\n\n"
        f"✅ نجح: <code>{sent}</code>\n"
        f"❌ فشل: <code>{failed}</code>"
    )


# ─── /stats command (quick shortcut) ─────────────────────────────────────────

@router.message(Command("stats"))
async def cmd_stats(message: Message) -> None:
    if not _is_admin(message.from_user.id):
        return

    stats = await _stats_text()
    sys_info = await _sys_text()
    db_info = await _db_text()
    await message.answer(stats + "\n" + sys_info + "\n" + db_info)
