import os
import hashlib
from datetime import datetime, timedelta, timezone

from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.types import Message

from db import get_active_sources, upsert_post


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()


def build_post_url(channel: str, message_id: int) -> str:
    return f"https://t.me/{channel}/{message_id}"


def normalize_text(msg: Message) -> str:
    t = msg.message or ""
    return " ".join(t.split())


async def collect_recent(theme: str, hours: int = 12, limit_per_channel: int = 60) -> int:
    """
    Собирает свежие посты из Telegram-каналов (public) через Telethon и сохраняет в Supabase.
    На Railway работает без интерактивного ввода благодаря StringSession в переменной окружения TG_SESSION.
    """
    api_id_raw = os.environ.get("TG_API_ID")
    api_hash = os.environ.get("TG_API_HASH")
    tg_session = os.environ.get("TG_SESSION")

    if not api_id_raw or not api_hash:
        raise RuntimeError("TG_API_ID / TG_API_HASH is not set")

    if not tg_session:
        raise RuntimeError("TG_SESSION is not set")

    try:
        api_id = int(api_id_raw)
    except ValueError:
        raise RuntimeError("TG_API_ID must be an integer")

    client = TelegramClient(StringSession(tg_session), api_id, api_hash)

    sources = get_active_sources(theme)
    if not sources:
        print(f"No sources for theme={theme}")
        return 0

    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    saved = 0

    # ВАЖНО: всё делаем внутри async with client, чтобы соединение было установлено
    async with client:
        me = await client.get_me()
        if not me:
            raise RuntimeError(
                "Telethon session invalid: get_me() returned None. Re-generate TG_SESSION."
            )

        for channel in sources:
            try:
                entity = await client.get_entity(channel)

                async for msg in client.iter_messages(entity, limit=limit_per_channel):
                    if not msg.date or msg.date < since:
                        break

                    text = normalize_text(msg)
                    url = build_post_url(channel, msg.id)

                    # hash для дедупликации (уникальность в БД)
                    h = sha(f"{channel}|{msg.id}|{text}|{url}")

                    row = {
                        "theme": theme,
                        "channel": channel,
                        "message_id": msg.id,
                        "published_at": msg.date.isoformat(),
                        "text": text,
                        "url": url,
                        "hash": h,
                    }

                    try:
                        upsert_post(row)
                        saved += 1
                    except Exception:
                        # чаще всего — дубль по unique(hash) / unique(channel,message_id)
                        pass

            except Exception as e:
                print(f"Channel {channel} failed: {e}")

    return saved


if __name__ == "__main__":
    import asyncio

    theme = os.getenv("THEME", "technology")
    n = asyncio.run(collect_recent(theme=theme, hours=12))
    print("saved:", n)
