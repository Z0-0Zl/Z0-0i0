"""
handlers/messages.py — All text/command message handlers.
Business logic stays in utils/; this file only orchestrates.
"""

from __future__ import annotations

import logging
from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from database import UserDAO, ConversationDAO, get_session_factory
from keyboards import (
    main_menu_keyboard,
    developer_profile_keyboard,
    ai_chat_keyboard,
    system_pulse_keyboard,
    predictor_keyboard,
)
from utils.ai_client import ask_ai, generate_prediction, get_system_pulse

logger = logging.getLogger(__name__)
router = Router(name="messages")


# ─── FSM: AI Chat ─────────────────────────────────────────────────────────────

class AIChat(StatesGroup):
    """Track whether the user is currently in AI chat mode."""
    waiting_for_input = State()


# ─── Decorator: log user & upsert DB record ───────────────────────────────────

def register_user(handler):
    """
    Middleware-style decorator that upserts the user into the DB
    and increments their message count before calling the real handler.
    """
    async def wrapper(message: Message, *args, **kwargs):
        session_factory = get_session_factory()
        async with session_factory() as session:
            dao = UserDAO(session)
            await dao.get_or_create(
                user_id=message.from_user.id,
                username=message.from_user.username,
                full_name=message.from_user.full_name,
                language_code=message.from_user.language_code,
            )
            await dao.increment_message_count(message.from_user.id)
        return await handler(message, *args, **kwargs)
    return wrapper


# ─── /start ───────────────────────────────────────────────────────────────────

@router.message(CommandStart())
@register_user
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    welcome = (
        "لا شيء.. كل شيء.. ٱلرمـ𖠌ــز الذي يختصر الحكاية.\n\n"
        "اختر ما تشاء من القائمة أدناه 👇"
    )
    await message.answer(welcome, reply_markup=main_menu_keyboard())


# ─── /clear — reset AI conversation ──────────────────────────────────────────

@router.message(Command("clear"))
async def cmd_clear(message: Message, state: FSMContext) -> None:
    await state.clear()
    session_factory = get_session_factory()
    async with session_factory() as session:
        dao = ConversationDAO(session)
        await dao.clear_history(message.from_user.id)
    await message.answer("🗑 تم مسح سجل المحادثة.")


# ─── Main Menu Button Handlers ────────────────────────────────────────────────

@router.message(F.text == "𖠌")
async def btn_ai_chat(message: Message, state: FSMContext) -> None:
    """Enter AI chat mode."""
    await state.set_state(AIChat.waiting_for_input)
    await message.answer(
        "𖠌 — أنا هنا.\nاكتب ما يجول في خاطرك...",
        reply_markup=ai_chat_keyboard(),
    )


@router.message(F.text == "◈ المطور")
@register_user
async def btn_developer(message: Message) -> None:
    card = (
        "◈ *المطور*\n\n"
        "مُهندس الظلام، نسّاج الكود، صانع الرمز.\n"
        "تواصل عبر المنصات أدناه 👇"
    )
    await message.answer(
        card,
        parse_mode="Markdown",
        reply_markup=developer_profile_keyboard(),
    )


@router.message(F.text == "◈ قناة الدعم ⚙️")
@register_user
async def btn_support(message: Message) -> None:
    import os
    link = os.getenv("SUPPORT_CHANNEL", "#")
    await message.answer(f"⚙️ قناة الدعم:\n{link}")


@router.message(F.text == "◈ ٱلتحديثات 24/7 📢")
@register_user
async def btn_updates(message: Message) -> None:
    import os
    link = os.getenv("UPDATES_CHANNEL", "#")
    await message.answer(f"📢 قناة التحديثات:\n{link}")


@router.message(F.text == "◈ الهدية اليومية 🎁")
@register_user
async def btn_gift(message: Message) -> None:
    import os
    link = os.getenv("GIFT_CHANNEL", "#")
    await message.answer(f"🎁 الهدية اليومية:\n{link}")


