#!/usr/bin/env python3
"""
ai-digest — fetch AI tool release feeds, summarize with a local LLM CLI,
output to terminal and/or GitHub Pages.

Config: copy config.example.yaml → config.yaml and edit.
Docs:   README.md
"""

import feedparser
import itertools
import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta
from html import unescape
from pathlib import Path

try:
    import yaml
except ImportError:
    print("Missing dependency: pip install pyyaml", file=sys.stderr)
    sys.exit(1)

SCRIPT_DIR    = Path(__file__).parent
SEEN_FILE     = SCRIPT_DIR / "seen_items.json"
CONFIG_FILE   = SCRIPT_DIR / "config.yaml"
DOCS_DIR      = SCRIPT_DIR / "docs"
LOOKBACK_DAYS = 7
FEED_TIMEOUT  = 10   # seconds per feed HTTP request
DIVIDER       = "━" * 52

# ── Default feeds ─────────────────────────────────────────────────────────────
# Always included unless the user sets include_defaults: false in config.yaml.

DEFAULT_FEEDS = [
    # CLI tools — highest signal for breaking changes to tooling
    ("Claude Code",     "https://github.com/anthropics/claude-code/releases.atom"),
    ("Codex CLI",       "https://github.com/openai/codex/releases.atom"),
    ("Gemini CLI",      "https://github.com/google-gemini/gemini-cli/releases.atom"),
    ("Aider",           "https://github.com/Aider-AI/aider/releases.atom"),
    ("Ollama",          "https://github.com/ollama/ollama/releases.atom"),

    # SDKs — API surface changes affect tooling
    ("Anthropic SDK",   "https://github.com/anthropics/anthropic-sdk-python/releases.atom"),
    ("OpenAI SDK",      "https://github.com/openai/openai-python/releases.atom"),

    # Model & product announcements
    ("Hugging Face",    "https://huggingface.co/blog/feed.xml"),

    # Curated AI dev news (weekly, low-noise)
    ("Last Week in AI", "https://lastweekin.ai/feed"),
    ("Latent Space",    "https://www.latent.space/feed"),
]

DEFAULT_PROMPT = (
    "Terse AI tools digest for a developer building tooling around Claude Code, "
    "Codex CLI, Gemini CLI, and Aider. Rules: plain text only, no markdown, "
    "grouped by tool/source, one line per item (version + key change), max 20 "
    "lines total. Prefix BREAKING: if anything could break existing integrations."
)

# ── LLM backends ──────────────────────────────────────────────────────────────
# Each entry: (cli_name, build_cmd_fn)
# build_cmd_fn(prompt, model) → list[str] command to run

def _cmd_claude(prompt: str, model: str) -> list:
    cmd = ["claude", "-p", prompt]
    if model and model != "default":
        cmd = ["claude", "--model", model, "-p", prompt]
    return cmd

def _cmd_gemini(prompt: str, model: str) -> list:
    cmd = ["gemini", "-p", prompt]
    if model and model != "default":
        cmd = ["gemini", "--model", model, "-p", prompt]
    return cmd

def _cmd_codex(prompt: str, model: str) -> list:
    # Codex non-interactive mode: `codex exec "prompt"`
    cmd = ["codex", "exec", prompt]
    if model and model != "default":
        cmd = ["codex", "exec", "--model", model, prompt]
    return cmd

def _cmd_ollama(prompt: str, model: str) -> list:
    m = model if model and model != "default" else "llama3"
    return ["ollama", "run", m, prompt]

BACKENDS = {
    "claude":  _cmd_claude,
    "gemini":  _cmd_gemini,
    "codex":   _cmd_codex,
    "ollama":  _cmd_ollama,
}

DEFAULT_BACKEND = "claude"
DEFAULT_MODEL   = "default"   # uses each CLI's own default


# ── Spinner ───────────────────────────────────────────────────────────────────

