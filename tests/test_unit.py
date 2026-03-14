"""
Unit tests for ai-digest core functions.

Uses pytest + unittest.mock — no external deps, no LLM calls, no network.
"""

import json
import sys
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

# Make sure parent dir is on path
sys.path.insert(0, str(Path(__file__).parent.parent))
import digest


# ── Fixtures ───────────────────────────────────────────────────────────────

@pytest.fixture
def tmp_config(tmp_path):
    return tmp_path / "config.yaml"

@pytest.fixture
def tmp_seen(tmp_path):
    return tmp_path / "seen_items.json"

def _entry(id="item1", title="Title", link="http://ex.com/1", summary="<p>Sum</p>", days_ago=1):
    """Build a mock feedparser entry."""
    pub = (datetime.now(timezone.utc) - timedelta(days=days_ago)).timetuple()
    return {"id": id, "title": title, "link": link, "summary": summary, "published_parsed": pub}

def _mock_feed(entries):
    f = MagicMock()
    f.entries = entries
    f.bozo = False
    return f


# ── load_seen() ────────────────────────────────────────────────────────────

class TestLoadSeen:
    def test_missing_file_returns_empty_set(self, tmp_seen):
        with patch.object(digest, "SEEN_FILE", tmp_seen):
            assert digest.load_seen() == set()

    def test_empty_json_array(self, tmp_seen):
        tmp_seen.write_text("[]")
        with patch.object(digest, "SEEN_FILE", tmp_seen):
            assert digest.load_seen() == set()

    def test_valid_json(self, tmp_seen):
        tmp_seen.write_text(json.dumps(["a", "b", "c"]))
        with patch.object(digest, "SEEN_FILE", tmp_seen):
            assert digest.load_seen() == {"a", "b", "c"}

    def test_duplicates_collapsed_into_set(self, tmp_seen):
        tmp_seen.write_text(json.dumps(["x", "x", "y"]))
        with patch.object(digest, "SEEN_FILE", tmp_seen):
            assert digest.load_seen() == {"x", "y"}


# ── save_seen() ────────────────────────────────────────────────────────────

class TestSaveSeen:
    def test_empty_set_writes_empty_list(self, tmp_seen):
        with patch.object(digest, "SEEN_FILE", tmp_seen):
            digest.save_seen(set())
        assert json.loads(tmp_seen.read_text()) == []

    def test_items_saved_sorted(self, tmp_seen):
        with patch.object(digest, "SEEN_FILE", tmp_seen):
            digest.save_seen({"z", "a", "m"})
        assert json.loads(tmp_seen.read_text()) == ["a", "m", "z"]

    def test_limits_to_2000_items(self, tmp_seen):
        items = {f"id_{i:04d}" for i in range(2500)}
        with patch.object(digest, "SEEN_FILE", tmp_seen):
            digest.save_seen(items)
        data = json.loads(tmp_seen.read_text())
        assert len(data) == 2000
        assert data[0] == "id_0500"   # sorted, last 2000

    def test_overwrites_existing_file(self, tmp_seen):
        tmp_seen.write_text(json.dumps(["old"]))
        with patch.object(digest, "SEEN_FILE", tmp_seen):
            digest.save_seen({"new1", "new2"})
        data = json.loads(tmp_seen.read_text())
        assert "old" not in data


# ── strip_html() ───────────────────────────────────────────────────────────

class TestStripHtml:
    def test_removes_tags(self):
        assert digest.strip_html("<p>Hello <b>World</b></p>") == "Hello World"

    def test_empty_string(self):
        assert digest.strip_html("") == ""

    def test_none_input(self):
        assert digest.strip_html(None) == ""

    def test_decodes_html_entities(self):
        # &lt;hot&gt; decodes to <hot> which is then stripped as a tag — correct behavior
        assert digest.strip_html("Fish &amp; Chips &lt;hot&gt;") == "Fish & Chips"
        # Plain ampersand entity decodes correctly
        assert digest.strip_html("A &amp; B") == "A & B"

    def test_strips_surrounding_whitespace(self):
        assert digest.strip_html("  <p>Text</p>  ") == "Text"


# ── load_config() ──────────────────────────────────────────────────────────

class TestLoadConfig:
    def test_missing_file_returns_empty_dict(self, tmp_config):
        with patch.object(digest, "CONFIG_FILE", tmp_config):
            assert digest.load_config() == {}

    def test_empty_yaml_returns_empty_dict(self, tmp_config):
        tmp_config.write_text("")
        with patch.object(digest, "CONFIG_FILE", tmp_config):
            assert digest.load_config() == {}

    def test_valid_yaml_loaded(self, tmp_config):
        data = {"output": "terminal", "include_defaults": True}
        tmp_config.write_text(yaml.dump(data))
        with patch.object(digest, "CONFIG_FILE", tmp_config):
            assert digest.load_config() == data

    def test_partial_config(self, tmp_config):
        tmp_config.write_text("output: github_pages\n")
        with patch.object(digest, "CONFIG_FILE", tmp_config):
            assert digest.load_config()["output"] == "github_pages"


