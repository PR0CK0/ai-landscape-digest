#!/bin/bash
# Triggered by sleepwatcher on lid open.
# Install: make setup
# Manual test: make test

sleep 5  # wait for network

DIGEST_SCRIPT="/Users/prockot/Library/CloudStorage/OneDrive-Personal/work_new/code/ai-digest/digest.py"

DIGEST_TRIGGER=wake python3 "$DIGEST_SCRIPT" 2>/dev/null
