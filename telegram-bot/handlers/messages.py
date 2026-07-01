"""
handlers/messages.py — Text & command handlers.
DAOs are module-level singletons; no session passing required with tortoise-orm.
"""

from __future__ import annotations

import functools
import logging
import os
import random

from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message

from database import ConversationDAO, UserDAO
from keyboards import (
    ai_chat_keyboard,
    developer_profile_keyboard,
    main_menu_keyboard,
    predictor_keyboard,
    system_pulse_keyboard,
)
from utils.ai_client import ask_ai, generate_prediction, get_system_pulse

logger = logging.getLogger(__name__)
router = Router(name="messages")

# Module-level DAO singletons — tortoise-orm manages the connection pool globally
_user_dao = UserDAO()
_conv_dao = ConversationDAO()

# ─── Media URLs ───────────────────────────────────────────────────────────────

_WELCOME_PHOTO     = "https://i.postimg.cc/3NzCRdQ9/Screenshot-20260630-090053.jpg"
_AI_GIF            = "https://i.postimg.cc/Z5jVsmQL/2189a5bcd78e4caabceae6814719581a-ezgif-com-crop.gif"
_DEV_PHOTO         = "https://i.postimg.cc/tgrqP2sW/IMG-20260620-133210-543.jpg"
_DEV_GIF           = "https://i.postimg.cc/4dp4ZWV5/fc51dcdde83ebae17aa8e99ba8e9fe93.gif"
_CHILL_GIF         = "https://i.postimg.cc/ZRJYbrc2/59acd10f528c5f5a91cdd51bff9e968f-ezgif-com-crop.gif"
_MONITOR_GIF       = "https://i.postimg.cc/4nkkNcRY/9b328b3561bc3750fb0718a802e19c62.gif"


# ─── FSM States ───────────────────────────────────────────────────────────────

class AIChat(StatesGroup):
    waiting_for_input = State()


# ─── Decorator: upsert user on every message ─────────────────────────────────

def register_user(handler):
    """
    Upserts the user record and increments message_count before the handler runs.
    @functools.wraps is required — aiogram uses __name__ to deduplicate handlers;
    without it every decorated function collapses to "wrapper" and overwrites each other.
    """
    @functools.wraps(handler)
    async def wrapper(message: Message, *args, **kwargs):
        await _user_dao.get_or_create(
            user_id=message.from_user.id,
            username=message.from_user.username,
            full_name=message.from_user.full_name,
            language_code=message.from_user.language_code,
        )
        await _user_dao.increment_message_count(message.from_user.id)
        return await handler(message, *args, **kwargs)
    return wrapper


# ─── /start ───────────────────────────────────────────────────────────────────

@router.message(CommandStart())
@register_user
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    caption = (
        "لا شيء.. كل شيء.. ٱلرمـ𖠌ــز الذي يختصر الحكاية.\n\n"
        "اختر ما تشاء من القائمة أدناه 👇"
    )
    try:
        await message.answer_photo(
            photo=_WELCOME_PHOTO,
            caption=caption,
            reply_markup=main_menu_keyboard(),
        )
    except Exception:
        await message.answer(caption, reply_markup=main_menu_keyboard())


# ─── /clear ───────────────────────────────────────────────────────────────────

@router.message(Command("clear"))
async def cmd_clear(message: Message, state: FSMContext) -> None:
    await state.clear()
    await _conv_dao.clear_history(message.from_user.id)
    await message.answer("🗑 تم مسح سجل المحادثة.")


# ─── Menu Buttons ─────────────────────────────────────────────────────────────

@router.message(F.text == "𖠌")
async def btn_ai_chat(message: Message, state: FSMContext) -> None:
    await state.set_state(AIChat.waiting_for_input)
    caption = "𖠌 — أنا هنا.\nاكتب ما يجول في خاطرك..."
    try:
        await message.answer_animation(
            animation=_AI_GIF,
            caption=caption,
            reply_markup=ai_chat_keyboard(),
        )
    except Exception:
        await message.answer(caption, reply_markup=ai_chat_keyboard())


@router.message(F.text == "◈ المطور")
@register_user
async def btn_developer(message: Message) -> None:
    text = (
        "◈ <b>المطور</b>\n\n"
        "مُهندس الظلام، نسّاج الكود، صانع الرمز.\n"
        "تواصل عبر المنصات أدناه 👇"
    )
    try:
        await message.answer_photo(photo=_DEV_PHOTO)
        await message.answer_animation(
            animation=_DEV_GIF,
            caption=text,
            reply_markup=developer_profile_keyboard(),
        )
    except Exception:
        await message.answer(text, reply_markup=developer_profile_keyboard())


@router.message(F.text == "◈ قناة الدعم ⚙️")
@register_user
async def btn_support(message: Message) -> None:
    link = os.getenv("SUPPORT_CHANNEL", "")
    await message.answer(
        f"⚙️ قناة الدعم:\n{link}" if link
        else "⚙️ لم يتم تعيين رابط قناة الدعم."
    )


