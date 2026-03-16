"""Static configuration values."""

from pathlib import Path

from ai_digest.paths import default_log_file

SCRIPT_DIR = Path(__file__).resolve().parent.parent
SEEN_FILE = SCRIPT_DIR / "seen_items.json"
CONFIG_FILE = SCRIPT_DIR / "config.yaml"
DOCS_DIR = SCRIPT_DIR / "docs"
LAST_FETCH_FILE = SCRIPT_DIR / ".last_fetch_at"
LOG_FILE = default_log_file()

LOOKBACK_DAYS = 7
FEED_TIMEOUT = 10
DEFAULT_CHECK_INTERVAL = 60 * 60
DIVIDER = "━" * 52

DEFAULT_BACKEND = "claude"
DEFAULT_MODEL = "default"

TRIGGER_LABELS = {
    "wake": "lid open",
    "manual": "manual",
    "automatic": "automatic",
    "github_actions": "GitHub Actions",
    "github_actions_scheduled": "GitHub Actions (scheduled)",
    "github_actions_manual": "GitHub Actions (manual)",
}
