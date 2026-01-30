import os
import re
from datetime import datetime, timedelta, timezone

import dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from collector import collect_recent
from db import fetch_posts_for_period, upsert_chat

# LLM / digest
from digest_simple import make_digest_simple
from digest_full import make_digest_full

# optional filters (если таблица chats уже расширена)
try:
    from db import get_chat_settings
except ImportError:
    get_chat_settings = None


# =====================
# ENV
# =====================

dotenv.load_dotenv(".env")


# =====================
# HELPERS
# =====================

def iso(dt: datetime) -> str:
    return dt.isoformat()


def make_digest(theme, start, end, items):
    mode = os.getenv("LLM_MODE", "simple")
    if mode == "full":
        return make_digest_full(theme, start, end, items)
    return make_digest_simple(theme, start, end, items)


def parse_keywords(s: str):
    if not s:
        return []
    parts = re.split(r"[,\n;]+", s)
    return [p.strip().lower() for p in parts if p.strip()]


def apply_filters(items, include, exclude):
    out = []
    for it in items:
        text = (it.get("text") or "").lower()

        if exclude and any(w in text for w in exclude):
            continue
        if include and not any(w in text for w in include):
            continue

        out.append(it)
    return out


# =====================
# HANDLERS
# =====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    theme = os.getenv("THEME", "technology")

    try:
        upsert_chat(
            chat_id=chat.id,
            chat_type=chat.type,
            title=getattr(chat, "title", None),
            theme=theme,
        )
    except Exception as e:
        await update.message.reply_text(
            f"⚠️ Не удалось зарегистрировать чат: {e}"
        )
        return

    await update.message.reply_text(
        "👋 Привет! Я новостной бот.\n\n"
        "Команды:\n"
        "/digest — собрать дайджест\n"
        "/help — справка\n"
        "/ping — проверка, что бот жив\n\n"
        f"Тема: {theme}\n"
        f"Режим: {os.getenv('LLM_MODE', 'simple')}"
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Команды:\n"
        "/start — регистрация чата\n"
        "/digest — дайджест\n"
        "/help — справка\n"
        "/ping — проверка\n"
    )


async def ping_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ pong (бот жив)")


async def digest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    theme = os.getenv("THEME", "technology")
    now = datetime.now(timezone.utc)
    hours = int(os.getenv("DIGEST_HOURS", "12"))
    start_dt = now - timedelta(hours=hours)

    await update.message.reply_text(
        "⏳ Собираю новости и готовлю дайджест...\n"
        f"🤖 Режим: {os.getenv('LLM_MODE', 'simple')}\n"
        f"🧭 Тема: {theme}\n"
        f"🕒 Окно: {hours}ч (UTC)"
    )

    # 1) Collect
    try:
        await collect_recent(theme=theme, hours=max(hours, 12))
    except Exception as e:
        await update.message.reply_text(f"⚠️ Ошибка сбора постов: {e}")
        return

    # 2) Fetch
    items = fetch_posts_for_period(theme, iso(start_dt), iso(now))

    # 3) Filters (optional)
    if get_chat_settings:
        try:
            st = get_chat_settings(update.effective_chat.id)
            include = parse_keywords(st.get("include_keywords", ""))
            exclude = parse_keywords(st.get("exclude_keywords", ""))
            items = apply_filters(items, include, exclude)
        except Exception:
            pass

    await update.message.reply_text(
        f"🔎 Из БД: {len(items)} постов\n"
        f"start={iso(start_dt)}\n"
        f"end={iso(now)}"
    )

    if not items:
        await update.message.reply_text("Постов за период не найдено.")
        return

    # 4) Digest
    try:
        if os.getenv("LLM_MODE") == "full":
            await update.message.reply_text("🧠 Генерирую дайджест через LLM...")
        content = make_digest(theme, iso(start_dt), iso(now), items)
    except Exception as e:
        await update.message.reply_text(f"⚠️ Ошибка генерации дайджеста: {e}")
        return

    if len(content) > 3500:
        content = content[:3500] + "\n\n…(обрезано из-за лимита Telegram)"

    await update.message.reply_text(content)


# =====================
# MAIN
# =====================

def main():
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise RuntimeError("BOT_TOKEN is missing in Railway Variables")

    print("✅ Bot started, entering polling loop…", flush=True)

    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("ping", ping_cmd))
    app.add_handler(CommandHandler("digest", digest))

    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
