"""Application settings loading."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

from ai_digest.constants import (
    CONFIG_FILE,
    DEFAULT_BACKEND,
    DEFAULT_CHECK_INTERVAL,
    DEFAULT_MODEL,
)
from ai_digest.feeds import DEFAULT_FEEDS
from ai_digest.prompts import DEFAULT_PROMPT


@dataclass
class AppConfig:
    backend: str = DEFAULT_BACKEND
    model: str = DEFAULT_MODEL
    output: str = "terminal"
    html_output: bool = True
    prompt: str = DEFAULT_PROMPT
    verbose: bool = False
    include_defaults: bool = True
    custom_feeds: list = field(default_factory=list)
    github_pages: dict = field(default_factory=dict)
    check_interval: int = DEFAULT_CHECK_INTERVAL
    seen_ttl_days: int = 30

    @property
    def feeds(self) -> list:
        feeds = list(DEFAULT_FEEDS) if self.include_defaults else []
        for feed in self.custom_feeds:
            feeds.append((feed["name"], feed["url"]))
        return feeds


def load_raw_config(config_path: Optional[Path] = None) -> dict:
    path = Path(config_path) if config_path else CONFIG_FILE
    if not path.exists():
        return {}
    with open(path) as handle:
        return yaml.safe_load(handle) or {}


def load_app_config(config_path: Optional[Path] = None) -> AppConfig:
    raw = load_raw_config(config_path)
    return build_app_config(raw)


def build_app_config(raw: dict) -> AppConfig:
    return AppConfig(
        backend=raw.get("backend", DEFAULT_BACKEND),
        model=raw.get("model", DEFAULT_MODEL),
        output=raw.get("output", "terminal"),
        html_output=raw.get("html_output", True),
        prompt=raw.get("prompt", DEFAULT_PROMPT),
        verbose=raw.get("verbose", False),
        include_defaults=raw.get("include_defaults", True),
        custom_feeds=raw.get("custom_feeds", []),
        github_pages=raw.get("github_pages", {}),
        check_interval=int(raw.get("check_interval", DEFAULT_CHECK_INTERVAL)),
        seen_ttl_days=int(raw.get("seen_ttl_days", 30)),
    )
