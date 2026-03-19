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
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta
from html import escape, unescape
from typing import Callable, Optional

from ai_digest.adapters.notifiers import build_notifier
from ai_digest.adapters.triggers import build_trigger_adapter
from ai_digest.cli import parse_args
from ai_digest.constants import (
    CONFIG_FILE,
    DEFAULT_BACKEND,
    DEFAULT_CHECK_INTERVAL,
    DEFAULT_MODEL,
    DIVIDER,
    DOCS_DIR,
    FEED_TIMEOUT,
    LAST_FETCH_FILE,
    LOOKBACK_DAYS,
    SCRIPT_DIR,
    SEEN_FILE,
    TRIGGER_LABELS,
)
from ai_digest.installers import install_trigger, uninstall_trigger, purge
from ai_digest.doctor import doctor_report
from ai_digest.feeds import DEFAULT_FEEDS
from ai_digest.prompts import DEFAULT_PROMPT
from ai_digest.settings import build_app_config, load_raw_config
import ai_digest.paths as paths

NotifierFn = Callable[[str, str, Optional[str], Optional[str]], None]

USER_DOCS_DIR = paths.user_documents_dir()
LOG_FILE = paths.default_log_file()


def current_timestamp(tz_name: str = "") -> str:
    from datetime import datetime
    import zoneinfo
    if tz_name:
        try:
            tz = zoneinfo.ZoneInfo(tz_name)
            return datetime.now(tz).strftime("%Y-%m-%d %H:%M %Z")
        except Exception:
            pass
    return datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z")


def render_terminal_markdown(digest: str, timestamp: str) -> str:
    return f"\n# AI Landscape Digest\n_Updated {timestamp}_\n\n{digest}\n"


def render_latest_markdown(digest: str, timestamp: str) -> str:
    return f"# AI Landscape Digest\n\n_Updated {timestamp}_\n\n{digest}\n"


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
    cmd = ["codex", "exec", prompt]
    if model and model != "default":
        cmd = ["codex", "exec", "--model", model, prompt]
    return cmd


def _cmd_ollama(prompt: str, model: str) -> list:
    selected_model = model if model and model != "default" else "default"
    return ["ollama", "run", selected_model, prompt]


BACKENDS = {
    "claude":  _cmd_claude,
    "gemini":  _cmd_gemini,
    "codex":   _cmd_codex,
    "ollama":  _cmd_ollama,
}
NOTIFIER = build_notifier()


class Spinner:
    FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

    def __init__(self):
        self._msg = ""
        self._stop = threading.Event()
        self._lock = threading.Lock()
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
        sys.stderr.write("\r\033[K")
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


def load_config() -> dict:
    return load_raw_config(CONFIG_FILE)


def load_seen() -> set:
    return set(load_seen_records().keys())


def save_seen(seen: set):
    now = time.time()
    with open(SEEN_FILE, "w") as f:
        json.dump(sorted(seen)[-2000:], f)


def load_seen_records() -> dict:
    if not SEEN_FILE.exists():
        return {}
    with open(SEEN_FILE) as f:
        data = json.load(f)
    if isinstance(data, list):
        now = time.time()
        return {item: now for item in data}
    if isinstance(data, dict):
        records = {}
        for item_id, ts in data.items():
            try:
                records[item_id] = float(ts)
            except (TypeError, ValueError):
                continue
        return records
    return {}


def prune_seen_records(records: dict, ttl_days: int, now: Optional[float] = None) -> dict:
    if now is None:
        now = time.time()
    cutoff = now - (ttl_days * 24 * 60 * 60)
    return {
        item_id: ts
        for item_id, ts in records.items()
        if ts >= cutoff
    }


def save_seen_records(records: dict):
    trimmed = dict(sorted(records.items(), key=lambda item: item[1])[-2000:])
    with open(SEEN_FILE, "w") as f:
        json.dump(trimmed, f, indent=2, sort_keys=True)


def strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", unescape(text or "")).strip()


