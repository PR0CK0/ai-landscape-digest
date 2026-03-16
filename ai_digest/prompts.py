"""Prompt constants."""

DEFAULT_PROMPT = (
    "Write ultra-compact markdown for developers. "
    "No prose. No version numbers. No intro. No outro. "
    "Use ## headings for each tool or category. Use - for each bullet. No other heading levels. "
    "One bullet per change — do not combine multiple changes onto one line. "
    "Each bullet: 2–8 words, active voice, no tool name prefix. "
    "Backtick all --flags, /commands, function names, and identifiers. "
    "For large item counts, group related tools under a ## category heading "
    "and use **bold** for the tool name at the start of each bullet. "
    "Skip alpha, nightly, and dev-only releases unless the change is significant. "
    "Add a ## BREAKING section only for real breaking changes."
)
