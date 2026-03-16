"""Prompt constants."""

DEFAULT_PROMPT = (
    "Write ultra-compact markdown for developers. "
    "No prose. No intro. No outro. No version numbers. "

    "INCLUDE ONLY: new features, flags, commands, API changes, and deprecations in developer tools and SDKs. "

    "EXCLUDE entirely — do not mention at all: "
    "policy news, legal news, company announcements, and model benchmark comparisons. "
    "Also exclude: documentation fixes, typo fixes, test changes, minor refactors, "
    "alpha/nightly/dev releases unless a major feature is present. "

    "FORMAT RULES — follow exactly: "
    "Use ## only for category headings: ## Tools, ## SDKs, ## CLI, ## BREAKING. "
    "Do NOT use ## headings for individual tool names. "
    "One bullet per tool. Start each bullet: **ToolName**: then comma-separated changes. "
    "Backtick all --flags, /commands, and identifiers. "
    "Each change phrase: 2–5 words. At most 6 changes per tool — pick the most impactful. "
    "## BREAKING for real breaking changes only."
)
