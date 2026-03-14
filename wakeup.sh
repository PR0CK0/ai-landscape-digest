#!/bin/bash
# Triggered by sleepwatcher on lid open.
# Generic example hook. `python -m ai_digest install-trigger` writes a concrete
# ~/.wakeup for the current machine and Python environment, and also installs a
# launchd timer for periodic background runs.

PYTHON_BIN="${AI_DIGEST_PYTHON_BIN:-python3}"
LOG_FILE="${AI_DIGEST_LOG_FILE:-$HOME/.local/state/ai-digest/ai-digest.log}"
NETWORK_TEST_URL="https://www.apple.com/library/test/success.html"
if [ -n "${AI_DIGEST_PYTHONPATH:-}" ]; then
  export PYTHONPATH="${AI_DIGEST_PYTHONPATH}"
fi
mkdir -p "$(dirname "$LOG_FILE")"

{
  echo ""
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] wake trigger start"
  echo "PATH=$PATH"

python3 -c '
import sys
import urllib.request

try:
    with urllib.request.urlopen("'"$NETWORK_TEST_URL"'", timeout=3) as response:
        sys.exit(0 if response.status < 400 else 1)
except Exception:
    sys.exit(1)
' >/dev/null 2>&1

if [ $? -ne 0 ]; then
  osascript -e 'display notification "Waiting for internet connection..." with title "AI Landscape Digest"' >/dev/null 2>&1
  until python3 -c '
import sys
import urllib.request

try:
    with urllib.request.urlopen("'"$NETWORK_TEST_URL"'", timeout=3) as response:
        sys.exit(0 if response.status < 400 else 1)
except Exception:
    sys.exit(1)
' >/dev/null 2>&1; do
  sleep 1
  done
fi

DIGEST_TRIGGER=wake "$PYTHON_BIN" -m ai_digest --trigger wake
status=$?
echo "[$(date '+%Y-%m-%d %H:%M:%S')] wake trigger exit status=$status"
exit $status
} >>"$LOG_FILE" 2>&1
