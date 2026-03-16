.PHONY: install setup install-trigger uninstall-trigger doctor test test-unit test-integration run reset reset-all help

LOOKBACK_DAYS := 7

help:
	@echo ""
	@echo "  ai-digest — AI landscape release tracker"
	@echo ""
	@echo "  make install          install Python deps"
	@echo "  make setup            install deps + platform trigger"
	@echo "  make install-trigger  install platform trigger"
	@echo "  make uninstall-trigger remove platform trigger"
	@echo "  make doctor           inspect local environment"
	@echo "  make test             run all unit tests"
	@echo "  make test-unit        run unit tests only (fast, no network)"
	@echo "  make test-integration run integration tests (requires network)"
	@echo "  make run              run full digest right now"
	@echo "  make reset            clear seen_items dedup cache (next run shows last $(LOOKBACK_DAYS) days)"
	@echo "  make reset-all        clear seen_items + digest history + local HTML"
	@echo ""
	@echo "  Config: copy config.example.yaml → config.yaml and edit."
	@echo ""

install:
	pip install -r requirements.txt

setup: install
	@echo "→ Installing platform trigger..."
	python3 -m ai_digest install-trigger
	@if [ ! -f config.yaml ]; then \
		cp config.example.yaml config.yaml; \
		echo "→ Created config.yaml — edit it to customize feeds, model, and output."; \
	fi
	@echo ""
	@echo "Done. Close and reopen your lid to trigger, or run: make run"

install-trigger:
	python3 -m ai_digest install-trigger

uninstall-trigger:
	python3 -m ai_digest uninstall-trigger

doctor:
	python3 -m ai_digest doctor

test: test-unit

test-unit:
	pytest -m "not integration"

test-integration:
	pytest -m integration

run:
	python3 -m ai_digest

reset:
	python3 -m ai_digest reset --seen

reset-all:
	python3 -m ai_digest reset
