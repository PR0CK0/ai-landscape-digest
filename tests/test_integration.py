"""
Integration tests for ai-digest.

Tests that hit real network or real filesystem. Requires:
  pytest -m integration

Skip network tests offline:
  pytest -m "integration and not network"
"""

import json
import socket
from unittest.mock import patch

import pytest
import yaml

from ai_digest import app as digest


# ── Helpers ───────────────────────────────────────────────────────────────

def network_available() -> bool:
    try:
        socket.create_connection(("8.8.8.8", 53), timeout=3)
        return True
    except OSError:
        return False

requires_network = pytest.mark.skipif(
    not network_available(),
    reason="Network unavailable"
)


# ── Feed reachability ──────────────────────────────────────────────────────

@pytest.mark.integration
@pytest.mark.network
class TestFeedReachability:
    @requires_network
    def test_all_default_feeds_parse(self):
        """Every default feed URL returns parseable RSS/Atom."""
        import feedparser
        failures = []
        for name, url in digest.DEFAULT_FEEDS:
            feed = feedparser.parse(url, agent="ai-digest/1.0", timeout=10)
            if not hasattr(feed, "entries"):
                failures.append(f"{name}: no entries attribute")
            elif feed.bozo and not feed.entries:
                failures.append(f"{name}: bozo error — {feed.bozo_exception}")
        assert not failures, "Feed failures:\n" + "\n".join(failures)

    @requires_network
    def test_github_release_feeds_have_entries(self):
        """GitHub release feeds (most critical) have at least one entry."""
        import feedparser
        github_feeds = [(n, u) for n, u in digest.DEFAULT_FEEDS if "github.com" in u]
        for name, url in github_feeds:
            feed = feedparser.parse(url, agent="ai-digest/1.0", timeout=10)
            assert len(feed.entries) > 0, f"{name} has no entries"

    @requires_network
    def test_fetch_new_items_returns_something_with_empty_seen(self):
        """With an empty seen set, at least one item should come back."""
        items = digest.fetch_new_items(list(digest.DEFAULT_FEEDS), seen=set())
        # Tools release frequently — there should always be recent entries
        assert len(items) > 0, "No items returned — check feeds or lookback window"


# ── JSON round-trip ────────────────────────────────────────────────────────

@pytest.mark.integration
class TestSeenRoundTrip:
    def test_write_read_cycle(self, tmp_path):
        f = tmp_path / "seen.json"
        ids = {"https://github.com/a/b/releases/tag/v1.0", "tag:github.com,2008:x/y"}
        with patch.object(digest, "SEEN_FILE", f):
            digest.save_seen(ids)
            loaded = digest.load_seen()
        assert loaded == ids

    def test_multiple_cycles_preserve_data(self, tmp_path):
        f = tmp_path / "seen.json"
        sets = [{"id1", "id2"}, {"id1", "id2", "id3"}, {"id1", "id2", "id3", "id4"}]
        for s in sets:
            with patch.object(digest, "SEEN_FILE", f):
                digest.save_seen(s)
                assert digest.load_seen() == s

    def test_unicode_ids_preserved(self, tmp_path):
        f = tmp_path / "seen.json"
        ids = {"tag:中文", "emoji:🚀", "korean:한국어"}
        with patch.object(digest, "SEEN_FILE", f):
            digest.save_seen(ids)
            assert digest.load_seen() == ids


# ── Config round-trip ──────────────────────────────────────────────────────

@pytest.mark.integration
class TestConfigRoundTrip:
    def test_custom_feeds_preserved(self, tmp_path):
        f = tmp_path / "config.yaml"
        data = {
            "output": "terminal",
            "include_defaults": False,
            "custom_feeds": [
                {"name": "HN AI", "url": "https://hnrss.org/newest?q=llm"},
            ],
        }
        f.write_text(yaml.dump(data))
        with patch.object(digest, "CONFIG_FILE", f):
            loaded = digest.load_config()
        assert loaded["custom_feeds"][0]["name"] == "HN AI"
        assert loaded["include_defaults"] is False

    def test_github_pages_config(self, tmp_path):
        f = tmp_path / "config.yaml"
        data = {
            "output": "github_pages",
            "github_pages": {"username": "example-user", "repo": "ai-digest", "base_url": "https://example.com/ai-digest"},
        }
        f.write_text(yaml.dump(data))
        with patch.object(digest, "CONFIG_FILE", f):
            loaded = digest.load_config()
        assert loaded["github_pages"]["username"] == "example-user"
        assert loaded["github_pages"]["base_url"] == "https://example.com/ai-digest"

    def test_backend_and_model_config(self, tmp_path):
        f = tmp_path / "config.yaml"
        data = {"backend": "ollama", "model": "qwen2.5-coder:32b"}
        f.write_text(yaml.dump(data))
        with patch.object(digest, "CONFIG_FILE", f):
            loaded = digest.load_config()
        assert loaded["backend"] == "ollama"
        assert loaded["model"] == "qwen2.5-coder:32b"