@router.message(F.text == "◈ إستراحة")
@register_user
async def btn_chill(message: Message) -> None:
    msgs = [
        "خذ نفساً عميقاً.. الكون لا يستعجل.",
        "الصمت أحياناً هو أعمق إجابة.",
        "لا شيء يستحق أن يُربك سكينتك الداخلية.",
        "توقّف.. وانظر كم أنت بعيد عن حيث كنت.",
    ]
    import random
    await message.answer(f"☁️ {random.choice(msgs)}")


@router.message(F.text == "☰ معاينة")
@register_user
async def btn_preview(message: Message) -> None:
    await message.answer(
        "☰ *معاينة*\n\n"
        "هذا الروبوت قيد التطوير المستمر.\n"
        "كل ميزة تُبنى بعناية، وكل تفصيل يُحسب.\n"
        "ابقَ على اتصال — الجديد قادم.",
        parse_mode="Markdown",
    )


@router.message(F.text == "⧓ نبض النظام")
@register_user
async def btn_pulse(message: Message) -> None:
    await message.answer("⧓ جارٍ قراءة نبض النظام...", reply_markup=system_pulse_keyboard())
    pulse = await get_system_pulse()
    text = (
        f"⧓ *نبض النظام*\n\n"
        f"🖥 CPU: `{pulse['cpu_pct']}%`\n"
        f"💾 RAM: `{pulse['ram_used']} / {pulse['ram_total']} MB` ({pulse['ram_pct']}%)\n"
        f"💿 Disk: `{pulse['disk_used']} / {pulse['disk_total']} GB`\n"
        f"⏱ Uptime: `{pulse['uptime']}`\n\n"
        f"النظام يعمل بشكل طبيعي ✓"
    )
    await message.answer(text, parse_mode="Markdown", reply_markup=system_pulse_keyboard())


@router.message(F.text == "محاكي التوقع")
@register_user
async def btn_predictor(message: Message) -> None:
    prediction = generate_prediction(message.from_user.id)
    await message.answer(
        f"🔮 *توقّعك لهذا اليوم:*\n\n_{prediction}_",
        parse_mode="Markdown",
        reply_markup=predictor_keyboard(),
    )


@router.message(F.text == "المراقبة")
@register_user
async def btn_monitor(message: Message) -> None:
    pulse = await get_system_pulse()
    bars = lambda pct: "█" * int(pct / 10) + "░" * (10 - int(pct / 10))
    text = (
        f"📡 *المراقبة — حالة النظام*\n\n"
        f"CPU  [{bars(pulse['cpu_pct'])}] {pulse['cpu_pct']}%\n"
        f"RAM  [{bars(pulse['ram_pct'])}] {pulse['ram_pct']}%\n\n"
        f"🕐 وقت التشغيل: `{pulse['uptime']}`\n"
        f"الحالة: 🟢 يعمل"
    )
    await message.answer(text, parse_mode="Markdown")


# ─── AI Chat — catch-all for FSM state ───────────────────────────────────────

@router.message(AIChat.waiting_for_input)
async def handle_ai_message(message: Message, state: FSMContext) -> None:
    """
    Processes free text while user is in AI chat mode.
    Fetches conversation history lazily, calls AI, persists both turns.
    """
    user_id  = message.from_user.id
    user_text = message.text or ""

    if not user_text.strip():
        await message.answer("أرسل نصاً لأتمكن من الرد.")
        return

    thinking = await message.answer("𖠌 ...")

    session_factory = get_session_factory()
    async with session_factory() as session:
        conv_dao = ConversationDAO(session)

        # Lazy-load only this user's history
        history = await conv_dao.get_history(user_id)

        # Call AI
        reply = await ask_ai(history, user_text)

        # Persist both turns
        await conv_dao.add_message(user_id, "user",      user_text)
        await conv_dao.add_message(user_id, "assistant", reply)

    await thinking.delete()
    await message.answer(reply, reply_markup=ai_chat_keyboard())