class Spinner:
    FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

    def __init__(self):
        self._msg    = ""
        self._stop   = threading.Event()
        self._lock   = threading.Lock()
        self._thread = None

    def _run(self):
        for frame in itertools.cycle(self.FRAMES):
            if self._stop.is_set():
                break
            with self._lock:
                msg = self._msg
            sys.stderr.write(f"\r  {frame} {msg}  ")
            sys.stderr.flush()
            time.sleep(0.08)
        sys.stderr.write("\r\033[K")  # clear the line on exit
        sys.stderr.flush()

    def update(self, msg: str):
        with self._lock:
            self._msg = msg

    def __enter__(self):
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *_):
        self._stop.set()
        if self._thread:
            self._thread.join()


# ── Helpers ───────────────────────────────────────────────────────────────────

def load_config() -> dict:
    if not CONFIG_FILE.exists():
        return {}
    with open(CONFIG_FILE) as f:
        return yaml.safe_load(f) or {}


def load_seen() -> set:
    if SEEN_FILE.exists():
        with open(SEEN_FILE) as f:
            return set(json.load(f))
    return set()


def save_seen(seen: set):
    with open(SEEN_FILE, "w") as f:
        json.dump(sorted(seen)[-2000:], f)


def strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", unescape(text or "")).strip()