def notify(title: str, message: str, action_label: Optional[str] = None, action_path: Optional[str] = None):
    NOTIFIER.send(title, message, action_label, action_path)


def open_report(path: str):
    NOTIFIER.open_path(path)


def check_url(url: str, timeout: int = FEED_TIMEOUT) -> bool:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "ai-digest/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return response.status < 400
    except Exception:
        return False


def get_ollama_default_model() -> str:
    result = subprocess.run(
        ["ollama", "list"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    if result.returncode != 0:
        err = result.stderr.strip()[:200]
        raise RuntimeError(f"ollama list failed: {err}")

    models = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line or line.startswith("NAME"):
            continue
        parts = line.split()
        if parts:
            models.append(parts[0])

    if not models:
        raise RuntimeError("no local Ollama models found; run `ollama pull <model>` first")

    preferred = [
        "ministral-3:3b",
        "qwen2.5-coder:32b",
        "qwen2.5-coder",
        "llama3.2",
        "llama3",
        "mistral:latest",
        "mistral",
    ]
    for name in preferred:
        if name in models:
            return name
    return models[0]


def load_last_fetch_at() -> Optional[float]:
    if not LAST_FETCH_FILE.exists():
        return None
    try:
        return float(LAST_FETCH_FILE.read_text().strip())
    except (OSError, ValueError):
        return None


def save_last_fetch_at(ts: Optional[float] = None):
    if ts is None:
        ts = time.time()
    LAST_FETCH_FILE.write_text(str(ts))


def wake_fetch_due(min_interval_seconds: int = DEFAULT_CHECK_INTERVAL,
                   now: Optional[float] = None) -> bool:
    if now is None:
        now = time.time()
    last_fetch_at = load_last_fetch_at()
    if last_fetch_at is None:
        return True
    return (now - last_fetch_at) >= min_interval_seconds


def format_interval_label(seconds: int) -> str:
    if seconds % 3600 == 0:
        hours = seconds // 3600
        if hours == 1:
            return "the last hour"
        return f"the last {hours} hours"
    if seconds % 60 == 0:
        minutes = seconds // 60
        if minutes == 1:
            return "the last minute"
        return f"the last {minutes} minutes"
    if seconds == 1:
        return "the last second"
    return f"the last {seconds} seconds"


def format_latency(seconds: float) -> str:
    if seconds < 10:
        return f"{seconds:.1f}s"
    return f"{round(seconds)}s"


def _fetch_one(source: str, url: str, seen: set, cutoff: datetime, verbose: bool) -> list:
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
            "source": source,
            "title": entry.get("title", "").strip(),
            "link": entry.get("link", ""),
            "summary": strip_html(entry.get("summary", ""))[:500],
            "id": item_id,
        })
    return items


def fetch_new_items(feeds: list, seen: set, verbose: bool = False) -> list:
    cutoff = datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)
    new_items = []
    total = len(feeds)
    print_lock = threading.Lock()
    pad = max(len(source) for source, _ in feeds)

    with ThreadPoolExecutor(max_workers=total) as pool:
        futures = {
            pool.submit(_fetch_one, source, url, seen, cutoff, verbose): source
            for source, url in feeds
        }
        for future in as_completed(futures):
            source = futures[future]
            items = future.result()
            new_items.extend(items)
            count = len(items)
            with print_lock:
                if count > 0:
                    sys.stderr.write(f"  ✓ {source:<{pad}}  {count} new\n")
                else:
                    sys.stderr.write(f"  · {source:<{pad}}  —\n")
                sys.stderr.flush()

    sys.stderr.write("\n")
    return new_items


