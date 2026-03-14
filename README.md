# ai-digest

![Python](https://img.shields.io/badge/python-3.9%2B-blue?logo=python&logoColor=white) ![License](https://img.shields.io/badge/license-MIT-green) ![Platform](https://img.shields.io/badge/platform-macOS%20%7C%20Linux%20%7C%20Windows-lightgrey) ![LLMs](https://img.shields.io/badge/LLM-Claude%20%7C%20Gemini%20%7C%20Codex%20%7C%20Ollama-8A2BE2)

Your local AI release feed, summarized and delivered on lid open — powered by whatever LLM CLI you already have.

## Table of Contents

- [What it does](#what-it-does)
- [Install](#install)
- [Configuration](#configuration)
- [Default feeds](#default-feeds)
- [Custom feeds](#custom-feeds)
- [Switching backends](#switching-backends)
- [Commands & flags](#commands--flags)
- [Timer & background checks](#timer--background-checks)
- [GitHub Pages *(experimental)*](#github-pages-experimental-)
- [Workspace](#workspace)
- [Testing](#testing)
- [File reference](#file-reference)
- [License](#license)

## What it does

Fetches RSS feeds from AI tools and research sources, deduplicates against what you've already seen, pipes the new stuff to your LLM CLI, and prints a terse digest. Runs automatically on lid open (and optionally on a background timer). No cloud accounts, no separate API keys — uses the CLI you already have.

## Install

```bash
git clone https://github.com/YOUR_USERNAME/ai-digest
cd ai-digest
pip install -r requirements.txt
python3 -m ai_digest install-trigger
```

That's it. Close and reopen your lid — it runs. Or `make run` to run now.

If you don't have `make`, `python3 -m ai_digest` is the same as `make run`.

## Configuration

**The only setting you must set:**

Copy `config.example.yaml` to `config.yaml` and set your backend:

```yaml
backend: claude   # or: gemini, codex, ollama
```

Everything else has sensible defaults.

**The full config reference** is in `config.example.yaml` — every option documented inline.

`config.yaml` is gitignored by default and stays local to your machine.

## Default feeds

| Source | Type |
|---|---|
| Claude Code | GitHub releases |
| Codex CLI | GitHub releases |
| Gemini CLI | GitHub releases |
| Aider | GitHub releases |
| Anthropic SDK (Python) | GitHub releases |
| OpenAI SDK (Python) | GitHub releases |
| OpenAI Blog | RSS |
| Hugging Face Blog | RSS |
| Last Week in AI | Newsletter RSS |
| Latent Space | Newsletter RSS |

Set `include_defaults: false` to use only your `custom_feeds`.

## Custom feeds

Any RSS or Atom feed URL works. The `name` field becomes the source label in the digest.

```yaml
custom_feeds:
  # Blogs & newsletters
  - name: "Simon Willison"
    url: "https://simonwillison.net/atom/everything/"
  - name: "The Batch (DeepLearning.AI)"
    url: "https://www.deeplearning.ai/the-batch/feed/"
  - name: "Interconnects"
    url: "https://www.interconnects.ai/feed"
  - name: "Ahead of AI"
    url: "https://magazine.sebastianraschka.com/feed"

  # GitHub releases — format is always https://github.com/OWNER/REPO/releases.atom
  - name: "LangChain"
    url: "https://github.com/langchain-ai/langchain/releases.atom"
  - name: "LlamaIndex"
    url: "https://github.com/run-llama/llama_index/releases.atom"
  - name: "Ollama"
    url: "https://github.com/ollama/ollama/releases.atom"
  - name: "vLLM"
    url: "https://github.com/vllm-project/vllm/releases.atom"

  # Hacker News filtered feeds — combine keywords and a minimum-points filter
  # to surface only high-signal posts
  - name: "Hacker News — LLMs"
    url: "https://hnrss.org/newest?q=LLM+OR+claude+OR+openai&count=15"
  - name: "Hacker News — AI (50+ pts)"
    url: "https://hnrss.org/newest?q=artificial+intelligence&points=50&count=10"

  # Company blogs
  - name: "Anthropic"
    url: "https://www.anthropic.com/rss.xml"
  - name: "Google DeepMind"
    url: "https://deepmind.google/blog/rss/"
  - name: "Mistral"
    url: "https://mistral.ai/news/rss/"

  # Research preprints
  - name: "arXiv CS.AI"
    url: "https://arxiv.org/rss/cs.AI"
  - name: "arXiv CS.LG"
    url: "https://arxiv.org/rss/cs.LG"
```

GitHub releases are the most reliable signal source: every repo on GitHub exposes `https://github.com/OWNER/REPO/releases.atom` automatically. No token needed for public repos.

## Switching backends

```yaml
# Claude Code (default) — uses your existing subscription
backend: claude

# Gemini CLI
backend: gemini
model: gemini-2.5-flash

# OpenAI Codex CLI
backend: codex
model: gpt-4o-mini

# Ollama (local, free) — great on M-series Macs
backend: ollama
model: qwen2.5-coder:32b
```

## Commands & flags

### Commands

| Command | Description |
|---|---|
| `make run` | Run digest immediately |
| `python3 -m ai_digest` | Same via package entrypoint |
| `python3 digest.py` | Compatibility entrypoint |
| `python3 -m ai_digest install-trigger` | Install platform wake + timer trigger |
| `python3 -m ai_digest uninstall-trigger` | Remove platform triggers |
| `python3 -m ai_digest doctor` | Check environment and installed triggers |
| `make reset` | Clear dedup cache (next run shows last 7 days) |
| `make test` | Run unit tests |
| `make test-integration` | Run integration tests (requires network) |

### Flags

| Flag | Default | Description |
|---|---|---|
| `--trigger TRIGGER` | `manual` | Override trigger label: `wake`, `manual`, `automatic`, `github_actions` |
| `--config PATH` | auto | Path to config.yaml |
| `--force` | off | Ignore seen_items.json and treat all fetched items as new |
| `--no-notify` | off | Disable desktop notifications for this run |

## Timer & background checks

The trigger system has two layers that work together:

**Platform timer** — installed by `python -m ai_digest install-trigger`:

| Platform | Mechanism | When it fires |
|---|---|---|
| macOS | `sleepwatcher` fires `~/.wakeup` on lid open; `launchd` timer fires on interval | Lid open + every N seconds |
| Linux | `systemd --user` service + timer unit | On boot + every N seconds |
| Windows | Task Scheduler XML definition | On logon + every N seconds |

**Python-layer throttle** — even if the platform fires more often than expected (e.g., repeated lid opens), the Python code checks the last-run timestamp and skips if not enough time has passed.

Both layers read the interval from `config.yaml`. A unified `check_interval` setting is coming (see `config.example.yaml`); for now, use `wake_min_interval_seconds`:

```yaml
# 1800  = 30 minutes
# 3600  = 1 hour  (default)
# 7200  = 2 hours
# 86400 = once a day
wake_min_interval_seconds: 3600

# Set false to always run on every trigger fire, ignoring the throttle
wake_throttle_enabled: true

# Set false to install only the lid-open wake hook and skip the background interval timer
timer_enabled: true
```

After changing `wake_min_interval_seconds`, re-run `install-trigger` to update the platform timer. The Python throttle picks up the new value immediately, but the launchd/systemd/Task Scheduler entry must be regenerated.

```bash
python3 -m ai_digest install-trigger
```

## GitHub Pages *(experimental)* ⚠️

> **⚠️ Experimental.** GitHub Pages publishing works but has known limitations. The primary use case for ai-digest is local runs on lid open and manual invocation — GitHub Pages is an optional layer on top.

**Known limitations:**
- Requires `config.yaml` to be committed to your fork (normally gitignored)
- GitHub Actions mode: `seen_items.json` must also be committed so dedup state persists between cloud runs — without it every scheduled run reprocesses all items from the last 7 days
- Push requires your git credentials to be configured (local push) or a repo secret (Actions)
- Not battle-tested across all environments

When `output: github_pages`, after printing to terminal the script also:
1. Writes `docs/latest.txt` and `docs/index.html`
2. Commits and pushes to origin

The page shows the digest, timestamp, and how it was triggered (lid open vs manual vs GitHub Actions).

Enable GitHub Pages for your repo under **Settings → Pages → Source: Deploy from branch → `main` / `docs`**.

Then access your digest at:
```bash
curl -s https://USERNAME.github.io/ai-digest/latest.txt
```

The `DIGEST_TRIGGER` environment variable controls the label shown on the page:

| Value | Label shown |
|---|---|
| `wake` (set by the platform trigger) | "triggered on lid open" |
| `manual` | "triggered manually" |
| `automatic` | "triggered automatically" |
| `github_actions` | "triggered by GitHub Actions" |

### Local push mode

Run on your own machine; each digest auto-commits and pushes to your fork.

1. Fork this repo to your GitHub account.
2. In `config.yaml`, set:
   ```yaml
   output: github_pages
   github_pages:
     username: YOUR_GITHUB_USERNAME
     repo: ai-digest
   ```
3. Enable Pages: **Settings → Pages → Deploy from branch → `main` / `docs`**.
4. Run normally (`make run` or via the wake trigger). Each digest commits `docs/` and pushes automatically.

`config.yaml` must be committed in your fork so the push workflow can read it. Because it contains your username (not secrets), committing it is safe.

### GitHub Actions mode

Cloud-scheduled — no local machine needed. The workflow runs on a cron schedule and pushes the digest from GitHub's runners.

1. Fork this repo to your GitHub account.
2. Add your LLM API key (or equivalent credential) as a repo secret: **Settings → Secrets → Actions → New repository secret**.
3. In `config.yaml` (committed to your fork), set:
   ```yaml
   output: github_pages
   backend: gemini        # or whichever backend your secret is for
   github_pages:
     username: YOUR_GITHUB_USERNAME
     repo: ai-digest
   ```
4. Enable Pages: **Settings → Pages → Deploy from branch → `main` / `docs`**.
5. Enable Actions: **Actions → (enable workflows if prompted)**.
6. The workflow in `.github/workflows/digest.yml` runs on schedule. Each run fetches feeds, summarizes, commits `docs/`, and pushes — all without your machine being on.

To trigger a run immediately: **Actions → digest → Run workflow**.

## Workspace

Config and state files live next to `config.yaml`. The default location is the repo root. Pass `--config PATH` to point at a config file in a different directory — state will follow it there.

## Testing

```bash
# Unit tests only (fast, no network, no LLM)
make test

# Integration tests (real network, real feeds)
make test-integration

# Everything
pytest
```

Unit tests mock all external calls (feedparser, subprocess). Integration tests hit real feed URLs and verify the JSON dedup round-trips correctly.

## File reference

```
ai_digest/
  app.py             application core + output helpers
  __main__.py        python -m ai_digest entrypoint
  cli.py             argument parsing
  constants.py       paths and defaults
  feeds.py           default feed list
  prompts.py         built-in summarization prompt
  settings.py        config loading
  paths.py           platform-aware file paths
  doctor.py          environment diagnostics
  installers.py      platform trigger install/uninstall + templates
  adapters/
    notifiers.py     desktop notification adapters
    triggers.py      trigger lifecycle behavior
config.yaml          your config (gitignored)
config.example.yaml  full config reference
seen_items.json      dedup state
Makefile             convenience commands
requirements.txt     Python deps
tests/
  test_unit.py
  test_integration.py
.github/
  workflows/
    digest.yml       GitHub Actions scheduled runner
```

## License

MIT — free to use, modify, and distribute. See [LICENSE](LICENSE).

Conceived and directed by [PR0CK0](https://github.com/PR0CK0). Programmed with [Claude Code](https://claude.ai/code), [Gemini CLI](https://github.com/google-gemini/gemini-cli), and [Codex CLI](https://github.com/openai/codex).
