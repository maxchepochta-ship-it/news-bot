import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import dotenv
from supabase import create_client
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from collector import collect_recent
from db import fetch_posts_for_period, upsert_chat
from digest_simple import make_digest_simple
from digest_full import make_digest_full


# --- локальная загрузка .env (на Railway .env нет, там только Variables) ---
if Path(".env").exists():
    dotenv.load_dotenv(".env")


def iso(dt: datetime) -> str:
    return dt.isoformat()


def make_digest(theme: str, start: str, end: str, items):
    # Явный переключатель режимов
    if os.getenv("LLM_MODE", "simple").lower() == "full":
        return make_digest_full(theme, start, end, items)
    return make_digest_simple(theme, start, end, items)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /start:
    1) Регистрирует текущий чат (личка/группа) в таблице chats
    2) Делает read-back (диагностика), чтобы убедиться, что запись реально в БД
    """
    theme = os.getenv("THEME", "technology")
    chat = update.effective_chat

    try:
        upsert_chat(chat.id, chat.type, getattr(chat, "title", None), theme)

        sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])
        res = (
            sb.table("chats")
            .select("chat_id,chat_type,title,theme,is_active")
            .eq("chat_id", chat.id)
            .execute()
        )

        await update.message.reply_text(
            "✅ Чат зарегистрирован.\n"
            f"id={chat.id}\n"
            f"type={chat.type}\n"
            f"title={getattr(chat, 'title', None)}\n"
            f"theme={theme}\n"
            f"read_back_rows={len(res.data or [])}\n"
            f"row={res.data[0] if (res.data or []) else None}"
        )

    except Exception as e:
        await update.message.reply_text(
            f"⚠️ Ошибка регистрации чата в БД: {type(e).__name__}: {e}"
        )
        await update.message.reply_text(
            "Команды:\n"
            "/digest — собрать дайджест\n"
            "/help — справка\n\n"
            "⚠️ Регистрация чата не удалась — см. ошибку выше."
        )
        return

    await update.message.reply_text(
        "👋 Привет! Я MVP-бот для мониторинга новостей.\n\n"
        "Команды:\n"
        "/digest — собрать дайджест\n"
        "/help — справка\n"
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Команды:\n"
        "/start — зарегистрировать чат (и показать диагностику)\n"
        "/digest — дайджест\n"
        "/help — справка\n\n"
        "Источники берутся из Supabase таблицы sources.\n"
        "Чаты для рассылок сохраняются в Supabase таблицу chats."
    )


async def digest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    theme = os.getenv("THEME", "technology")
    mode = os.getenv("LLM_MODE", "simple").lower()

    now = datetime.now(timezone.utc)
    period_hours = int(os.getenv("DIGEST_HOURS", "12"))
    start_dt = now - timedelta(hours=period_hours)

    await update.message.reply_text(
        "⏳ Собираю новости и готовлю дайджест...\n"
        f"🤖 Режим: {mode}\n"
        f"🧭 Тема: {theme}\n"
        f"🕒 Окно: {period_hours}ч (UTC)"
    )

    # 1) Подтянуть свежие посты
    try:
        await collect_recent(theme=theme, hours=max(period_hours, 12))
    except Exception as e:
        await update.message.reply_text(
            f"⚠️ Ошибка сбора постов: {type(e).__name__}: {e}"
        )
        return

    # 2) Берем посты за окно
    items = fetch_posts_for_period(theme, iso(start_dt), iso(now))

    await update.message.reply_text(
        f"🔎 Из БД: {len(items)} постов\n"
        f"start={iso(start_dt)}\n"
        f"end={iso(now)}"
    )

    if not items:
        await update.message.reply_text(
            "Постов за период не нашёл.\n"
            "Проверь:\n"
            "1) sources для этой темы\n"
            "2) что collector пишет в posts\n"
            "3) увеличь DIGEST_HOURS"
        )
        return

    # 3) Генерация дайджеста (simple или full)
    try:
        await update.message.reply_text(
            "🧠 Генерирую дайджест через LLM..." if mode == "full" else "📝 Генерирую простой дайджест..."
        )
        content = make_digest(theme, iso(start_dt), iso(now), items)
    except Exception as e:
        await update.message.reply_text(
            f"⚠️ Ошибка генерации дайджеста: {type(e).__name__}: {e}"
        )
        return

    # 4) Telegram лимит
    if len(content) > 3500:
        content = content[:3500] + "\n\n…(обрезано из-за лимита Telegram)"

    await update.message.reply_text(content)


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Глобальный хендлер ошибок, чтобы не было "No error handlers..."
    try:
        msg = f"⚠️ Unhandled error: {context.error}"
        if isinstance(update, Update) and update.effective_message:
            await update.effective_message.reply_text(msg)
    except Exception:
        pass


def main():
    token = os.getenv("BOT_TOKEN")
    if not token:
        # Не падаем в crash loop. Просто лог и выход.
        print("BOT_TOKEN is missing. Set it in Railway Variables (Production) or in local .env.")
        return

    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("digest", digest))

    app.add_error_handler(on_error)

    app.run_polling()


if __name__ == "__main__":
    main()
