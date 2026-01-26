import os
import hashlib
from datetime import datetime, timedelta, timezone

from telethon import TelegramClient
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
    api_id = int(os.environ["TG_API_ID"])
    api_hash = os.environ["TG_API_HASH"]

    # Telethon создаст файл tg_session.session (мы его игнорим через .gitignore)
    client = TelegramClient("tg_session", api_id, api_hash)

    sources = get_active_sources(theme)
    if not sources:
        print(f"No sources for theme={theme}")
        return 0

    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    saved = 0

    async with client:
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
