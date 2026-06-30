"""
handlers/messages.py — All text/command message handlers.
Business logic stays in utils/; this file only orchestrates.
"""

from __future__ import annotations

import logging
import os
import random
import functools

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


# ─── Decorator: upsert DB record on every message ────────────────────────────

def register_user(handler):
    """
    Middleware-style decorator that upserts the user into the DB
    and increments their message count before calling the real handler.

    FIX: @functools.wraps preserves __name__ so aiogram can distinguish
         each decorated handler — without it, all handlers share the same
         name and aiogram silently overwrites earlier registrations.
    """
    @functools.wraps(handler)
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
    """
    Logic trace for '𖠌' button:
      1. Sets FSM state → AIChat.waiting_for_input
      2. Next message from this user hits handle_ai_message()
      3. handle_ai_message() lazy-loads DB history → calls ask_ai()
      4. ask_ai() reads AI_PROVIDER env → dispatches to active provider fn
      5. Provider fn reads its API key env var → calls provider API
      6. Reply saved to DB, sent to user with inline controls
    """
    await state.set_state(AIChat.waiting_for_input)
    await message.answer(
        "𖠌 — أنا هنا.\nاكتب ما يجول في خاطرك...",
        reply_markup=ai_chat_keyboard(),
    )


@router.message(F.text == "◈ المطور")
@register_user
async def btn_developer(message: Message) -> None:
    card = (
        "◈ <b>المطور</b>\n\n"
        "مُهندس الظلام، نسّاج الكود، صانع الرمز.\n"
        "تواصل عبر المنصات أدناه 👇"
    )
    await message.answer(card, reply_markup=developer_profile_keyboard())


@router.message(F.text == "◈ قناة الدعم ⚙️")
@register_user
async def btn_support(message: Message) -> None:
    link = os.getenv("SUPPORT_CHANNEL", "")
    text = f"⚙️ قناة الدعم:\n{link}" if link else "⚙️ لم يتم تعيين رابط قناة الدعم بعد."
    await message.answer(text)


@router.message(F.text == "◈ ٱلتحديثات 24/7 📢")
@register_user
async def btn_updates(message: Message) -> None:
    link = os.getenv("UPDATES_CHANNEL", "")
    text = f"📢 قناة التحديثات:\n{link}" if link else "📢 لم يتم تعيين رابط قناة التحديثات بعد."
    await message.answer(text)


@router.message(F.text == "◈ الهدية اليومية 🎁")
@register_user
async def btn_gift(message: Message) -> None:
    link = os.getenv("GIFT_CHANNEL", "")
    text = f"🎁 الهدية اليومية:\n{link}" if link else "🎁 لم يتم تعيين رابط قناة الهدايا بعد."
    await message.answer(text)


@router.message(F.text == "◈ إستراحة")
@register_user
async def btn_chill(message: Message) -> None:
    msgs = [
        "خذ نفساً عميقاً.. الكون لا يستعجل.",
        "الصمت أحياناً هو أعمق إجابة.",
        "لا شيء يستحق أن يُربك سكينتك الداخلية.",
        "توقّف.. وانظر كم أنت بعيد عن حيث كنت.",
    ]
    await message.answer(f"☁️ {random.choice(msgs)}")


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
    text = (
        f"⧓ <b>نبض النظام</b>\n\n"
        f"🖥 CPU: <code>{pulse['cpu_pct']}%</code>\n"
        f"💾 RAM: <code>{pulse['ram_used']} / {pulse['ram_total']} MB</code> ({pulse['ram_pct']}%)\n"
        f"💿 Disk: <code>{pulse['disk_used']} / {pulse['disk_total']} GB</code>\n"
        f"⏱ Uptime: <code>{pulse['uptime']}</code>\n\n"
        f"النظام يعمل بشكل طبيعي ✓"
    )
    await waiting.delete()
    await message.answer(text, reply_markup=system_pulse_keyboard())


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
    text = (
        f"📡 <b>المراقبة — حالة النظام</b>\n\n"
        f"CPU  [{bars(pulse['cpu_pct'])}] {pulse['cpu_pct']}%\n"
        f"RAM  [{bars(pulse['ram_pct'])}] {pulse['ram_pct']}%\n\n"
        f"🕐 وقت التشغيل: <code>{pulse['uptime']}</code>\n"
        f"الحالة: 🟢 يعمل"
    )
    await message.answer(text)


# ─── AI Chat — catch-all for FSM state ───────────────────────────────────────

@router.message(AIChat.waiting_for_input)
async def handle_ai_message(message: Message, state: FSMContext) -> None:
    """
    Live logic trace — '𖠌' button full round-trip:

    USER PRESSES '𖠌'
      └─ btn_ai_chat() → state = AIChat.waiting_for_input

    USER TYPES "من أنت؟"
      └─ handle_ai_message() triggered (FSM filter matches)
          ├─ get_session_factory() → existing asyncpg pool connection
          ├─ ConversationDAO.get_history(user_id)
          │    └─ SELECT last 20 rows WHERE user_id=X ORDER BY created_at DESC
          │       (lazy — only this user's rows, never all users)
          ├─ ask_ai(history, "من أنت؟")
          │    ├─ reads _PROVIDER = os.getenv("AI_PROVIDER")  e.g. "groq"
          │    ├─ _DISPATCH["groq"] → _call_groq()
          │    │    ├─ AsyncGroq(api_key=os.environ["GROQ_API_KEY"])
          │    │    ├─ messages = [system_prompt] + history + [user_turn]
          │    │    └─ groq.chat.completions.create(model=...) → reply str
          │    └─ returns reply
          ├─ ConversationDAO.add_message(user_id, "user", user_text)
          ├─ ConversationDAO.add_message(user_id, "assistant", reply)
          └─ message.answer(reply, reply_markup=ai_chat_keyboard())
               └─ inline buttons: [🗑 مسح] [🔄 إعادة]
                    callback_data="ai:clear" | "ai:retry"
                    → centralised_callback_handler() in callbacks.py
    """
    user_id   = message.from_user.id
    user_text = message.text or ""

    if not user_text.strip():
        await message.answer("أرسل نصاً لأتمكن من الرد.")
        return

    thinking = await message.answer("𖠌 ...")

    session_factory = get_session_factory()
    async with session_factory() as session:
        conv_dao = ConversationDAO(session)

        # Lazy-load — only this user's last MAX_HISTORY messages
        history = await conv_dao.get_history(user_id)

        # Dispatch to active AI provider
        reply = await ask_ai(history, user_text)

        # Persist both turns to DB
        await conv_dao.add_message(user_id, "user",      user_text)
        await conv_dao.add_message(user_id, "assistant", reply)

    await thinking.delete()
    await message.answer(reply, reply_markup=ai_chat_keyboard())
