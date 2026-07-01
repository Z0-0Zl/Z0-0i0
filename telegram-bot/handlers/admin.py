"""
handlers/admin.py — Professional hidden admin dashboard.
100% InlineKeyboardMarkup — no text commands listed in messages ever.
All navigation via edit_message_text / edit_message_reply_markup.

Access control:
  - Authorised: OWNER_ID and ADMIN_ID env vars only
  - Unauthorised access attempts → logged to admin_logs + silently ignored

Screens:
  main_menu → stats / sys / db / logs / broadcast / users / settings / close
  users     → users_list / users_search (FSM)
  broadcast → FSM: type text → confirm → send

FSM States:
  BroadcastState : waiting_for_text | waiting_for_confirm
  UserSearchState: waiting_for_id
"""

from __future__ import annotations

import datetime
import logging
import os

from aiogram import Router
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
)
from utils.ai_client import get_system_pulse

logger = logging.getLogger(__name__)
router = Router(name="admin")

_audit = AdminLogDAO()

# ═══════════════════════════════════════════════════════════════════════════════
# FSM States
# ═══════════════════════════════════════════════════════════════════════════════

class BroadcastState(StatesGroup):
    waiting_for_text    = State()
    waiting_for_confirm = State()


class UserSearchState(StatesGroup):
    waiting_for_id = State()


# ═══════════════════════════════════════════════════════════════════════════════
# Access control
# ═══════════════════════════════════════════════════════════════════════════════

def _get_admin_ids() -> set[int]:
    ids: set[int] = set()
    for key in ("ADMIN_ID", "OWNER_ID"):
        raw = os.getenv(key, "").strip()
        if raw.isdigit():
            ids.add(int(raw))
    return ids


def _is_admin(user_id: int) -> bool:
    return user_id in _get_admin_ids()


# ═══════════════════════════════════════════════════════════════════════════════
# Keyboards  (InlineKeyboardMarkup ONLY — no ReplyKeyboardMarkup)
# ═══════════════════════════════════════════════════════════════════════════════

def kb_main_menu() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text="📊 الإحصائيات",      callback_data="adm:stats"),
        InlineKeyboardButton(text="💻 حالة الخادم",      callback_data="adm:sys"),
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
        InlineKeyboardButton(text="👥 المستخدمون",       callback_data="adm:users"),
        InlineKeyboardButton(text="⚙️ الإعدادات",        callback_data="adm:settings"),
    )
    b.row(
        InlineKeyboardButton(text="✖ إغلاق",             callback_data="adm:close"),
    )
    return b.as_markup()


def kb_back() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.add(InlineKeyboardButton(text="◀️ رجوع", callback_data="adm:menu"))
    return b.as_markup()


def kb_broadcast_confirm() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text="✅ إرسال الآن",  callback_data="adm:broadcast_send"),
        InlineKeyboardButton(text="❌ إلغاء",        callback_data="adm:broadcast_cancel"),
    )
    return b.as_markup()


def kb_users() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text="📋 أحدث المستخدمين", callback_data="adm:users_list"),
    )
    b.row(
        InlineKeyboardButton(text="🔍 بحث بـ ID",        callback_data="adm:users_search"),
    )
    b.row(
        InlineKeyboardButton(text="◀️ رجوع",             callback_data="adm:menu"),
    )
    return b.as_markup()


def kb_user_detail(user_id: int) -> InlineKeyboardMarkup:
    """Keyboard shown after viewing a user's details."""
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text="🗑 مسح المحادثة", callback_data=f"adm:user_clear:{user_id}"),
    )
    b.row(
        InlineKeyboardButton(text="◀️ رجوع",          callback_data="adm:users"),
    )
    return b.as_markup()


# ═══════════════════════════════════════════════════════════════════════════════
# Text content builders
# ═══════════════════════════════════════════════════════════════════════════════

def _menu_text() -> str:
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return (
        "🔐 <b>لوحة الإدارة</b>\n"
        f"🕐 <code>{now}</code>\n\n"
        "اختر من القائمة:"
    )


async def _stats_text() -> str:
    total_u = await User.all().count()
    total_m = await ConversationMessage.all().count()
    total_a = await AdminLog.all().count()
    active  = await ConversationMessage.all().distinct().values_list("user_id", flat=True)
    avg_msg = round(total_m / total_u, 1) if total_u else 0
    return (
        "📊 <b>إحصائيات البوت</b>\n\n"
        f"👤 إجمالي المستخدمين:  <code>{total_u}</code>\n"
        f"💬 إجمالي الرسائل:     <code>{total_m}</code>\n"
        f"🔗 مستخدمون نشطون:    <code>{len(active)}</code>\n"
        f"📈 متوسط رسائل/مستخدم: <code>{avg_msg}</code>\n"
        f"🔐 إجراءات الإدمن:    <code>{total_a}</code>\n"
    )


