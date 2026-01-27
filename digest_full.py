from typing import List, Dict
from llm import process_posts_with_llm

def make_digest_full(theme: str, start_iso: str, end_iso: str, posts: List[Dict]) -> str:
    data = process_posts_with_llm(posts)

    lines = []
    lines.append(f"⚡ ГЛАВНОЕ ЗА {start_iso[:16]} — {end_iso[:16]}\n")
    lines.append(data.get("summary", ""))
    lines.append("\n" + "━" * 30 + "\n")

    stories = sorted(
        data.get("stories", []),
        key=lambda s: s.get("importance", 0),
        reverse=True,
    )

    for story in stories:
        importance = story.get("importance", 1)
        emoji = "🔥" if importance >= 5 else "⭐" if importance >= 4 else "•"

        lines.append(f"{emoji} {story.get('title')}")
        lines.append(story.get("summary", ""))

        for item in story.get("items", []):
            lines.append(
                f"  • {item.get('channel')} — {item.get('unique_detail')}\n    {item.get('url')}"
            )

        lines.append("\n")

    lines.append("⚠️ Дайджест сформирован ИИ. Проверяй первоисточники.")
    return "\n".join(lines)
