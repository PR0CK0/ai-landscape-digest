#!/usr/bin/env python3
"""
AI Tools Digest — fetches release feeds, deduplicates, summarizes with Claude Haiku.
"""

import feedparser
import anthropic
import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from html import unescape
import re

FEEDS = [
    ("Claude Code",   "https://github.com/anthropics/claude-code/releases.atom"),
    ("Codex CLI",     "https://github.com/openai/codex/releases.atom"),
    ("Gemini CLI",    "https://github.com/google-gemini/gemini-cli/releases.atom"),
    ("Aider",         "https://github.com/Aider-AI/aider/releases.atom"),
    ("Anthropic API", "https://github.com/anthropics/anthropic-sdk-python/releases.atom"),
    ("OpenAI SDK",    "https://github.com/openai/openai-python/releases.atom"),
]

SEEN_FILE = "seen_items.json"
DOCS_DIR = Path("docs")
OUTPUT_TXT = DOCS_DIR / "latest.txt"
OUTPUT_HTML = DOCS_DIR / "index.html"
LOOKBACK_DAYS = 7


def strip_html(text):
    return re.sub(r"<[^>]+>", "", unescape(text or "")).strip()


def load_seen():
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE) as f:
            return set(json.load(f))
    return set()


def save_seen(seen):
    with open(SEEN_FILE, "w") as f:
        json.dump(sorted(seen)[-2000:], f)


def fetch_new_items(seen):
    new_items = []
    cutoff = datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)

    for source, url in FEEDS:
        try:
            feed = feedparser.parse(url, agent="ai-digest/1.0")
        except Exception as e:
            print(f"  [warn] failed to fetch {source}: {e}")
            continue

        for entry in feed.entries:
            item_id = entry.get("id") or entry.get("link") or ""
            if not item_id or item_id in seen:
                continue

            published = entry.get("published_parsed")
            if published:
                pub_dt = datetime(*published[:6], tzinfo=timezone.utc)
                if pub_dt < cutoff:
                    continue

            summary = strip_html(entry.get("summary", ""))[:600]

            new_items.append({
                "source": source,
                "title": entry.get("title", "").strip(),
                "link": entry.get("link", ""),
                "summary": summary,
                "id": item_id,
            })
            print(f"  [new] {source}: {entry.get('title', '').strip()}")

    return new_items


def summarize(items, timestamp):
    if not items:
        return "No new updates since last check."

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    items_text = "\n\n".join(
        f"[{i['source']}] {i['title']}\n{i['link']}\n{i['summary']}"
        for i in items
    )

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=800,
        messages=[{
            "role": "user",
            "content": f"""You are an AI tools tracker for a developer who builds scaffolding around Claude Code, Codex CLI, Gemini CLI, and Aider.

Summarize these new releases into a terse terminal digest. Rules:
- Plain text only, no markdown, no asterisks
- Bullet points with dash (-)
- Group by tool
- One line per item max — version number + what changed
- Flag anything that could break existing integrations or tooling (label: BREAKING)
- Skip patch releases that are purely internal/trivial
- Max 25 lines total

NEW ITEMS ({timestamp}):
{items_text}"""
        }]
    )

    return response.content[0].text.strip()


def write_html(digest, timestamp):
    escaped = digest.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    OUTPUT_HTML.write_text(f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>AI Tools Digest</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ background: #0d1117; color: #e6edf3; font-family: 'SF Mono', 'Fira Code', monospace; padding: 40px 24px; }}
    .container {{ max-width: 680px; margin: 0 auto; }}
    .header {{ color: #58a6ff; font-size: 0.8rem; margin-bottom: 8px; letter-spacing: 0.05em; text-transform: uppercase; }}
    .timestamp {{ color: #484f58; font-size: 0.75rem; margin-bottom: 24px; }}
    pre {{ white-space: pre-wrap; line-height: 1.75; font-size: 0.85rem; color: #c9d1d9; }}
    .curl {{ margin-top: 32px; padding: 12px 16px; background: #161b22; border: 1px solid #30363d; border-radius: 6px; font-size: 0.75rem; color: #484f58; }}
    .curl code {{ color: #58a6ff; }}
  </style>
</head>
<body>
  <div class="container">
    <div class="header">AI Tools Digest</div>
    <div class="timestamp">{timestamp}</div>
    <pre>{escaped}</pre>
    <div class="curl">terminal: <code>curl -s https://PR0CK0.github.io/ai-digest/latest.txt</code></div>
  </div>
</body>
</html>""")


def main():
    print("Fetching feeds...")
    seen = load_seen()
    new_items = fetch_new_items(seen)
    print(f"Found {len(new_items)} new items")

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    digest = summarize(new_items, timestamp)

    for item in new_items:
        seen.add(item["id"])
    save_seen(seen)

    DOCS_DIR.mkdir(exist_ok=True)

    OUTPUT_TXT.write_text(
        f"AI Tools Digest — {timestamp}\n"
        + "=" * 50 + "\n"
        + digest + "\n"
    )

    write_html(digest, timestamp)
    print(f"Done. Output written to {OUTPUT_TXT} and {OUTPUT_HTML}")


if __name__ == "__main__":
    main()
