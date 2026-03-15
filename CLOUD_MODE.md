# Cloud mode

Run ai-landscape-digest automatically in the cloud and view your digest from anywhere — no local machine needed.

GitHub Actions fetches feeds, summarizes with your chosen LLM, and publishes the result to GitHub Pages every 6 hours.

---

## Recommended backend: Gemini

Use **Gemini** — it has a free tier that's more than sufficient for a digest run every few hours.

Get a free API key at [aistudio.google.com](https://aistudio.google.com) → Get API key.

---

## Setup

### 1. Fork this repo

Fork `PR0CK0/ai-landscape-digest` to your GitHub account.

### 2. Add your API key as a secret

Go to your fork → **Settings → Secrets and variables → Actions → Secrets tab** → New repository secret:

| Name | Value |
|---|---|
| `GEMINI_API_KEY` | your Gemini API key |

For other backends:

| Backend | Secret name |
|---|---|
| Gemini *(recommended — free tier)* | `GEMINI_API_KEY` |
| Claude | `ANTHROPIC_API_KEY` |
| Codex | `OPENAI_API_KEY` |

### 3. Add GitHub Pages variables

Same page → **Variables tab** → New repository variable. Add these:

| Name | Value |
|---|---|
| `PAGES_USERNAME` | your GitHub username |
| `PAGES_REPO` | `ai-landscape-digest` (or whatever you named your fork) |
| `PAGES_TZ` | your timezone, e.g. `America/New_York` *(optional — defaults to UTC)* |
| `PAGES_URL` | your custom domain URL, e.g. `https://procko.pro/ai-landscape-digest` *(optional)* |

### 4. Enable GitHub Pages

Go to your fork → **Settings → Pages**:
- Source: **GitHub Actions**
- Save

### 5. Trigger a run

Go to **Actions → AI Digest → Run workflow** to fire your first run manually. After that it runs automatically every 6 hours.

Your digest will be live at:
```
https://YOUR_USERNAME.github.io/ai-landscape-digest/
```

---

## Adjusting the schedule

Edit `.github/workflows/digest.yml` and change the cron line:

```yaml
schedule:
  - cron: '0 */6 * * *'   # every 6 hours (default)
  # - cron: '0 8 * * *'   # daily at 8am UTC
  # - cron: '0 */4 * * *' # every 4 hours
```

---

## Switching backends

Edit the `Install` step and `Run digest` env in `.github/workflows/digest.yml`, then update `backend` and `model` in the `Generate cloud config` step:

```yaml
# Gemini (default — free tier)
- name: Install Gemini CLI
  run: npm install -g @google/gemini-cli
...
env:
  GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}

# Claude
- name: Install Claude CLI
  run: npm install -g @anthropic-ai/claude-code
...
env:
  ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
```

---

## Known limitations

- **No Ollama** — GitHub Actions runners have no local GPU; use a cloud backend
- **Dedup resets between runs** — `seen_items.json` is not committed, so each run processes the last `seen_ttl_days` of feeds. Items may repeat across runs if they stay in the feed window.
- **No config to commit** — the workflow generates its config at runtime from your GitHub Actions secrets and variables; nothing personal lives in the repo
