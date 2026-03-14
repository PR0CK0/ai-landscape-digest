.PHONY: install setup test test-unit test-integration run reset help

SCRIPT_DIR := $(shell pwd)
WAKEUP     := $(HOME)/.wakeup
LOOKBACK_DAYS := 7

help:
	@echo ""
	@echo "  ai-digest — AI tools release tracker"
	@echo ""
	@echo "  make install          install Python deps"
	@echo "  make setup            install deps + sleepwatcher + write ~/.wakeup"
	@echo "  make test             run all unit tests"
	@echo "  make test-unit        run unit tests only (fast, no network)"
	@echo "  make test-integration run integration tests (requires network)"
	@echo "  make run              run full digest right now"
	@echo "  make reset            clear seen items (next run shows last $(LOOKBACK_DAYS) days)"
	@echo ""
	@echo "  Config: copy config.example.yaml → config.yaml and edit."
	@echo ""

install:
	pip3 install -r requirements.txt

setup: install
	@echo "→ Installing sleepwatcher..."
	brew install sleepwatcher
	brew services start sleepwatcher
	@echo "→ Writing ~/.wakeup..."
	@sed 's|DIGEST_SCRIPT=".*"|DIGEST_SCRIPT="$(SCRIPT_DIR)/digest.py"|' wakeup.sh > $(WAKEUP)
	chmod 700 $(WAKEUP)
	@if [ ! -f config.yaml ]; then \
		cp config.example.yaml config.yaml; \
		echo "→ Created config.yaml — edit it to customize feeds, model, and output."; \
	fi
	@echo ""
	@echo "Done. Close and reopen your lid to trigger, or run: make run"

test: test-unit

test-unit:
	pytest -m "not integration"

test-integration:
	pytest -m integration

run:
	python3 digest.py

reset:
	echo "[]" > seen_items.json
	@echo "Cleared. Next run shows last $(LOOKBACK_DAYS) days of releases."
