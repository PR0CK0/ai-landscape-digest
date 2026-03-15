# Cloud mode

Run the digest automatically on GitHub's servers on a schedule. Each run publishes output to GitHub Pages — accessible from any device, no local machine required.

The workflow lives at `.github/workflows/digest.yml`. By default it runs on manual trigger only; cron is commented out.

---

## Prerequisites

- A cloud LLM backend: `claude`, `gemini`, or `codex`. **Ollama cannot be used** — GitHub Actions runners have no local GPU.
- A fork of this repo on your GitHub account.

---

## Setup

### 1. Fork the repo

Fork `github.com/PR0CK0/ai-landscape-digest` to your GitHub account.

### 2. Add your LLM API key as a repo secret

**Settings → Secrets and variables → Actions → New repository secret**

The secret name must match what the CLI expects:

| Backend | Secret name |
|---|---|
| `claude` | `ANTHROPIC_API_KEY` |
| `gemini` | `GEMINI_API_KEY` |
| `codex` | `OPENAI_API_KEY` |

### 3. Commit a `config.yaml`

`config.yaml` is gitignored by default. For cloud mode you must commit it. Either remove the `config.yaml` line from `.gitignore`, or force-add it.

Minimal `config.yaml`:

```yaml
backend: claude          # or gemini, codex
output: github_pages
github_pages:
  username: YOUR_GITHUB_USERNAME
  repo: ai-landscape-digest
```

Commit this to `main`.

### 4. Expose `docs/`

Remove the `docs/` line from `.gitignore`, then commit an empty sentinel file so the directory is tracked:

```bash
mkdir -p docs
touch docs/.nojekyll
git add docs/.nojekyll
git commit -m "add docs/.nojekyll for GitHub Pages"
```

The `.nojekyll` file tells Pages to serve files as-is without Jekyll processing.

### 5. Expose `seen_items.json`

`seen_items.json` tracks which feed items have already been seen. Without it committed, every cloud run reprocesses everything from the last 7 days and dedup state is lost between runs.

Remove `seen_items.json` from `.gitignore` (there is no entry by default — check yours), then commit an empty state file:

```bash
echo '{}' > seen_items.json
git add seen_items.json
git commit -m "add empty seen_items.json for cloud dedup"
```

### 6. Enable GitHub Pages

**Settings → Pages → Source: Deploy from a branch → Branch: `main` / `docs` → Save**

### 7. Trigger a run

**Actions → AI Digest → Run workflow → Run workflow**

Watch the run. On success, the workflow commits `docs/index.html` and `docs/latest.txt` to `main` and Pages deploys automatically.

### 8. Enable a schedule (optional)

By default the workflow only runs on manual dispatch. To run on a cron schedule, open `.github/workflows/digest.yml` and uncomment the cron line:

```yaml
on:
  schedule:
    - cron: '0 * * * *'   # every hour — adjust to taste
  workflow_dispatch:
```

Commit the change to `main`.

---

## Accessing your digest

Once Pages is enabled and a run has completed:

```
https://YOUR_USERNAME.github.io/ai-landscape-digest/
```

Plain-text version:

```bash
curl -s https://YOUR_USERNAME.github.io/ai-landscape-digest/latest.txt
```

---

## Known limitations

- `config.yaml` must be committed to `main` (it is normally gitignored — remove that line).
- `seen_items.json` must be committed so dedup state persists between runs. Without it, every run is a full replay of the last 7 days.
- Ollama cannot be used — no local GPU on GitHub Actions runners.
- The workflow checks out and runs against the `main` branch. Keep your committed `config.yaml` and `seen_items.json` on `main`.
- The workflow has `contents: write` permission so it can commit `docs/` back to the repo. This is set in `.github/workflows/digest.yml` — do not remove it.
