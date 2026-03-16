# Changelog

## v0.5.4

- CI: opt into Node.js 24 for GitHub Actions jobs (`FORCE_JAVASCRIPT_ACTIONS_TO_NODE24`) ahead of June 2026 forced migration
- Docs: added cloud mode disclaimer to README — cloud mode is under active testing; many LLMs struggle with strict formatting requirements; local Ollama (`ministral-3:3b`) remains the gold standard

---

## v0.5.3

- Cloud model switched from `gemini-2.5-flash` to `gemini-2.0-flash-lite` (non-thinking model, better instruction following)
- `PAGES_MODEL` GitHub Actions variable added — override the Gemini model without touching workflow code; defaults to `gemini-2.0-flash-lite`
- Prompt: rewrote with explicit `INCLUDE ONLY` / `EXCLUDE` / `FORMAT RULES` sections to combat Gemini's tendency to ignore vague instructions
- Prompt: hard ban on `##` for individual tool names; one bullet per tool; at most 6 comma-separated changes per tool
- Docs: noted `gemini-2.5-flash` as a poor choice (thinking model, ignores formatting rules)

---

## v0.5.2

- Prompt: skip newsletters, blog posts, research papers, policy/legal news entirely
- Prompt: consolidate multiple releases of the same tool into one bullet
- Prompt: `## Category` grouping with `**Tool**:` inline prefix per bullet
- Prompt: tighten per-change word limit to 2–6 words

---

## v0.5.1

- Fix: reset workflow YAML parse error — heredoc with unindented content broke
  validation; moved ci-state README to `.github/ci-state-README.md` and `cp` it in
- Fix: reset rerun now triggers digest without `--force` so `seen_items` are saved
  as the new baseline (force skips `save_seen_records`)
- Fix: ci-state README now persisted on every save in both `digest.yml` and `reset.yml`
- Prompt: one bullet per change (not comma-separated); explicit backtick rule for
  `--flags`, `/commands`, identifiers; no-prose directive; grouping instruction for
  large item counts

---

## v0.5.0

### Bug fix — GitHub Actions no longer double-commits to main

The guard in `push_github_pages` that skips git operations when running in GitHub Actions was checking `DIGEST_TRIGGER == "github_actions"`, but the workflow sets it to `"github_actions_manual"` or `"github_actions_scheduled"`. The check now uses `startswith("github_actions")` so it matches all GHA trigger variants. Previously this caused the app to run a spurious `git commit + push` to the main branch mid-workflow, which could corrupt `seen_items.json` state and cause every cloud run to reprocess the same items.

### New — `reset` subcommand

Clear dedup cache, digest history, or both without manual file editing.

```bash
# clear everything (cache + history)
python3 -m ai_digest reset

# clear only seen_items.json (next run reprocesses last 7 days)
python3 -m ai_digest reset --seen
make reset

# clear only digest history (digests.json + index.html)
python3 -m ai_digest reset --history

# clear everything
make reset-all
```

### New — Reset Digest State GitHub Actions workflow

`reset.yml` is a manual `workflow_dispatch` workflow with two inputs:

| Input | Options |
|---|---|
| `what` | `all` / `seen_only` / `history_only` |
| `rerun` | `true` — trigger a fresh digest immediately after reset |

Resets the `ci-state` branch directly. Use `rerun: true` + `what: all` to clear duplicate digest entries and re-seed the hosted page cleanly.

### Docs

- `CLOUD_MODE.md` — added Reset Digest State section; corrected stale note about "GitHub Actions cache" (state is stored in the `ci-state` branch)
- `README.md` — added `reset` / `reset-all` commands and `--seen` / `--history` flags; updated file reference to include `reset.yml`
- `CHANGELOG.md` — added (this file)

---

## v0.4.3

- Release maintenance and workflow fixes

## v0.4.2

- ci-state branch for seen_items persistence across GitHub Actions runs
- Trigger labels in digest metadata
- `--force` flag and force indicator in HTML output

## v0.4.1

- Scheduling and trigger improvements

## v0.4.0

- Normalize markdown rendering — headings, bullets, slash-commands