def summarize(items: list, prompt: str, backend: str = DEFAULT_BACKEND, model: str = DEFAULT_MODEL) -> str:
    raw = "\n\n".join(
        f"[{item['source']}] {item['title']}\n{item['link']}\n{item['summary']}"
        for item in items
    )
    full_prompt = f"{prompt}\n\nNEW RELEASES:\n\n{raw}"

    build_cmd = BACKENDS.get(backend)
    if not build_cmd:
        print(f"  [warn] unknown backend '{backend}', falling back to claude", file=sys.stderr)
        build_cmd = BACKENDS["claude"]

    if backend == "ollama" and model == "default":
        try:
            model = get_ollama_default_model()
        except FileNotFoundError:
            return "[error] 'ollama' not found — is it installed and on PATH?]"
        except subprocess.TimeoutExpired:
            return "[error] ollama list timed out after 10s]"
        except RuntimeError as e:
            return f"[error] {e}]"

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


def print_terminal(digest: str, timestamp: str):
    print(render_terminal_markdown(digest, timestamp))


_NOISE_RE = re.compile(r"\b(alpha|nightly|\.dev|pre-?release|rc\d*)\b", re.I)


def is_significant(items: list) -> bool:
    return any(not _NOISE_RE.search(item["title"]) for item in items)


def _load_digests() -> list:
    path = DOCS_DIR / "digests.json"
    if path.exists():
        return json.loads(path.read_text())
    return []


def _sources_html(sources: list) -> str:
    if not sources:
        return ""
    rows = []
    for source in sources:
        src = source.get("source", "")
        title = source.get("title", "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        link = source.get("link", "")
        rows.append(
            f'    <li><span class="src-tag">{src}</span>'
            f'<a href="{link}" target="_blank" rel="noopener">{title}</a></li>'
        )
    return (
        '\n  <details class="sources">\n'
        '    <summary>sources</summary>\n'
        '    <ul>\n' + "\n".join(rows) + "\n    </ul>\n"
        "  </details>"
    )


def _format_inline_markdown(text: str) -> str:
    escaped = escape(text)
    escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"(?<![a-zA-Z0-9<])(/[a-z][a-z0-9-]*)(?![a-zA-Z0-9/])", r"<code>\1</code>", escaped)
    return escaped


def _render_digest_markdown(content: str) -> str:
    blocks = []
    in_list = False

    def close_list():
        nonlocal in_list
        if in_list:
            blocks.append("    </ul>")
            in_list = False

    for raw_line in content.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()

        if not stripped:
            close_list()
            continue

        if stripped.startswith("### "):
            close_list()
            blocks.append(f"    <h3>{_format_inline_markdown(stripped[4:])}</h3>")
            continue

        if stripped.startswith("## "):
            close_list()
            blocks.append(f"    <h2>{_format_inline_markdown(stripped[3:])}</h2>")
            continue

        if stripped.startswith("# "):
            close_list()
            blocks.append(f"    <h2>{_format_inline_markdown(stripped[2:])}</h2>")
            continue

        if stripped.startswith("- ") or stripped.startswith("* "):
            if not in_list:
                blocks.append('    <ul class="digest-list">')
                in_list = True
            item_html = _format_inline_markdown(stripped[2:])
            item_class = ' class="breaking"' if "BREAKING" in stripped.upper() else ""
            blocks.append(f"      <li{item_class}>{item_html}</li>")
            continue

        close_list()
        paragraph_class = ' class="breaking-label"' if "BREAKING" in stripped.upper() else ""
        blocks.append(f"    <p{paragraph_class}>{_format_inline_markdown(stripped)}</p>")

    close_list()
    return '<div class="digest-markdown">\n' + "\n".join(blocks) + "\n  </div>"


