# ai-digest

Fetches AI tool release feeds, summarizes them with a local LLM CLI, and prints a terse digest to your terminal — automatically on lid open, or on demand.

No cloud hosting required. No API keys. Uses your existing Claude Code (or Gemini, Codex, or Ollama) subscription.

## How it works

```
lid open
  → sleepwatcher triggers ~/.wakeup
    → digest.py fetches RSS feeds (GitHub releases, blogs)
      → deduplicates against seen_items.json
        → pipes new items to: claude -p "summarize..."
          → prints digest to terminal
```

On subsequent opens, you only see what's new since last time.

Optionally: push `docs/latest.txt` + `docs/index.html` to a GitHub Pages branch so the digest is also available at a URL (`curl -s yoursite.com/ai-digest/latest.txt`).

## Requirements

- Python 3.9+
- macOS (for sleepwatcher / lid-open trigger)
- One of: `claude` CLI, `gemini` CLI, `codex` CLI, or `ollama`

## Install

```bash
git clone https://github.com/YOUR_USERNAME/ai-digest
cd ai-digest
make setup
```

`make setup` does:
1. `pip install feedparser pyyaml pytest`
2. `brew install sleepwatcher && brew services start sleepwatcher`
3. Writes `~/.wakeup` pointing at this repo
4. Copies `config.example.yaml` → `config.yaml` for you to edit

## Configuration

Edit `config.yaml` (gitignored — stays local):

```yaml
# Which CLI to use for summarization
# Options: claude (default) | gemini | codex | ollama
backend: claude

# Model override (leave as "default" to use each CLI's default)
# claude:  claude-haiku-4-5-20251001 | claude-sonnet-4-6
# gemini:  gemini-2.5-flash
# codex:   gpt-4o-mini
# ollama:  llama3 | qwen2.5-coder:32b
model: default

# Output mode
# "terminal"     — print to stdout only (default)
# "github_pages" — also write docs/ and git push to GitHub Pages
output: terminal

# GitHub Pages (only used when output: github_pages)
github_pages:
  username: YOUR_GITHUB_USERNAME
  repo: ai-digest
  # base_url: https://yourdomain.com/ai-digest  # optional custom domain

# Set false to disable built-in defaults and use only custom_feeds
include_defaults: true

# Add your own feeds
custom_feeds:
  - name: "Simon Willison"
    url: "https://simonwillison.net/atom/everything/"
  - name: "Hacker News AI"
    url: "https://hnrss.org/newest?q=LLM+OR+claude+OR+openai&count=10"
```

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

## Switching LLM backends

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

## GitHub Pages mode

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
| `wake` (set by `~/.wakeup`) | "triggered on lid open" |
| `manual` | "triggered manually" |
| `automatic` | "triggered automatically" |
| `github_actions` | "triggered by GitHub Actions" |

## Usage

```bash
make run           # run digest right now
make reset         # clear dedup cache (shows last 7 days on next run)
make test          # run unit tests
make test-integration  # run integration tests (hits real feeds)
```

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
digest.py              main script
config.yaml            your local config (gitignored)
config.example.yaml    reference config to copy from
seen_items.json        dedup state (tracks last 2000 item IDs)
wakeup.sh              source for ~/.wakeup (versioned here)
requirements.txt       Python deps
Makefile               convenience commands
tests/
  test_unit.py         unit tests (mock everything)
  test_integration.py  integration tests (real network/fs)
pytest.ini             test config
```