async def _sys_text() -> str:
    p = await get_system_pulse()
    return (
        "💻 <b>حالة الخادم</b>\n\n"
        f"🖥 CPU:    <code>{p['cpu_pct']}%</code>\n"
        f"💾 RAM:    <code>{p['ram_used']} / {p['ram_total']} MB</code>  "
        f"(<code>{p['ram_pct']}%</code>)\n"
        f"💿 Disk:   <code>{p['disk_used']} / {p['disk_total']} GB</code>\n"
        f"⏱ Uptime: <code>{p['uptime']}</code>\n"
    )


async def _db_text() -> str:
    total_u = await User.all().count()
    total_m = await ConversationMessage.all().count()
    total_a = await AdminLog.all().count()
    active  = await ConversationMessage.all().distinct().values_list("user_id", flat=True)
    return (
        "🗃 <b>قاعدة البيانات</b>\n\n"
        f"📋 users:                 <code>{total_u}</code> سجل\n"
        f"📋 conversation_messages: <code>{total_m}</code> سجل\n"
        f"📋 admin_logs:            <code>{total_a}</code> سجل\n"
        f"🔗 مستخدمون لديهم محادثات: <code>{len(active)}</code>\n\n"
        "✅ الاتصال بقاعدة البيانات يعمل"
    )


async def _logs_text() -> str:
    entries = await _audit.get_recent(15)
    if not entries:
        return "📜 <b>سجل الأوامر</b>\n\nلا توجد سجلات بعد."
    lines = ["📜 <b>سجل أوامر الإدمن</b>  (آخر 15)\n"]
    for e in entries:
        ts  = e.executed_at.strftime("%m-%d %H:%M")
        det = f"  <i>{e.details[:35]}…</i>" if e.details else ""
        lines.append(f"<code>{ts}</code>  [{e.admin_id}]  <b>{e.command}</b>{det}")
    return "\n".join(lines)


async def _users_list_text() -> str:
    recent = await User.all().order_by("-joined_at").limit(10)
    if not recent:
        return "👥 <b>المستخدمون</b>\n\nلا يوجد مستخدمون بعد."
    lines = [f"👥 <b>أحدث {len(recent)} مستخدمين</b>\n"]
    for u in recent:
        name  = u.full_name or "—"
        uname = f"@{u.username}" if u.username else "بدون معرّف"
        joined = u.joined_at.strftime("%Y-%m-%d")
        lines.append(
            f"• <code>{u.id}</code>  {name}  ({uname})\n"
            f"  رسائل: <code>{u.message_count}</code>  انضم: <code>{joined}</code>"
        )
    return "\n".join(lines)


async def _user_detail_text(user_id: int) -> tuple[str, bool]:
    """Returns (text, found)."""
    u = await User.get_or_none(id=user_id)
    if not u:
        return f"❌ لم يُعثر على مستخدم بـ ID <code>{user_id}</code>", False
    msgs = await ConversationMessage.filter(user_id=user_id).count()
    uname  = f"@{u.username}" if u.username else "بدون معرّف"
    joined = u.joined_at.strftime("%Y-%m-%d %H:%M UTC")
    text = (
        f"👤 <b>تفاصيل المستخدم</b>\n\n"
        f"🆔 ID:        <code>{u.id}</code>\n"
        f"📛 الاسم:     {u.full_name}\n"
        f"🔗 معرّف:     {uname}\n"
        f"🌐 اللغة:     <code>{u.language_code or '—'}</code>\n"
        f"📅 الانضمام:  <code>{joined}</code>\n"
        f"💬 الرسائل:   <code>{u.message_count}</code>  "
        f"(محادثة: <code>{msgs}</code> سجل)\n"
    )
    return text, True


