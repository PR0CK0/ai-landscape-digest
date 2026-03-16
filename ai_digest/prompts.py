"""Prompt constants."""

DEFAULT_PROMPT = (
    "Write ultra-compact markdown for developers. "
    "No prose. No version numbers. No intro. No outro. "
    "Focus only on tool and SDK changes: new features, flags, commands, APIs, deprecations. "
    "Skip newsletters, blog posts, research papers, and policy or legal news entirely. "
    "Skip alpha, nightly, and dev-only releases unless the change is genuinely significant. "
    "Consolidate multiple releases of the same tool into one bullet — do not repeat the tool. "
    "Group bullets under ## category headings (e.g. ## Tools, ## SDKs, ## CLI). "
    "Start each bullet with **ToolName**: followed by comma-separated changes. "
    "Backtick all --flags, /commands, function names, and identifiers. "
    "Each individual change: 2–6 words. "
    "Add ## BREAKING only for real breaking changes."
)