def check_url(url: str, timeout: int = FEED_TIMEOUT) -> bool:
    """Return True if the URL is reachable."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "ai-digest/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status < 400
    except Exception:
        return False


# ── Core logic ────────────────────────────────────────────────────────────────

def _fetch_one(source: str, url: str, seen: set, cutoff: datetime, verbose: bool) -> list:
    """Fetch a single feed. Returns list of new items (may be empty)."""
    try:
        feed = feedparser.parse(
            url,
            agent="ai-digest/1.0",
            request_headers={"Accept": "application/atom+xml, application/rss+xml, */*"},
        )
        if feed.bozo and not feed.entries:
            raise ValueError(f"feed parse error: {feed.bozo_exception}")
    except Exception as e:
        print(f"  [warn] {source}: unreachable or unparseable — {e}", file=sys.stderr)
        return []

    if not feed.entries:
        if verbose:
            print(f"  [info] {source}: no entries", file=sys.stderr)
        return []

    items = []
    for entry in feed.entries:
        item_id = entry.get("id") or entry.get("link") or ""
        if not item_id or item_id in seen:
            continue
        published = entry.get("published_parsed")
        if published:
            pub_dt = datetime(*published[:6], tzinfo=timezone.utc)
            if pub_dt < cutoff:
                continue
        items.append({
            "source":  source,
            "title":   entry.get("title", "").strip(),
            "link":    entry.get("link", ""),
            "summary": strip_html(entry.get("summary", ""))[:500],
            "id":      item_id,
        })
    return items


def fetch_new_items(feeds: list, seen: set, verbose: bool = False) -> list:
    cutoff    = datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)
    new_items = []
    total     = len(feeds)
    print_lock = threading.Lock()
    pad        = max(len(s) for s, _ in feeds)

    with ThreadPoolExecutor(max_workers=total) as pool:
        futures = {
            pool.submit(_fetch_one, source, url, seen, cutoff, verbose): source
            for source, url in feeds
        }
        for future in as_completed(futures):
            source = futures[future]
            items  = future.result()
            new_items.extend(items)
            n = len(items)
            with print_lock:
                if n > 0:
                    sys.stderr.write(f"  ✓ {source:<{pad}}  {n} new\n")
                else:
                    sys.stderr.write(f"  · {source:<{pad}}  —\n")
                sys.stderr.flush()

    sys.stderr.write("\n")
    return new_items


def summarize(items: list, prompt: str, backend: str = DEFAULT_BACKEND, model: str = DEFAULT_MODEL) -> str:
    raw = "\n\n".join(
        f"[{i['source']}] {i['title']}\n{i['link']}\n{i['summary']}"
        for i in items
    )
    full_prompt = f"{prompt}\n\nNEW RELEASES:\n\n{raw}"

    build_cmd = BACKENDS.get(backend)
    if not build_cmd:
        print(f"  [warn] unknown backend '{backend}', falling back to claude", file=sys.stderr)
        build_cmd = BACKENDS["claude"]

    cmd = build_cmd(full_prompt, model)

    label = f"{backend}" + (f"/{model}" if model != "default" else "")
    try:
        with Spinner() as spin:
            spin.update(f"summarizing {len(items)} items with {label}...")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except FileNotFoundError:
        return f"[error] '{cmd[0]}' not found — is it installed and on PATH?]"
    except subprocess.TimeoutExpired:
        return "[error] LLM timed out after 120s]"

    if result.returncode != 0:
        err = result.stderr.strip()[:200]
        return f"[error] {cmd[0]} exited {result.returncode}: {err}]"

    return result.stdout.strip()


# ── Output modes ──────────────────────────────────────────────────────────────

def print_terminal(digest: str, timestamp: str):
    print(f"\n{DIVIDER}")
    print(f"  AI TOOLS DIGEST — {timestamp}")
    print(DIVIDER)
    print(digest)
    print(f"{DIVIDER}\n")


TRIGGER_LABELS = {
    "wake":           "lid open",
    "manual":         "manual",
    "automatic":      "automatic",
    "github_actions": "GitHub Actions",
}

# Patterns that indicate a non-significant release (alpha, nightly, dev)
_NOISE_RE = re.compile(r"\b(alpha|nightly|\.dev|pre-?release|rc\d*)\b", re.I)

def is_significant(items: list) -> bool:
    """Return True if any item looks like a real release, not just noise."""
    return any(not _NOISE_RE.search(i["title"]) for i in items)


def _load_digests() -> list:
    path = DOCS_DIR / "digests.json"
    if path.exists():
        return json.loads(path.read_text())
    return []


def _render_html(digests: list, curl_example: str) -> str:
    if not digests:
        entries_html = "<p style='color:#484f58'>No digests yet.</p>"
    else:
        parts = []
        for i, d in enumerate(digests):
            escaped = (d["content"]
                .replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;"))
            trigger = TRIGGER_LABELS.get(d.get("trigger", ""), d.get("trigger", ""))
            n       = d.get("items", "?")
            label   = f"{d['timestamp']}  ·  {n} items  ·  {trigger}"
            parts.append(f"""  <details{'  open' if i == 0 else ''}>
    <summary>{label}</summary>
    <pre>{escaped}</pre>
  </details>""")
        entries_html = "\n".join(parts)

    latest_ts = digests[0]["timestamp"] if digests else "—"
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>AI Tools Digest</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ background: #0d1117; color: #e6edf3; font-family: 'SF Mono','Fira Code',monospace; padding: 40px 24px; }}
    .wrap {{ max-width: 720px; margin: 0 auto; }}
    .site-label {{ color: #58a6ff; font-size: .7rem; letter-spacing: .1em; text-transform: uppercase; margin-bottom: 2px; }}
    .latest-ts {{ color: #484f58; font-size: .72rem; margin-bottom: 32px; }}
    details {{ border: 1px solid #21262d; border-radius: 6px; margin-bottom: 12px; overflow: hidden; }}
    details[open] {{ border-color: #30363d; }}
    summary {{
      padding: 10px 14px; cursor: pointer; font-size: .75rem; color: #8b949e;
      list-style: none; user-select: none;
    }}
    summary::-webkit-details-marker {{ display: none; }}
    summary::before {{ content: '▶ '; font-size: .6rem; color: #484f58; }}
    details[open] summary::before {{ content: '▼ '; }}
    details[open] summary {{ color: #e6edf3; border-bottom: 1px solid #21262d; }}
    pre {{ padding: 16px 14px; white-space: pre-wrap; line-height: 1.8; font-size: .82rem; color: #c9d1d9; }}
    .tip {{ margin-top: 28px; padding: 10px 14px; background: #161b22; border: 1px solid #21262d; border-radius: 6px; font-size: .72rem; color: #484f58; }}
    .tip code {{ color: #58a6ff; }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="site-label">AI Tools Digest</div>
    <div class="latest-ts">last updated {latest_ts}</div>
{entries_html}
    <div class="tip">terminal: <code>{curl_example}</code></div>
  </div>
</body>
</html>"""