# ── fetch_new_items() ──────────────────────────────────────────────────────

class TestFetchNewItems:
    def test_returns_new_item(self):
        feeds = [("Src", "http://ex.com/feed")]
        with patch("digest.feedparser.parse", return_value=_mock_feed([_entry()])):
            result = digest.fetch_new_items(feeds, set())
        assert len(result) == 1
        assert result[0]["source"] == "Src"
        assert result[0]["summary"] == "Sum"   # HTML stripped

    def test_deduplicates_seen_items(self):
        feeds = [("Src", "http://ex.com/feed")]
        with patch("digest.feedparser.parse", return_value=_mock_feed([_entry(id="item1")])):
            result = digest.fetch_new_items(feeds, {"item1"})
        assert result == []

    def test_excludes_old_items(self):
        feeds = [("Src", "http://ex.com/feed")]
        with patch("digest.feedparser.parse", return_value=_mock_feed([_entry(days_ago=10)])):
            result = digest.fetch_new_items(feeds, set())
        assert result == []

    def test_skips_entry_with_no_id_or_link(self):
        entry = {"title": "No ID", "summary": "x", "published_parsed": _entry()["published_parsed"]}
        feeds = [("Src", "http://ex.com/feed")]
        with patch("digest.feedparser.parse", return_value=_mock_feed([entry])):
            result = digest.fetch_new_items(feeds, set())
        assert result == []

    def test_uses_link_as_fallback_id(self):
        entry = {**_entry(), "id": None, "link": "http://fallback.com"}
        # feedparser entries return None for missing keys sometimes
        entry.pop("id")
        feeds = [("Src", "http://ex.com/feed")]
        with patch("digest.feedparser.parse", return_value=_mock_feed([entry])):
            result = digest.fetch_new_items(feeds, set())
        assert len(result) == 1
        assert result[0]["id"] == "http://fallback.com"

    def test_bad_feed_does_not_stop_others(self):
        feeds = [("Bad", "http://bad.com/feed"), ("Good", "http://good.com/feed")]

        def side_effect(url, **kw):
            if "bad" in url:
                raise ConnectionError("unreachable")
            return _mock_feed([_entry()])

        with patch("digest.feedparser.parse", side_effect=side_effect):
            result = digest.fetch_new_items(feeds, set())
        assert len(result) == 1

    def test_truncates_summary_to_500_chars(self):
        entry = _entry(summary="x" * 1000)
        feeds = [("Src", "http://ex.com/feed")]
        with patch("digest.feedparser.parse", return_value=_mock_feed([entry])):
            result = digest.fetch_new_items(feeds, set())
        assert len(result[0]["summary"]) == 500

    def test_missing_optional_fields_do_not_crash(self):
        entry = {"id": "min", "published_parsed": _entry()["published_parsed"]}
        feeds = [("Src", "http://ex.com/feed")]
        with patch("digest.feedparser.parse", return_value=_mock_feed([entry])):
            result = digest.fetch_new_items(feeds, set())
        assert result[0]["title"] == ""
        assert result[0]["link"] == ""
        assert result[0]["summary"] == ""


# ── summarize() ────────────────────────────────────────────────────────────

class TestSummarize:
    ITEMS = [{"source": "S", "title": "T", "link": "http://x.com", "summary": "Sum"}]

    def _mock_run(self, stdout="output", returncode=0):
        m = MagicMock()
        m.returncode = returncode
        m.stdout = stdout
        m.stderr = "err"
        return m

    def test_calls_claude_by_default(self):
        with patch("digest.subprocess.run", return_value=self._mock_run()) as mock:
            digest.summarize(self.ITEMS, "prompt")
        cmd = mock.call_args[0][0]
        assert cmd[0] == "claude"

    def test_returns_stripped_stdout(self):
        with patch("digest.subprocess.run", return_value=self._mock_run(stdout="  result  \n")):
            assert digest.summarize(self.ITEMS, "p") == "result"

    def test_returns_error_on_nonzero_exit(self):
        with patch("digest.subprocess.run", return_value=self._mock_run(returncode=1)):
            result = digest.summarize(self.ITEMS, "p")
        assert "error" in result.lower()

    def test_returns_error_when_cli_not_found(self):
        with patch("digest.subprocess.run", side_effect=FileNotFoundError):
            result = digest.summarize(self.ITEMS, "p")
        assert "not found" in result

    def test_uses_gemini_backend(self):
        with patch("digest.subprocess.run", return_value=self._mock_run()) as mock:
            digest.summarize(self.ITEMS, "p", backend="gemini")
        assert mock.call_args[0][0][0] == "gemini"

    def test_uses_codex_exec_subcommand(self):
        with patch("digest.subprocess.run", return_value=self._mock_run()) as mock:
            digest.summarize(self.ITEMS, "p", backend="codex")
        cmd = mock.call_args[0][0]
        assert cmd[0] == "codex"
        assert cmd[1] == "exec"

    def test_uses_ollama_with_model(self):
        with patch("digest.subprocess.run", return_value=self._mock_run()) as mock:
            digest.summarize(self.ITEMS, "p", backend="ollama", model="qwen2.5-coder:32b")
        cmd = mock.call_args[0][0]
        assert cmd[0] == "ollama"
        assert "qwen2.5-coder:32b" in cmd

    def test_falls_back_to_claude_for_unknown_backend(self):
        with patch("digest.subprocess.run", return_value=self._mock_run()) as mock:
            digest.summarize(self.ITEMS, "p", backend="unknown_tool")
        assert mock.call_args[0][0][0] == "claude"

    def test_items_appear_in_prompt(self):
        with patch("digest.subprocess.run", return_value=self._mock_run()) as mock:
            digest.summarize(self.ITEMS, "myprompt")
        prompt_arg = mock.call_args[0][0][-1]
        assert "[S]" in prompt_arg
        assert "T" in prompt_arg
        assert "http://x.com" in prompt_arg


