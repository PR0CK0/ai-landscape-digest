#!/bin/bash
# Triggered by sleepwatcher on lid open.
# Install: make setup
# Manual test: make test

sleep 5  # wait for network

DIGEST_SCRIPT="/Users/prockot/Library/CloudStorage/OneDrive-Personal/work_new/code/ai-digest/fetch_feeds.py"

ITEMS=$(python3 "$DIGEST_SCRIPT" 2>/dev/null)

if [ -z "$ITEMS" ]; then
    exit 0
fi

PROMPT="$(printf 'Terse AI tools digest for a developer building tooling around Claude Code, Codex CLI, Gemini CLI, and Aider. Plain text only, no markdown, grouped by tool, one line per release (version + key change), max 20 lines, prefix BREAKING: if anything could break existing integrations.\n\nNEW RELEASES:\n\n%s' "$ITEMS")"

echo ""
echo "━━━ AI TOOLS DIGEST ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
claude -p "$PROMPT"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