def push_github_pages(digest: str, timestamp: str, items: list,
                      username: str, repo: str,
                      base_url: str = "", trigger: str = "automatic",
                      max_history: int = 50):
    DOCS_DIR.mkdir(exist_ok=True)

    page_url     = base_url or f"https://{username}.github.io/{repo}"
    curl_example = f"curl -s {page_url}/latest.txt"

    # Always update latest.txt
    (DOCS_DIR / "latest.txt").write_text(
        f"AI Tools Digest — {timestamp}\n{DIVIDER}\n{digest}\n"
    )

    # Load history, prepend new entry, trim
    digests = _load_digests()
    digests.insert(0, {
        "timestamp": timestamp,
        "trigger":   trigger,
        "items":     len(items),
        "content":   digest,
    })
    digests = digests[:max_history]
    (DOCS_DIR / "digests.json").write_text(json.dumps(digests, indent=2))

    # Regenerate full HTML from history
    (DOCS_DIR / "index.html").write_text(_render_html(digests, curl_example))

    cwd = str(SCRIPT_DIR)
    subprocess.run(["git", "add", "docs/", "seen_items.json"], cwd=cwd)
    result = subprocess.run(
        ["git", "commit", "-m", f"digest: {timestamp}"],
        cwd=cwd, capture_output=True, text=True
    )
    if "nothing to commit" not in result.stdout + result.stderr:
        push = subprocess.run(["git", "push"], cwd=cwd, capture_output=True, text=True)
        if push.returncode == 0:
            print(f"  → pushed to {page_url}", file=sys.stderr)
        else:
            print(f"  [warn] git push failed: {push.stderr.strip()}", file=sys.stderr)


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    config  = load_config()
    verbose = config.get("verbose", False)

    # Build feed list
    feeds = list(DEFAULT_FEEDS) if config.get("include_defaults", True) else []
    for f in config.get("custom_feeds", []):
        feeds.append((f["name"], f["url"]))

    prompt  = config.get("prompt", DEFAULT_PROMPT)
    backend = config.get("backend", DEFAULT_BACKEND)
    model   = config.get("model", DEFAULT_MODEL)

    # Fetch
    seen      = load_seen()
    new_items = fetch_new_items(feeds, seen, verbose=verbose)

    if not new_items:
        sys.exit(0)  # silence = nothing new; callers treat as no-op

    for item in new_items:
        seen.add(item["id"])
    save_seen(seen)

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    digest    = summarize(new_items, prompt, backend, model)

    # Always print to terminal
    print_terminal(digest, timestamp)

    # Optionally push to GitHub Pages
    if config.get("output") == "github_pages":
        gp          = config.get("github_pages", {})
        username    = gp.get("username", "")
        repo        = gp.get("repo", "ai-digest")
        base_url    = gp.get("base_url", "")
        trigger     = os.environ.get("DIGEST_TRIGGER", "automatic")
        max_history = gp.get("max_history", 50)
        significant = is_significant(new_items)

        if not username:
            print("[warn] github_pages.username not set in config.yaml", file=sys.stderr)
        elif not significant and not config.get("github_pages", {}).get("push_noise", False):
            print("  → skipping push (only alpha/nightly/dev releases)", file=sys.stderr)
        else:
            push_github_pages(digest, timestamp, new_items,
                              username, repo, base_url, trigger, max_history)


if __name__ == "__main__":
    main()
