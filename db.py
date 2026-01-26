import os
from supabase import create_client, Client

def get_supabase() -> Client:
    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_KEY"]
    return create_client(url, key)

def get_active_sources(theme: str) -> list[str]:
    sb = get_supabase()
    res = (
        sb.table("sources")
        .select("channel")
        .eq("theme", theme)
        .eq("is_active", True)
        .execute()
    )
    return [row["channel"] for row in (res.data or [])]

def upsert_post(row: dict) -> None:
    """
    row fields:
      theme, channel, message_id, published_at, text, url, hash
    """
    sb = get_supabase()
    sb.table("posts").insert(row).execute()

def fetch_posts_for_period(theme: str, start_iso: str, end_iso: str) -> list[dict]:
    sb = get_supabase()
    res = (
        sb.table("posts")
        .select("channel,message_id,published_at,text,url")
        .eq("theme", theme)
        .gte("published_at", start_iso)
        .lt("published_at", end_iso)
        .order("published_at", desc=True)
        .execute()
    )
    return res.data or []

def upsert_chat(chat_id: int, chat_type: str, title, theme: str):
    sb = get_supabase()
    row = {
        "chat_id": chat_id,
        "chat_type": chat_type,
        "title": title,
        "theme": theme,
        "is_active": True,
    }
    # upsert по primary key chat_id
    return sb.table("chats").upsert(row).execute()

def get_active_chats(theme: str) -> list[dict]:
    sb = get_supabase()
    res = (
        sb.table("chats")
        .select("chat_id,chat_type,title")
        .eq("theme", theme)
        .eq("is_active", True)
        .execute()
    )
    return res.data or []
