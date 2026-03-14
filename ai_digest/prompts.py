"""Prompt constants."""

DEFAULT_PROMPT = (
    "Write ultra-compact markdown for developers. "
    "No version numbers. No intro. No outro. "
    "Group by tool or source with short headings. "
    "One bullet per tool. If a tool has multiple changes, list them comma-separated on that one line — do not use separate bullets per change. "
    "Each bullet: tool name then comma-separated changes, 2–8 words total. "
    "Use at most 10 bullets total. "
    "Add a BREAKING section only for real breakage."
)
