# Cloud mode

Run ai-landscape-digest automatically in the cloud and view your digest from anywhere — no local machine needed.

The main reason to set this up is **custom feeds**. Fork the repo, add your own RSS sources (company blogs, GitHub release feeds, newsletters, whatever you actually follow), and get a hosted digest tuned to your specific interests — updating every 6 hours without your machine ever being on.

GitHub Actions fetches your feeds, summarizes with your chosen LLM, and publishes the result to GitHub Pages every 6 hours.

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
| `PAGES_MODEL` | Gemini model name *(optional — defaults to `gemini-2.0-flash-lite`)* |

**Model recommendation:** Use `gemini-2.0-flash-lite` (default) or `gemini-2.0-flash`. **Avoid `gemini-2.5-flash`** — it is a thinking/reasoning model that tends to ignore strict formatting instructions, producing verbose prose instead of the compact bullet format this project requires. If Gemini deprecates a model, update `PAGES_MODEL` in your repo variables without touching any code.

### 4. Enable GitHub Pages

Go to your fork → **Settings → Pages**:
- Source: **GitHub Actions**
- Save

### 5. Trigger a run

Go to **Actions → AI Digest → Run workflow**. Check **"Force re-process all items"** for your first run to seed the page, then click **Run workflow**. After that it runs automatically every 6 hours.

Your digest will be live at:
```
https://YOUR_USERNAME.github.io/ai-landscape-digest/
```

Or at your custom domain if you set `PAGES_URL`.

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

---

## Resetting state

Use the **Reset Digest State** workflow to clear dedup cache, digest history, or both — without editing any files manually.

**Actions → Reset Digest State → Run workflow**

| Input | Options | Description |
|---|---|---|
| `what` | `all` *(default)*, `seen_only`, `history_only` | What to clear |
| `rerun` | `true` / `false` | Trigger a fresh digest immediately after reset |

- **`seen_only`** — clears `seen_items.json` so the next scheduled run re-processes all items from the past `seen_ttl_days` window. Use this when you want a fresh summary without wiping the page history.
- **`history_only`** — clears `digests.json` so the hosted page starts from a clean slate. Existing seen-item dedup is preserved.
- **`all`** — clears both. Use `rerun: true` to immediately re-seed the page with a fresh digest.

State is persisted in the `ci-state` branch (not GitHub Actions cache). The reset workflow updates that branch directly.

---

## Known limitations

- **No Ollama** — GitHub Actions runners have no local GPU; use a cloud backend
- **Dedup via ci-state branch** — `seen_items.json` is persisted between runs in the `ci-state` branch. This branch is created automatically on first run and updated after each successful digest.
- **No config to commit** — the workflow generates its config at runtime from your GitHub Actions secrets and variables; nothing personal lives in the repo