@router.message(F.text == "◈ ٱلتحديثات 24/7 📢")
@register_user
async def btn_updates(message: Message) -> None:
    link = os.getenv("UPDATES_CHANNEL", "")
    await message.answer(
        f"📢 قناة التحديثات:\n{link}" if link
        else "📢 لم يتم تعيين رابط قناة التحديثات."
    )


@router.message(F.text == "◈ الهدية اليومية 🎁")
@register_user
async def btn_gift(message: Message) -> None:
    link = os.getenv("GIFT_CHANNEL", "")
    await message.answer(
        f"🎁 الهدية اليومية:\n{link}" if link
        else "🎁 لم يتم تعيين رابط قناة الهدايا."
    )


@router.message(F.text == "◈ إستراحة")
@register_user
async def btn_chill(message: Message) -> None:
    pool = [
        "خذ نفساً عميقاً.. الكون لا يستعجل.",
        "الصمت أحياناً هو أعمق إجابة.",
        "لا شيء يستحق أن يُربك سكينتك الداخلية.",
        "توقّف.. وانظر كم أنت بعيد عن حيث كنت.",
    ]
    quote = random.choice(pool)
    try:
        await message.answer_animation(
            animation=_CHILL_GIF,
            caption=f"☁️ {quote}",
        )
    except Exception:
        await message.answer(f"☁️ {quote}")


@router.message(F.text == "☰ معاينة")
@register_user
async def btn_preview(message: Message) -> None:
    await message.answer(
        "☰ <b>معاينة</b>\n\n"
        "هذا الروبوت قيد التطوير المستمر.\n"
        "كل ميزة تُبنى بعناية، وكل تفصيل يُحسب.\n"
        "ابقَ على اتصال — الجديد قادم."
    )


@router.message(F.text == "⧓ نبض النظام")
@register_user
async def btn_pulse(message: Message) -> None:
    waiting = await message.answer("⧓ جارٍ قراءة نبض النظام...")
    pulse = await get_system_pulse()
    await waiting.delete()
    await message.answer(
        f"⧓ <b>نبض النظام</b>\n\n"
        f"🖥 CPU: <code>{pulse['cpu_pct']}%</code>\n"
        f"💾 RAM: <code>{pulse['ram_used']} / {pulse['ram_total']} MB</code> ({pulse['ram_pct']}%)\n"
        f"💿 Disk: <code>{pulse['disk_used']} / {pulse['disk_total']} GB</code>\n"
        f"⏱ Uptime: <code>{pulse['uptime']}</code>\n\n"
        f"النظام يعمل بشكل طبيعي ✓",
        reply_markup=system_pulse_keyboard(),
    )


@router.message(F.text == "محاكي التوقع")
@register_user
async def btn_predictor(message: Message) -> None:
    prediction = generate_prediction(message.from_user.id)
    await message.answer(
        f"🔮 <b>توقّعك لهذا اليوم:</b>\n\n<i>{prediction}</i>",
        reply_markup=predictor_keyboard(),
    )


@router.message(F.text == "المراقبة")
@register_user
async def btn_monitor(message: Message) -> None:
    pulse = await get_system_pulse()
    bars = lambda pct: "█" * int(pct / 10) + "░" * (10 - int(pct / 10))
    monitor_text = (
        f"📡 <b>المراقبة — حالة النظام</b>\n\n"
        f"CPU  [{bars(pulse['cpu_pct'])}] {pulse['cpu_pct']}%\n"
        f"RAM  [{bars(pulse['ram_pct'])}] {pulse['ram_pct']}%\n\n"
        f"🕐 وقت التشغيل: <code>{pulse['uptime']}</code>\n"
        f"الحالة: 🟢 يعمل"
    )
    try:
        await message.answer_animation(
            animation=_MONITOR_GIF,
            caption=monitor_text,
        )
    except Exception:
        await message.answer(monitor_text)


# ─── AI Chat FSM handler ──────────────────────────────────────────────────────

@router.message(AIChat.waiting_for_input)
async def handle_ai_message(message: Message, state: FSMContext) -> None:
    """
    Full round-trip for the '𖠌' AI button:
      1. FSM state filter routes here (only while user is in AIChat mode)
      2. ConversationDAO.get_history() — lazy, only this user's rows
      3. ask_ai() — dispatches to AI_PROVIDER (env var)
      4. Both turns saved to DB
      5. Reply sent with inline controls
    """
    user_text = (message.text or "").strip()
    if not user_text:
        await message.answer("أرسل نصاً لأتمكن من الرد.")
        return

    thinking = await message.answer("𖠌 ...")

    history = await _conv_dao.get_history(message.from_user.id)
    reply = await ask_ai(history, user_text)

    await _conv_dao.add_message(message.from_user.id, "user",      user_text)
    await _conv_dao.add_message(message.from_user.id, "assistant", reply)

    await thinking.delete()
    await message.answer(reply, reply_markup=ai_chat_keyboard())
