import os
from openai import OpenAI

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

SYSTEM = (
    "Ты — новостной редактор и агрегатор для редакции медиа. "
    "Ты НЕ выдумываешь факты, работаешь строго по входным данным. "
    "Если информации недостаточно — так и скажи."
)

def build_prompt(theme: str, start: str, end: str, items: list[dict]) -> str:
    items = items[:60]  # ограничим объём для MVP

    lines = []
    for it in items:
        published = it.get("published_at", "")
        channel = it.get("channel", "")
        text = (it.get("text") or "").strip()
        url = it.get("url") or ""
        if not text and url:
            text = "(пост без текста, только ссылка)"
        lines.append(f"- [{channel}] {published}\n  {text}\n  {url}")

    joined = "\n".join(lines)

    return f"""
ТЕМА: {theme}
ПЕРИОД: {start} — {end}

Вот список новостей/постов:
{joined}

ЗАДАЧА:
1) Сгруппируй по сюжетам (одно событие = один сюжет)
2) Для каждого сюжета:
   - заголовок
   - 2–4 предложения описания (без выдумок)
   - список источников со ссылками
   - уникальные детали: что добавил каждый источник (если есть)
3) Выдели один главный сюжет (если он очевиден), иначе пропусти этот блок
4) В конце: статистика (сколько постов было → сколько сюжетов получилось)

ФОРМАТ:
Верни аккуратный Markdown, пригодный для отправки в Telegram.
"""

def make_digest(theme: str, start: str, end: str, items: list[dict]) -> str:
    resp = client.chat.completions.create(
        model="gpt-4.1-mini",
        temperature=0.2,
        messages=[
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": build_prompt(theme, start, end, items)},
        ],
    )
    return resp.choices[0].message.content.strip()