def _render_html(digests: list, curl_example: str, repo_url: str = "", commit_sha: str = "", username: str = "") -> str:
    if not digests:
        entries_html = "<p style='color:#484f58'>No digests yet.</p>"
    else:
        parts = []
        for index, digest in enumerate(digests):
            digest_html = _render_digest_markdown(digest["content"])
            trigger = TRIGGER_LABELS.get(digest.get("trigger", ""), digest.get("trigger", ""))
            count = digest.get("item_count", digest.get("items", "?"))
            parts_meta = [f"{count} items", trigger]
            model = digest.get("model")
            latency_seconds = digest.get("latency_seconds")
            if model:
                parts_meta.append(model)
            if latency_seconds is not None:
                parts_meta.append(format_latency(float(latency_seconds)))
            if digest.get("force"):
                parts_meta.append("(forced)")
            label = f"{digest['timestamp']}  ·  " + "  ·  ".join(parts_meta)
            src_html = _sources_html(digest.get("sources", []))
            parts.append(f"""  <details{'  open' if index == 0 else ''}>
    <summary>{label}</summary>
{digest_html}{src_html}
  </details>""")
        entries_html = "\n".join(parts)

    latest_ts = digests[0]["timestamp"] if digests else "—"

    title_html = (
        f'<a href="{repo_url}" target="_blank" rel="noopener" class="site-link">AI Landscape Digest</a>'
        if repo_url else "AI Landscape Digest"
    )

    footer_parts = []
    if curl_example:
        footer_parts.append(f'terminal: <code>{curl_example}</code>')
    if commit_sha and repo_url:
        short_sha = commit_sha[:7]
        footer_parts.append(f'<a href="{repo_url}/commit/{commit_sha}" target="_blank" rel="noopener" class="footer-link">{short_sha}</a>')
    elif commit_sha:
        footer_parts.append(commit_sha[:7])
    if username:
        footer_parts.append(f'<a href="https://github.com/{username}" target="_blank" rel="noopener" class="footer-link">@{username}</a>')
    footer_html = '    <div class="tip">' + '  ·  '.join(footer_parts) + '</div>' if footer_parts else ''

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>AI Landscape Digest</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ background: #0d1117; color: #e6edf3; font-family: 'SF Mono','Fira Code',monospace; padding: 40px 24px; }}
    .wrap {{ max-width: 720px; margin: 0 auto; }}
    .site-label {{ color: #58a6ff; font-size: .7rem; letter-spacing: .1em; text-transform: uppercase; margin-bottom: 2px; }}
    .site-link {{ color: inherit; text-decoration: none; }}
    .site-link:hover {{ color: #79c0ff; }}
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
    .digest-markdown {{ padding: 16px 14px 6px; color: #c9d1d9; }}
    .digest-markdown h1, .digest-markdown h2, .digest-markdown h3 {{
      font-size: .92rem; line-height: 1.3; margin: 0 0 10px; color: #f0f6fc;
    }}
    .digest-markdown h2, .digest-markdown h3 {{
      font-size: .8rem; text-transform: uppercase; letter-spacing: .04em; color: #58a6ff;
      margin-top: 18px;
    }}
    .digest-markdown p {{
      margin: 0 0 10px; line-height: 1.55; font-size: .84rem;
    }}
    .digest-markdown .breaking-label {{ color: #ffb86b; font-weight: 700; }}
    .digest-list {{ list-style: none; margin: 0 0 6px; padding: 0; }}
    .digest-list li {{
      position: relative; padding-left: 14px; margin: 0 0 8px; line-height: 1.5; font-size: .84rem;
    }}
    .digest-list li::before {{
      content: '•'; position: absolute; left: 0; color: #8b949e;
    }}
    .digest-list li.breaking {{ color: #ffd8a8; }}
    .digest-markdown strong {{ color: #f0f6fc; font-weight: 700; }}
    .digest-markdown code {{
      color: #7ee787; background: #161b22; padding: 1px 5px; border-radius: 4px; font-size: .78rem;
    }}
    .tip {{ margin-top: 28px; padding: 10px 14px; background: #161b22; border: 1px solid #21262d; border-radius: 6px; font-size: .72rem; color: #484f58; }}
    .tip code {{ color: #58a6ff; }}
    .footer-link {{ color: #484f58; text-decoration: none; }}
    .footer-link:hover {{ color: #8b949e; }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="site-label">{title_html}</div>
    <div class="latest-ts">last updated {latest_ts}</div>
{entries_html}
{footer_html}
  </div>
</body>
</html>"""


def generate_html_report(target_dir: Path, digest: str, timestamp: str, items: list,
                         trigger: str = "automatic", model: str = "",
                         latency_seconds: Optional[float] = None,
                         max_history: int = 50, page_url: str = "",
                         repo_url: str = "", username: str = "",
                         force: bool = False):
    target_dir.mkdir(parents=True, exist_ok=True)

    curl_example = f"curl -s {page_url}/latest.txt" if page_url else ""
    commit_sha = os.environ.get("GITHUB_SHA", "")

    (target_dir / "latest.txt").write_text(
        render_latest_markdown(digest, timestamp)
    )

    digests = _load_digests_from(target_dir)
    digests.insert(0, {
        "timestamp": timestamp,
        "trigger": trigger,
        "item_count": len(items),
        "model": model,
        "latency_seconds": latency_seconds,
        "force": force,
        "sources": [{"source": item["source"], "title": item["title"], "link": item["link"]}
                    for item in items if item.get("link")],
        "content": digest,
    })
    digests = digests[:max_history]
    (target_dir / "digests.json").write_text(json.dumps(digests, indent=2))
    (target_dir / "index.html").write_text(_render_html(digests, curl_example, repo_url, commit_sha, username))
    (target_dir / ".nojekyll").touch()


def _load_digests_from(target_dir: Path) -> list:
    path = target_dir / "digests.json"
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            pass
    return []


def push_github_pages(target_dir: Path, timestamp: str, username: str, repo: str, base_url: str = ""):
    page_url = base_url or f"https://{username}.github.io/{repo}"
    cwd = str(SCRIPT_DIR)

    # In GitHub Actions, deployment is handled by the workflow (upload-pages-artifact +
    # deploy-pages). Skip git operations here to keep master clean.
    if (os.environ.get("DIGEST_TRIGGER") or "").startswith("github_actions"):
        print(f"  → docs/ written; GitHub Actions will deploy to {page_url}", file=sys.stderr)
        return

    # Check if we are in a git repo
    if not (SCRIPT_DIR / ".git").exists():
        print("  [warn] not a git repository, skipping push", file=sys.stderr)
        return

    subprocess.run(["git", "add", str(target_dir), str(SEEN_FILE)], cwd=cwd)
    result = subprocess.run(
        ["git", "commit", "-m", f"digest: {timestamp}"],
        cwd=cwd, capture_output=True, text=True
    )
    if "nothing to commit" not in result.stdout + result.stderr:
        has_remote = subprocess.run(["git", "remote"], cwd=cwd, capture_output=True, text=True).stdout.strip()
        if has_remote:
            push = subprocess.run(["git", "push"], cwd=cwd, capture_output=True, text=True)
            if push.returncode == 0:
                print(f"  → pushed to {page_url}", file=sys.stderr)
            else:
                print(f"  [warn] git push failed: {push.stderr.strip()}", file=sys.stderr)
        else:
            print(f"  → local files updated (no git remote found)", file=sys.stderr)


def main(argv=None):
    global CONFIG_FILE, SEEN_FILE, DOCS_DIR, LAST_FETCH_FILE, USER_DOCS_DIR, LOG_FILE
    args = parse_args([] if argv is None else argv)

    # Resolve workspace paths
    if args.config:
        _root = Path(args.config).resolve().parent
        CONFIG_FILE = Path(args.config).resolve()
    else:
        _root = SCRIPT_DIR
        CONFIG_FILE = _root / "config.yaml"
    SEEN_FILE = _root / "seen_items.json"
    DOCS_DIR = _root / "docs"
    LAST_FETCH_FILE = _root / ".last_fetch_at"
    USER_DOCS_DIR = paths.user_documents_dir()
    LOG_FILE = paths.default_log_file()

    if args.command == "install-trigger":
        config = build_app_config(load_config())
        print(install_trigger(config))
        return
    if args.command == "uninstall-trigger":
        print(uninstall_trigger())
        return
    if args.command == "purge":
        print(purge())
        return
    if args.command == "doctor":
        print(doctor_report(args.config))
        return
    if args.command == "reset":
        neither = not args.seen and not args.history
        clear_seen = args.seen or neither
        clear_history = args.history or neither
        if clear_seen:
            save_seen_records({})
            print(f"  ✓ Cleared seen_items.json — next run reprocesses the last {LOOKBACK_DAYS} days")
        if clear_history:
            for d in (USER_DOCS_DIR, DOCS_DIR):
                digests_file = d / "digests.json"
                html_file = d / "index.html"
                if digests_file.exists():
                    digests_file.write_text("[]")
                    print(f"  ✓ Cleared {digests_file}")
                if html_file.exists():
                    html_file.unlink()
                    print(f"  ✓ Removed {html_file}")
        return

    config = build_app_config(load_config())
    trigger_name = args.trigger or os.environ.get("DIGEST_TRIGGER", "manual")
    trigger = build_trigger_adapter(
        trigger=trigger_name,
        notifier=notify,
        notifications_enabled=not args.no_notify,
        due_fn=wake_fetch_due,
        save_last_fetch_at_fn=save_last_fetch_at,
        interval_label_fn=format_interval_label,
    )

    if not trigger.should_run(config):
        trigger.on_skip(config)
        sys.exit(0)

    trigger.on_start(config)

    if args.force:
        seen_records = {}
    else:
        seen_records = prune_seen_records(load_seen_records(), config.seen_ttl_days)
    seen = set(seen_records.keys())
    new_items = fetch_new_items(config.feeds, seen, verbose=config.verbose)

    if not new_items:
        trigger.on_no_items(config)
        print("All caught up! No new items to summarize.")
        sys.exit(0)

    if not args.force:
        for item in new_items:
            seen_records[item["id"]] = time.time()
        save_seen_records(seen_records)

    timestamp = current_timestamp(config.timezone)
    if config.html_output and trigger_name == "manual":
        print("  → HTML report will open in browser upon completion", file=sys.stderr)
    trigger.on_summarize(config, config.backend, config.model)
    summary_started_at = time.time()
    digest = summarize(new_items, config.prompt, config.backend, config.model)
    latency_seconds = time.time() - summary_started_at

    if digest.startswith("[error]"):
        print(f"  {digest}", file=sys.stderr)
        trigger.on_error(config)
        sys.exit(1)

    if not digest.strip():
        print("All caught up! Model filtered all items — nothing to publish.", file=sys.stderr)
        sys.exit(0)

    trigger.on_success(config, len(new_items), config.backend)

    print_terminal(digest, timestamp)

    # Local HTML report in Documents folder
    if config.html_output:
        generate_html_report(
            USER_DOCS_DIR, digest, timestamp, new_items,
            trigger_name or "automatic", config.model, latency_seconds,
            force=args.force
        )
        report_path = USER_DOCS_DIR / "index.html"
        print(f"  → local report: {report_path}", file=sys.stderr)
        if trigger_name == "manual":
            open_report(str(report_path))
        else:
            trigger.on_html_ready(config, str(report_path))

    # GitHub Pages sync
    if config.output == "github_pages":
        github_pages = config.github_pages
        username = github_pages.get("username", "")
        repo = github_pages.get("repo", "ai-digest")
        base_url = github_pages.get("base_url", "")
        max_history = github_pages.get("max_history", 50)
        significant = is_significant(new_items)

        if not username:
            print("[warn] github_pages.username not set in config.yaml", file=sys.stderr)
        elif not significant and not github_pages.get("push_noise", False):
            print("  → skipping push (only alpha/nightly/dev releases)", file=sys.stderr)
        else:
            page_url = base_url or f"https://{username}.github.io/{repo}"
            repo_url = f"https://github.com/{username}/{repo}"
            generate_html_report(
                DOCS_DIR, digest, timestamp, new_items,
                trigger_name or "automatic", config.model, latency_seconds,
                max_history, page_url, repo_url, username,
                force=args.force
            )
            push_github_pages(DOCS_DIR, timestamp, username, repo, page_url)


if __name__ == "__main__":
    main()
