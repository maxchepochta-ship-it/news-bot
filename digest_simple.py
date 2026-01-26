from collections import defaultdict

def _short(text: str, n: int = 220) -> str:
    text = (text or "").strip()
    text = " ".join(text.split())
    if len(text) > n:
        return text[:n].rstrip() + "…"
    return text

def make_digest_simple(theme: str, start: str, end: str, items: list[dict]) -> str:
    by_channel = defaultdict(list)

    for it in items:
        by_channel[it.get("channel", "unknown")].append(it)

    lines = []
    lines.append(f"📰 ДАЙДЖЕСТ: {theme.upper()}")
    lines.append(f"Период: {start} — {end}")
    lines.append("")

    total_posts = 0

    for channel, posts in sorted(by_channel.items(), key=lambda x: len(x[1]), reverse=True):
        posts = sorted(posts, key=lambda x: x.get("published_at", ""), reverse=True)

        lines.append(f"🔹 {channel} ({len(posts)})")
        for p in posts[:50]:
            txt = _short(p.get("text", ""))
            url = p.get("url") or ""
            ts = p.get("published_at") or ""

            if ts:
                ts = ts.replace("T", " ").replace("+00:00", " UTC")
                ts = ts[:16] + " UTC"
                lines.append(f"• {ts} — {txt}")
            else:
                lines.append(f"• {txt}")

            if url:
                lines.append(f"  → {url}")

            total_posts += 1

        lines.append("")

    lines.append("━━━━━━━━━━━━━━━━━━━━━━")
    lines.append(f"📊 Всего постов в дайджесте: {total_posts}")

    return "\n".join(lines)
