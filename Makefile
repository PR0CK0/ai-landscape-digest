.PHONY: install setup test run reset help

SCRIPT_DIR := $(shell pwd)
WAKEUP := $(HOME)/.wakeup

help:
	@echo "ai-digest — AI tools release tracker"
	@echo ""
	@echo "  make install   install Python deps"
	@echo "  make setup     install deps + sleepwatcher + wakeup script"
	@echo "  make test      run full digest pipeline right now"
	@echo "  make run       fetch feeds only (no summarization)"
	@echo "  make reset     clear seen items (next run shows everything)"

install:
	pip3 install -r requirements.txt

setup: install
	@echo "Installing sleepwatcher..."
	brew install sleepwatcher
	brew services start sleepwatcher
	@echo "Writing ~/.wakeup..."
	@sed 's|DIGEST_SCRIPT=".*"|DIGEST_SCRIPT="$(SCRIPT_DIR)/fetch_feeds.py"|' wakeup.sh > $(WAKEUP)
	chmod 700 $(WAKEUP)
	@echo ""
	@echo "Done. Close and reopen your lid to test."
	@echo "Or run: make test"

test:
	@ITEMS=$$(python3 fetch_feeds.py); \
	if [ -z "$$ITEMS" ]; then \
		echo "Nothing new since last run. Run 'make reset' to force output."; \
	else \
		PROMPT=$$(printf 'Terse AI tools digest for a developer building tooling around Claude Code, Codex CLI, Gemini CLI, and Aider. Plain text only, no markdown, grouped by tool, one line per release (version + key change), max 20 lines, prefix BREAKING: if anything could break existing integrations.\n\nNEW RELEASES:\n\n%s' "$$ITEMS"); \
		echo ""; \
		echo "━━━ AI TOOLS DIGEST ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"; \
		claude -p "$$PROMPT"; \
		echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"; \
		echo ""; \
	fi

run:
	python3 fetch_feeds.py

reset:
	echo "[]" > seen_items.json
	@echo "Seen items cleared. Next run will show last 7 days of releases."
