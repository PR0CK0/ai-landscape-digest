"""Prompt constants."""

DEFAULT_PROMPT = (
    "Write ultra-compact markdown for developers. "
    "No version numbers. No intro. No outro. "
    "Use ## for each tool or source heading. Use - for each bullet. No other heading levels. "
    "One bullet per heading. If a tool has multiple changes, list them comma-separated on that one line — do not use separate bullets per change. "
    "Each bullet: just the changes, no tool name prefix, 2–8 words total. "
    "Use at most 10 bullets total. "
    "Add a BREAKING section only for real breakage."
)
