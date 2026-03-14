#!/usr/bin/env python3
"""
Fetch new AI tool releases from RSS feeds.
Outputs plain text to stdout for piping to claude -p.
Deduplicates via seen_items.json in this directory.
"""

import feedparser
import json
import os
import sys
import re
from datetime import datetime, timezone, timedelta
from html import unescape

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SEEN_FILE = os.path.join(SCRIPT_DIR, "seen_items.json")
LOOKBACK_DAYS = 7

FEEDS = [
    ("Claude Code",   "https://github.com/anthropics/claude-code/releases.atom"),
    ("Codex CLI",     "https://github.com/openai/codex/releases.atom"),
    ("Gemini CLI",    "https://github.com/google-gemini/gemini-cli/releases.atom"),
    ("Aider",         "https://github.com/Aider-AI/aider/releases.atom"),
    ("Anthropic SDK", "https://github.com/anthropics/anthropic-sdk-python/releases.atom"),
    ("OpenAI SDK",    "https://github.com/openai/openai-python/releases.atom"),
]


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


def main():
    seen = load_seen()
    new_items = []
    cutoff = datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)

    for source, url in FEEDS:
        try:
            feed = feedparser.parse(url, agent="ai-digest/1.0")
        except Exception:
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

            new_items.append({
                "source": source,
                "title": entry.get("title", "").strip(),
                "link": entry.get("link", ""),
                "summary": strip_html(entry.get("summary", ""))[:500],
                "id": item_id,
            })

    if not new_items:
        sys.exit(0)  # empty output signals "nothing new" to the caller

    for item in new_items:
        seen.add(item["id"])
    save_seen(seen)

    for item in new_items:
        print(f"[{item['source']}] {item['title']}")
        print(item["link"])
        if item["summary"]:
            print(item["summary"])
        print()


if __name__ == "__main__":
    main()