# ── print_terminal() ───────────────────────────────────────────────────────

class TestPrintTerminal:
    def test_prints_digest_and_timestamp(self, capsys):
        digest.print_terminal("my digest", "2024-01-15 10:30 UTC")
        out = capsys.readouterr().out
        assert "my digest" in out
        assert "2024-01-15 10:30 UTC" in out
        assert "AI TOOLS DIGEST" in out


# ── push_github_pages() ────────────────────────────────────────────────────

SAMPLE_ITEMS = [{"source": "S", "title": "v1.0", "link": "http://x.com", "summary": "Fix"}]

class TestPushGithubPages:
    def _push(self, tmp_path, content="d", timestamp="ts", items=None,
              username="user", repo="repo", **kw):
        items = items or SAMPLE_ITEMS
        with patch.object(digest, "DOCS_DIR", tmp_path / "docs"):
            with patch.object(digest, "SCRIPT_DIR", tmp_path):
                with patch("digest.subprocess.run", return_value=MagicMock(stdout="", stderr="")):
                    digest.push_github_pages(content, timestamp, items, username, repo, **kw)

    def test_creates_docs_dir(self, tmp_path):
        self._push(tmp_path)
        assert (tmp_path / "docs").exists()

    def test_writes_latest_txt(self, tmp_path):
        self._push(tmp_path, content="my digest")
        content = (tmp_path / "docs" / "latest.txt").read_text()
        assert "my digest" in content

    def test_writes_index_html(self, tmp_path):
        self._push(tmp_path, username="myuser", repo="myrepo")
        content = (tmp_path / "docs" / "index.html").read_text()
        assert "myuser.github.io/myrepo" in content

    def test_writes_digests_json(self, tmp_path):
        self._push(tmp_path, content="first", timestamp="t1")
        self._push(tmp_path, content="second", timestamp="t2")
        import json as _json
        data = _json.loads((tmp_path / "docs" / "digests.json").read_text())
        assert len(data) == 2
        assert data[0]["timestamp"] == "t2"   # newest first
        assert data[1]["timestamp"] == "t1"

    def test_escapes_html_in_digest(self, tmp_path):
        self._push(tmp_path, content="<script>xss</script> & stuff")
        content = (tmp_path / "docs" / "index.html").read_text()
        assert "<script>" not in content
        assert "&lt;script&gt;" in content
        assert "&amp;" in content

    def test_trigger_label_appears_in_html(self, tmp_path):
        self._push(tmp_path, trigger="wake")
        content = (tmp_path / "docs" / "index.html").read_text()
        assert "lid open" in content

    def test_custom_base_url_used(self, tmp_path):
        self._push(tmp_path, base_url="https://procko.pro/ai-digest")
        content = (tmp_path / "docs" / "index.html").read_text()
        assert "procko.pro/ai-digest" in content
        assert "user.github.io" not in content

    def test_history_capped_at_max(self, tmp_path):
        for i in range(5):
            self._push(tmp_path, content=f"digest {i}", timestamp=f"t{i}", max_history=3)
        import json as _json
        data = _json.loads((tmp_path / "docs" / "digests.json").read_text())
        assert len(data) == 3


class TestIsSignificant:
    def test_real_release_is_significant(self):
        items = [{"title": "v2.1.76", "source": "Claude Code", "link": "", "summary": ""}]
        assert digest.is_significant(items)

    def test_alpha_only_is_not_significant(self):
        items = [{"title": "v0.115.0-alpha.12", "source": "Codex", "link": "", "summary": ""}]
        assert not digest.is_significant(items)

    def test_nightly_only_is_not_significant(self):
        items = [{"title": "v0.35.0-nightly.20260314", "source": "Gemini", "link": "", "summary": ""}]
        assert not digest.is_significant(items)

    def test_mix_of_noise_and_real_is_significant(self):
        items = [
            {"title": "v0.115.0-alpha.12", "source": "Codex", "link": "", "summary": ""},
            {"title": "v2.1.76", "source": "Claude Code", "link": "", "summary": ""},
        ]
        assert digest.is_significant(items)