async def _settings_text() -> str:
    ai_provider = os.getenv("AI_PROVIDER", "groq")
    ai_model    = os.getenv("AI_MODEL", "—")
    owner_id    = os.getenv("OWNER_ID", "—")
    admin_id    = os.getenv("ADMIN_ID", "—")
    db_url_raw  = os.getenv("DATABASE_URL", "")
    db_host     = "—"
    if "@" in db_url_raw:
        try:
            db_host = db_url_raw.split("@")[1].split("/")[0]
        except Exception:
            pass
    return (
        "⚙️ <b>إعدادات البوت</b>\n\n"
        f"🤖 مزوّد الذكاء: <code>{ai_provider}</code>\n"
        f"🧠 النموذج:      <code>{ai_model}</code>\n"
        f"👑 OWNER_ID:     <code>{owner_id}</code>\n"
        f"🔐 ADMIN_ID:     <code>{admin_id}</code>\n"
        f"🗄 DB Host:      <code>{db_host}</code>\n"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# /admin command — entry point
# ═══════════════════════════════════════════════════════════════════════════════

@router.message(Command("admin"))
async def cmd_admin(message: Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id):
        await _audit.log(message.from_user.id, "UNAUTHORIZED", "/admin")
        return
    await state.clear()
    await _audit.log(message.from_user.id, "open_panel")
    await message.answer(_menu_text(), reply_markup=kb_main_menu())


# ═══════════════════════════════════════════════════════════════════════════════
# /stats  — quick shortcut (opens inline panel, not a text dump)
# ═══════════════════════════════════════════════════════════════════════════════

@router.message(Command("stats"))
async def cmd_stats(message: Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id):
        await _audit.log(message.from_user.id, "UNAUTHORIZED", "/stats")
        return
    await state.clear()
    await _audit.log(message.from_user.id, "stats_shortcut")
    await message.answer(await _stats_text(), reply_markup=kb_back())


# ═══════════════════════════════════════════════════════════════════════════════
# /broadcast — shortcut: opens FSM, no inline text arg required
# ═══════════════════════════════════════════════════════════════════════════════

@router.message(Command("broadcast"))
async def cmd_broadcast(message: Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id):
        await _audit.log(message.from_user.id, "UNAUTHORIZED", "/broadcast")
        return
    text_arg = (message.text or "").removeprefix("/broadcast").strip()
    if text_arg:
        await state.update_data(broadcast_text=text_arg)
        await state.set_state(BroadcastState.waiting_for_confirm)
        await _audit.log(message.from_user.id, "broadcast_start", text_arg[:80])
        total_u = await User.all().count()
        await message.answer(
            f"📢 <b>تأكيد الإرسال</b>\n\n"
            f"النص:\n<blockquote>{text_arg}</blockquote>\n\n"
            f"المستلمون: <code>{total_u}</code> مستخدم",
            reply_markup=kb_broadcast_confirm(),
        )
    else:
        await state.set_state(BroadcastState.waiting_for_text)
        await message.answer(
            "📢 <b>إشعار جماعي</b>\n\nأرسل نص الرسالة:",
            reply_markup=kb_back(),
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Master inline callback router  (all adm:* prefixed callbacks)
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(lambda cq: (cq.data or "").startswith("adm:"))
async def admin_callback(cq: CallbackQuery, state: FSMContext) -> None:
    # ── Access guard — log unauthorised attempts ──
    if not _is_admin(cq.from_user.id):
        await _audit.log(cq.from_user.id, "UNAUTHORIZED", cq.data)
        await cq.answer("⛔ غير مصرح.", show_alert=True)
        return

    action = (cq.data or "").removeprefix("adm:")

    # ── Dynamic user_clear:ID ──
    if action.startswith("user_clear:"):
        uid_str = action.split(":", 1)[1]
        if uid_str.lstrip("-").isdigit():
            uid = int(uid_str)
            await ConversationMessage.filter(user_id=uid).delete()
            await _audit.log(cq.from_user.id, "user_clear_history", str(uid))
            await cq.answer("✅ محادثة المستخدم مُسحت.")
            text, found = await _user_detail_text(uid)
            kb = kb_user_detail(uid) if found else kb_users()
            await cq.message.edit_text(text, reply_markup=kb)
        else:
            await cq.answer("معرف غير صحيح.", show_alert=True)
        return

    # ── Main menu ──
    if action in ("menu", "refresh"):
        await state.clear()
        await _audit.log(cq.from_user.id, action)
        await cq.answer("تم التحديث ✓" if action == "refresh" else "")
        await cq.message.edit_text(_menu_text(), reply_markup=kb_main_menu())

    # ── Statistics ──
    elif action == "stats":
        await cq.answer()
        await _audit.log(cq.from_user.id, "stats")
        await cq.message.edit_text(await _stats_text(), reply_markup=kb_back())

    # ── Server status ──
    elif action == "sys":
        await cq.answer("جارٍ القراءة…")
        await _audit.log(cq.from_user.id, "sys")
        await cq.message.edit_text(await _sys_text(), reply_markup=kb_back())

    # ── Database ──
    elif action == "db":
        await cq.answer()
        await _audit.log(cq.from_user.id, "db")
        await cq.message.edit_text(await _db_text(), reply_markup=kb_back())

    # ── Audit log ──
    elif action == "logs":
        await cq.answer()
        await _audit.log(cq.from_user.id, "view_logs")
        await cq.message.edit_text(await _logs_text(), reply_markup=kb_back())

    # ── Settings ──
    elif action == "settings":
        await cq.answer()
        await _audit.log(cq.from_user.id, "settings")
        await cq.message.edit_text(await _settings_text(), reply_markup=kb_back())

    # ── Users sub-menu ──
    elif action == "users":
        await cq.answer()
        await _audit.log(cq.from_user.id, "users_menu")
        await cq.message.edit_text(
            "👥 <b>إدارة المستخدمين</b>\n\nاختر إجراءً:",
            reply_markup=kb_users(),
        )

    # ── Users list ──
    elif action == "users_list":
        await cq.answer()
        await _audit.log(cq.from_user.id, "users_list")
        await cq.message.edit_text(await _users_list_text(), reply_markup=kb_users())

    # ── User search: open FSM ──
    elif action == "users_search":
        await cq.answer()
        await state.set_state(UserSearchState.waiting_for_id)
        await _audit.log(cq.from_user.id, "users_search_open")
        await cq.message.edit_text(
            "🔍 <b>بحث عن مستخدم</b>\n\nأرسل الـ Telegram ID (رقم):",
            reply_markup=kb_back(),
        )

    # ── Broadcast: open prompt ──
    elif action == "broadcast_prompt":
        await cq.answer()
        await state.set_state(BroadcastState.waiting_for_text)
        await cq.message.edit_text(
            "📢 <b>إشعار جماعي</b>\n\nأرسل نص الرسالة التي تريد بثّها:",
            reply_markup=kb_back(),
        )

    # ── Broadcast: confirm send ──
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
        await _audit.log(cq.from_user.id, "broadcast_done", f"sent={sent} failed={failed}")
        await cq.message.edit_text(
            f"📢 <b>اكتمل الإرسال</b>\n\n"
            f"✅ نجح: <code>{sent}</code>\n"
            f"❌ فشل: <code>{failed}</code>",
            reply_markup=kb_back(),
        )

    # ── Broadcast: cancel ──
    elif action == "broadcast_cancel":
        await state.clear()
        await cq.answer("تم الإلغاء.")
        await _audit.log(cq.from_user.id, "broadcast_cancel")
        await cq.message.edit_text(_menu_text(), reply_markup=kb_main_menu())

    # ── Close ──
    elif action == "close":
        await state.clear()
        await cq.answer("تم الإغلاق.")
        await _audit.log(cq.from_user.id, "close_panel")
        await cq.message.delete()

    else:
        await cq.answer("إجراء غير معروف.")


# ═══════════════════════════════════════════════════════════════════════════════
# FSM: Broadcast — receive text
# ═══════════════════════════════════════════════════════════════════════════════

@router.message(BroadcastState.waiting_for_text)
async def fsm_broadcast_text(message: Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id):
        await state.clear()
        return
    text = (message.text or "").strip()
    if not text:
        await message.answer("⚠️ النص فارغ — أرسل نصاً صحيحاً:", reply_markup=kb_back())
        return
    await state.update_data(broadcast_text=text)
    await state.set_state(BroadcastState.waiting_for_confirm)
    await _audit.log(message.from_user.id, "broadcast_text_set", text[:80])
    total_u = await User.all().count()
    await message.answer(
        f"📢 <b>تأكيد الإرسال</b>\n\n"
        f"النص:\n<blockquote>{text}</blockquote>\n\n"
        f"المستلمون: <code>{total_u}</code> مستخدم\n\n"
        "هل تريد الإرسال الآن؟",
        reply_markup=kb_broadcast_confirm(),
    )


@router.message(BroadcastState.waiting_for_confirm)
async def fsm_broadcast_confirm_guard(message: Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id):
        await state.clear()
        return
    await message.answer(
        "اضغط ✅ إرسال الآن أو ❌ إلغاء من الأزرار:",
        reply_markup=kb_broadcast_confirm(),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# FSM: User search — receive Telegram ID
# ═══════════════════════════════════════════════════════════════════════════════

@router.message(UserSearchState.waiting_for_id)
async def fsm_user_search(message: Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id):
        await state.clear()
        return
    raw = (message.text or "").strip()
    if not raw.lstrip("-").isdigit():
        await message.answer(
            "⚠️ أرسل رقماً صحيحاً (Telegram user ID):",
            reply_markup=kb_back(),
        )
        return
    uid = int(raw)
    await state.clear()
    await _audit.log(message.from_user.id, "users_search", str(uid))
    text, found = await _user_detail_text(uid)
    kb = kb_user_detail(uid) if found else kb_users()
    await message.answer(text, reply_markup=kb)
