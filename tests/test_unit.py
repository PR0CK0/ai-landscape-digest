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

from ai_digest import app as digest
from ai_digest import doctor as doctor_mod
from ai_digest import installers


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
        with patch("ai_digest.app.feedparser.parse", return_value=_mock_feed([_entry()])):
            result = digest.fetch_new_items(feeds, set())
        assert len(result) == 1
        assert result[0]["source"] == "Src"
        assert result[0]["summary"] == "Sum"   # HTML stripped

    def test_deduplicates_seen_items(self):
        feeds = [("Src", "http://ex.com/feed")]
        with patch("ai_digest.app.feedparser.parse", return_value=_mock_feed([_entry(id="item1")])):
            result = digest.fetch_new_items(feeds, {"item1"})
        assert result == []

    def test_excludes_old_items(self):
        feeds = [("Src", "http://ex.com/feed")]
        with patch("ai_digest.app.feedparser.parse", return_value=_mock_feed([_entry(days_ago=10)])):
            result = digest.fetch_new_items(feeds, set())
        assert result == []

    def test_skips_entry_with_no_id_or_link(self):
        entry = {"title": "No ID", "summary": "x", "published_parsed": _entry()["published_parsed"]}
        feeds = [("Src", "http://ex.com/feed")]
        with patch("ai_digest.app.feedparser.parse", return_value=_mock_feed([entry])):
            result = digest.fetch_new_items(feeds, set())
        assert result == []

    def test_uses_link_as_fallback_id(self):
        entry = {**_entry(), "id": None, "link": "http://fallback.com"}
        # feedparser entries return None for missing keys sometimes
        entry.pop("id")
        feeds = [("Src", "http://ex.com/feed")]
        with patch("ai_digest.app.feedparser.parse", return_value=_mock_feed([entry])):
            result = digest.fetch_new_items(feeds, set())
        assert len(result) == 1
        assert result[0]["id"] == "http://fallback.com"

    def test_bad_feed_does_not_stop_others(self):
        feeds = [("Bad", "http://bad.com/feed"), ("Good", "http://good.com/feed")]

        def side_effect(url, **kw):
            if "bad" in url:
                raise ConnectionError("unreachable")
            return _mock_feed([_entry()])

        with patch("ai_digest.app.feedparser.parse", side_effect=side_effect):
            result = digest.fetch_new_items(feeds, set())
        assert len(result) == 1

    def test_truncates_summary_to_500_chars(self):
        entry = _entry(summary="x" * 1000)
        feeds = [("Src", "http://ex.com/feed")]
        with patch("ai_digest.app.feedparser.parse", return_value=_mock_feed([entry])):
            result = digest.fetch_new_items(feeds, set())
        assert len(result[0]["summary"]) == 500

    def test_missing_optional_fields_do_not_crash(self):
        entry = {"id": "min", "published_parsed": _entry()["published_parsed"]}
        feeds = [("Src", "http://ex.com/feed")]
        with patch("ai_digest.app.feedparser.parse", return_value=_mock_feed([entry])):
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
        with patch("ai_digest.app.subprocess.run", return_value=self._mock_run()) as mock:
            digest.summarize(self.ITEMS, "prompt")
        cmd = mock.call_args[0][0]
        assert cmd[0] == "claude"

    def test_returns_stripped_stdout(self):
        with patch("ai_digest.app.subprocess.run", return_value=self._mock_run(stdout="  result  \n")):
            assert digest.summarize(self.ITEMS, "p") == "result"

    def test_returns_error_on_nonzero_exit(self):
        with patch("ai_digest.app.subprocess.run", return_value=self._mock_run(returncode=1)):
            result = digest.summarize(self.ITEMS, "p")
        assert "error" in result.lower()

    def test_returns_error_when_cli_not_found(self):
        with patch("ai_digest.app.subprocess.run", side_effect=FileNotFoundError):
            result = digest.summarize(self.ITEMS, "p")
        assert "not found" in result

    def test_uses_gemini_backend(self):
        with patch("ai_digest.app.subprocess.run", return_value=self._mock_run()) as mock:
            digest.summarize(self.ITEMS, "p", backend="gemini")
        assert mock.call_args[0][0][0] == "gemini"

    def test_uses_codex_exec_subcommand(self):
        with patch("ai_digest.app.subprocess.run", return_value=self._mock_run()) as mock:
            digest.summarize(self.ITEMS, "p", backend="codex")
        cmd = mock.call_args[0][0]
        assert cmd[0] == "codex"
        assert cmd[1] == "exec"

    def test_uses_ollama_with_model(self):
        with patch("ai_digest.app.subprocess.run", return_value=self._mock_run()) as mock:
            digest.summarize(self.ITEMS, "p", backend="ollama", model="qwen2.5-coder:32b")
        cmd = mock.call_args[0][0]
        assert cmd[0] == "ollama"
        assert "qwen2.5-coder:32b" in cmd

    def test_ollama_default_uses_installed_model(self):
        with patch("ai_digest.app.get_ollama_default_model", return_value="mistral:latest"):
            with patch("ai_digest.app.subprocess.run", return_value=self._mock_run()) as mock:
                digest.summarize(self.ITEMS, "p", backend="ollama")
        cmd = mock.call_args[0][0]
        assert cmd[:3] == ["ollama", "run", "mistral:latest"]

    def test_ollama_default_reports_missing_local_models(self):
        with patch("ai_digest.app.get_ollama_default_model", side_effect=RuntimeError("no local Ollama models found")):
            result = digest.summarize(self.ITEMS, "p", backend="ollama")
        assert "no local Ollama models found" in result

    def test_falls_back_to_claude_for_unknown_backend(self):
        with patch("ai_digest.app.subprocess.run", return_value=self._mock_run()) as mock:
            digest.summarize(self.ITEMS, "p", backend="unknown_tool")
        assert mock.call_args[0][0][0] == "claude"

    def test_items_appear_in_prompt(self):
        with patch("ai_digest.app.subprocess.run", return_value=self._mock_run()) as mock:
            digest.summarize(self.ITEMS, "myprompt")
        prompt_arg = mock.call_args[0][0][-1]
        assert "[S]" in prompt_arg
        assert "T" in prompt_arg
        assert "http://x.com" in prompt_arg


class TestGetOllamaDefaultModel:
    def _mock_run(self, stdout="", returncode=0, stderr=""):
        m = MagicMock()
        m.returncode = returncode
        m.stdout = stdout
        m.stderr = stderr
        return m

    def test_prefers_known_models_when_present(self):
        output = (
            "NAME              ID              SIZE      MODIFIED\n"
            "mistral:latest    abc             4 GB      now\n"
            "llama3            def             4 GB      now\n"
        )
        with patch("ai_digest.app.subprocess.run", return_value=self._mock_run(stdout=output)):
            assert digest.get_ollama_default_model() == "llama3"

    def test_falls_back_to_first_installed_model(self):
        output = (
            "NAME              ID              SIZE      MODIFIED\n"
            "ministral-3:3b    abc             3 GB      now\n"
            "foo               def             1 GB      now\n"
        )
        with patch("ai_digest.app.subprocess.run", return_value=self._mock_run(stdout=output)):
            assert digest.get_ollama_default_model() == "ministral-3:3b"

    def test_errors_when_no_models_installed(self):
        output = "NAME              ID              SIZE      MODIFIED\n"
        with patch("ai_digest.app.subprocess.run", return_value=self._mock_run(stdout=output)):
            with pytest.raises(RuntimeError, match="no local Ollama models found"):
                digest.get_ollama_default_model()


class TestWakeFetchThrottle:
    def test_missing_last_fetch_file_is_due(self, tmp_path):
        with patch.object(digest, "LAST_FETCH_FILE", tmp_path / ".last_fetch_at"):
            assert digest.wake_fetch_due(now=3600)

    def test_recent_last_fetch_is_not_due(self, tmp_path):
        path = tmp_path / ".last_fetch_at"
        path.write_text("3500")
        with patch.object(digest, "LAST_FETCH_FILE", path):
            assert not digest.wake_fetch_due(now=3600)

    def test_old_last_fetch_is_due(self, tmp_path):
        path = tmp_path / ".last_fetch_at"
        path.write_text("0")
        with patch.object(digest, "LAST_FETCH_FILE", path):
            assert digest.wake_fetch_due(now=digest.DEFAULT_CHECK_INTERVAL)

    def test_invalid_last_fetch_file_is_treated_as_missing(self, tmp_path):
        path = tmp_path / ".last_fetch_at"
        path.write_text("not-a-timestamp")
        with patch.object(digest, "LAST_FETCH_FILE", path):
            assert digest.wake_fetch_due(now=3600)

    def test_custom_interval_is_respected(self, tmp_path):
        path = tmp_path / ".last_fetch_at"
        path.write_text("3500")
        with patch.object(digest, "LAST_FETCH_FILE", path):
            assert digest.wake_fetch_due(min_interval_seconds=60, now=3600)

    def test_main_ignores_recent_check_when_throttle_disabled(self):
        with patch.dict("os.environ", {"DIGEST_TRIGGER": "wake"}, clear=False):
            with patch("ai_digest.app.load_config", return_value={"check_interval": 0}):
                with patch("ai_digest.app.wake_fetch_due") as wake_fetch_due:
                    with patch("ai_digest.app.fetch_new_items", return_value=[]):
                        with patch("ai_digest.app.notify"):
                            with patch("ai_digest.app.save_last_fetch_at"):
                                with patch("ai_digest.app.load_seen_records", return_value={}):
                                    with pytest.raises(SystemExit):
                                        digest.main()
        wake_fetch_due.assert_not_called()

    def test_main_skips_wake_fetch_if_recent(self):
        with patch.dict("os.environ", {"DIGEST_TRIGGER": "wake"}, clear=False):
            with patch("ai_digest.app.load_config", return_value={}):
                with patch("ai_digest.app.wake_fetch_due", return_value=False):
                    with patch("ai_digest.app.notify") as notify:
                        with patch("ai_digest.app.fetch_new_items") as fetch_new_items:
                            with pytest.raises(SystemExit) as exc:
                                digest.main()
        fetch_new_items.assert_not_called()
        notify.assert_called_once_with(
            "AI Landscape Digest",
            "Skipped: checked for new releases within the last hour.",
            None,
            None,
        )
        assert exc.value.code == 0

    def test_main_uses_configured_skip_interval_in_notification(self):
        with patch.dict("os.environ", {"DIGEST_TRIGGER": "wake"}, clear=False):
            with patch("ai_digest.app.load_config", return_value={"check_interval": 120}):
                with patch("ai_digest.app.wake_fetch_due", return_value=False) as wake_fetch_due:
                    with patch("ai_digest.app.notify") as notify:
                        with pytest.raises(SystemExit):
                            digest.main()
        wake_fetch_due.assert_called_once_with(120)
        notify.assert_called_once_with(
            "AI Landscape Digest",
            "Skipped: checked for new releases within the last 2 minutes.",
            None,
            None,
        )


class TestFormatIntervalLabel:
    def test_formats_hours(self):
        assert digest.format_interval_label(3600) == "the last hour"

    def test_formats_plural_hours(self):
        assert digest.format_interval_label(7200) == "the last 2 hours"

    def test_formats_minutes(self):
        assert digest.format_interval_label(120) == "the last 2 minutes"

    def test_formats_seconds(self):
        assert digest.format_interval_label(45) == "the last 45 seconds"

    def test_main_records_fetch_time_for_wake_runs(self):
        with patch.dict("os.environ", {"DIGEST_TRIGGER": "wake"}, clear=False):
            with patch("ai_digest.app.load_config", return_value={}):
                with patch("ai_digest.app.wake_fetch_due", return_value=True):
                    with patch("ai_digest.app.notify"):
                        with patch("ai_digest.app.save_last_fetch_at") as save_last_fetch_at:
                            with patch("ai_digest.app.load_seen_records", return_value={}):
                                with patch("ai_digest.app.fetch_new_items", return_value=[]):
                                    with pytest.raises(SystemExit):
                                        digest.main()
        save_last_fetch_at.assert_called_once()

    def test_main_notifies_before_summarizing_for_wake_runs(self):
        with patch.dict("os.environ", {"DIGEST_TRIGGER": "wake"}, clear=False):
            with patch("ai_digest.app.load_config", return_value={"backend": "ollama", "model": "ministral-3:3b"}):
                with patch("ai_digest.app.wake_fetch_due", return_value=True):
                    with patch("ai_digest.app.notify") as notify:
                        with patch("ai_digest.app.save_last_fetch_at"):
                            with patch("ai_digest.app.load_seen_records", return_value={}):
                                with patch("ai_digest.app.fetch_new_items", return_value=[{"id": "1", "source": "S", "title": "T", "link": "", "summary": ""}]):
                                    with patch("ai_digest.app.save_seen_records"):
                                        with patch("ai_digest.app.summarize", return_value="ok"):
                                            with patch("ai_digest.app.print_terminal"):
                                                digest.main()
        assert any(
            call.args[:2] == ("AI Landscape Digest", "Summarizing with ministral-3:3b...")
            for call in notify.call_args_list
        )


# ── print_terminal() ───────────────────────────────────────────────────────

class TestPrintTerminal:
    def test_prints_digest_and_timestamp(self, capsys):
        digest.print_terminal("my digest", "2024-01-15 10:30 UTC")
        out = capsys.readouterr().out
        assert "my digest" in out
        assert "2024-01-15 10:30 UTC" in out
        assert "# AI Landscape Digest" in out


class TestCliCommands:
    def test_install_trigger_command_dispatches(self, capsys):
        with patch("ai_digest.app.install_trigger", return_value="installed") as install:
            digest.main(["install-trigger"])
        install.assert_called_once()
        assert "installed" in capsys.readouterr().out

    def test_uninstall_trigger_command_dispatches(self, capsys):
        with patch("ai_digest.app.uninstall_trigger", return_value="removed") as uninstall:
            digest.main(["uninstall-trigger"])
        uninstall.assert_called_once()
        assert "removed" in capsys.readouterr().out

    def test_doctor_command_dispatches(self, capsys):
        with patch("ai_digest.app.doctor_report", return_value="OK   platform") as doctor:
            digest.main(["doctor"])
        doctor.assert_called_once()
        assert "OK   platform" in capsys.readouterr().out


class TestPlatformHooks:
    def test_render_macos_wakeup_script_uses_explicit_launcher(self):
        script = installers.render_macos_wakeup_script(
            "/usr/bin/python3",
            "/usr/bin:/bin",
            Path("/tmp/ai-digest.log"),
            "/repo/digest.py",
            ["--trigger", "wake"],
        )
        assert 'PYTHON_BIN="/usr/bin/python3"' in script
        assert 'LOG_FILE="/tmp/ai-digest.log"' in script
        assert '"/repo/digest.py" "--trigger" "wake"' in script
        assert "AI Landscape Digest" in script

    def test_render_linux_systemd_service_contains_execstart(self):
        service = installers.render_linux_systemd_service(
            "/usr/bin/python3",
            "/usr/bin:/bin",
            Path("/tmp/ai-digest.log"),
            "/repo/digest.py",
            ["--trigger", "automatic"],
        )
        assert "ExecStart=/usr/bin/python3 /repo/digest.py --trigger automatic" in service
        assert "StandardOutput=append:/tmp/ai-digest.log" in service

    def test_render_windows_task_xml_contains_explicit_launcher(self):
        xml = installers.render_windows_task_xml(
            r"C:\Python39\python.exe",
            r"C:\repo\digest.py",
            ["--trigger", "automatic"],
            3600,
        )
        assert r"<Command>C:\Python39\python.exe</Command>" in xml
        assert '<Arguments>"C:\\repo\\digest.py" "--trigger" "automatic"</Arguments>' in xml


class TestInstallers:
    def test_install_macos_trigger_writes_wakeup(self, tmp_path):
        wakeup = tmp_path / ".wakeup"
        plist = tmp_path / "LaunchAgents" / "com.ai-digest.plist"
        log_file = tmp_path / "logs" / "ai-digest.log"
        with patch.object(installers, "MACOS_WAKEUP_FILE", wakeup):
            with patch.object(installers, "MACOS_LAUNCHD_PLIST", plist):
                with patch.object(installers, "LOG_FILE", log_file):
                    with patch("ai_digest.installers.ensure_sleepwatcher"):
                        with patch("ai_digest.installers.ensure_user_state_dir", return_value=log_file.parent):
                            with patch("ai_digest.installers.sys.executable", "/usr/bin/python3"):
                                with patch.dict("os.environ", {"PATH": "/usr/bin:/bin"}, clear=False):
                                    msg = installers.install_macos_trigger()
        assert wakeup.exists()
        assert plist.exists()
        content = wakeup.read_text()
        assert str(log_file) in content
        assert "Installed macOS wake trigger" in msg

    def test_install_linux_trigger_writes_unit_files(self, tmp_path):
        systemd_dir = tmp_path / "systemd"
        log_dir = tmp_path / "logs"
        log_file = log_dir / "ai-digest.log"
        with patch.object(installers, "LINUX_SYSTEMD_DIR", systemd_dir):
            with patch.object(installers, "LOG_FILE", log_file):
                with patch("ai_digest.installers.ensure_user_state_dir", return_value=log_dir):
                    with patch("ai_digest.installers.sys.executable", "/usr/bin/python3"):
                        with patch.dict("os.environ", {"PATH": "/usr/bin:/bin"}, clear=False):
                            with patch("ai_digest.installers.shutil.which", return_value=None):
                                msg = installers.install_linux_trigger()
        assert (systemd_dir / "ai-landscape-digest.service").exists()
        assert (systemd_dir / "ai-landscape-digest.timer").exists()
        assert "Installed Linux systemd user timer" in msg

    def test_install_windows_trigger_writes_xml(self, tmp_path):
        state_dir = tmp_path / "state"
        state_dir.mkdir()
        with patch("ai_digest.installers.ensure_user_state_dir", return_value=state_dir):
            with patch("ai_digest.installers.shutil.which", return_value=None):
                with patch("ai_digest.installers.sys.executable", r"C:\Python39\python.exe"):
                    msg = installers.install_windows_trigger()
        xml_path = state_dir / "windows-task.xml"
        assert xml_path.exists()
        assert "Installed Windows scheduled task definition" in msg
        assert "ai_digest" in xml_path.read_text(encoding="utf-16")

    def test_uninstall_linux_trigger_removes_files(self, tmp_path):
        systemd_dir = tmp_path / "systemd"
        systemd_dir.mkdir()
        service = systemd_dir / "ai-landscape-digest.service"
        timer = systemd_dir / "ai-landscape-digest.timer"
        service.write_text("x")
        timer.write_text("y")
        with patch.object(installers, "LINUX_SYSTEMD_DIR", systemd_dir):
            with patch("ai_digest.installers.shutil.which", return_value=None):
                msg = installers.uninstall_linux_trigger()
        assert not service.exists()
        assert not timer.exists()
        assert "Removed Linux trigger files" in msg

    def test_install_trigger_dispatches_by_platform(self):
        with patch("ai_digest.installers.platform.system", return_value="Linux"):
            with patch("ai_digest.installers.install_linux_trigger", return_value="linux"):
                assert installers.install_trigger() == "linux"

    def test_uninstall_trigger_dispatches_by_platform(self):
        with patch("ai_digest.installers.platform.system", return_value="Windows"):
            with patch("ai_digest.installers.uninstall_windows_trigger", return_value="windows"):
                assert installers.uninstall_trigger() == "windows"


class TestDoctor:
    def test_doctor_report_lists_tools(self):
        with patch("ai_digest.doctor.platform.system", return_value="Darwin"):
            with patch("ai_digest.doctor.shutil.which", side_effect=lambda name: f"/bin/{name}" if name in {"brew", "osascript", "claude"} else None):
                report = doctor_mod.doctor_report()
        assert "platform" in report
        assert "cli:claude" in report
        assert "brew" in report


# ── push_github_pages() ────────────────────────────────────────────────────

SAMPLE_ITEMS = [{"source": "S", "title": "v1.0", "link": "http://x.com", "summary": "Fix"}]

class TestPushGithubPages:
    def _push(self, tmp_path, content="d", timestamp="ts", items=None,
              username="user", repo="repo", **kw):
        items = items or SAMPLE_ITEMS
        with patch.object(digest, "SCRIPT_DIR", tmp_path):
            with patch.object(digest, "SEEN_FILE", tmp_path / "seen_items.json"):
                # Extract kw that are for generate_html_report
                report_kw = {k: v for k, v in kw.items() if k in ["trigger", "model", "latency_seconds", "max_history"]}
                page_url = kw.get("base_url") or f"https://{username}.github.io/{repo}"
                digest.generate_html_report(tmp_path / "docs", content, timestamp, items, page_url=page_url, **report_kw)

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
        assert '<div class="digest-markdown">' in content
        assert "<pre>" not in content

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

    def test_renders_markdown_emphasis_in_digest(self, tmp_path):
        self._push(tmp_path, content="## **Tools**\n- **OpenAI** `Responses API`")
        content = (tmp_path / "docs" / "index.html").read_text()
        assert "<h2><strong>Tools</strong></h2>" in content
        assert "<strong>OpenAI</strong>" in content
        assert "<code>Responses API</code>" in content

    def test_trigger_label_appears_in_html(self, tmp_path):
        self._push(tmp_path, trigger="wake")
        content = (tmp_path / "docs" / "index.html").read_text()
        assert "lid open" in content

    def test_model_and_latency_appear_in_html(self, tmp_path):
        self._push(tmp_path, trigger="manual", model="ministral-3:3b", latency_seconds=12.4)
        content = (tmp_path / "docs" / "index.html").read_text()
        assert "manual" in content
        assert "ministral-3:3b" in content
        assert "12s" in content

    def test_custom_base_url_used(self, tmp_path):
        self._push(tmp_path, base_url="https://example.com/ai-digest")
        content = (tmp_path / "docs" / "index.html").read_text()
        assert "example.com/ai-digest" in content
        assert "user.github.io" not in content

    def test_history_capped_at_max(self, tmp_path):
        for i in range(5):
            self._push(tmp_path, content=f"digest {i}", timestamp=f"t{i}", max_history=3)
        import json as _json
        data = _json.loads((tmp_path / "docs" / "digests.json").read_text())
        assert len(data) == 3

    def test_writes_model_and_latency_to_history(self, tmp_path):
        self._push(tmp_path, model="ministral-3:3b", latency_seconds=4.6)
        import json as _json
        data = _json.loads((tmp_path / "docs" / "digests.json").read_text())
        assert data[0]["model"] == "ministral-3:3b"
        assert data[0]["latency_seconds"] == 4.6


# ── Digest history accumulation ────────────────────────────────────────────
#
# These tests verify the behavior that was broken in CI: without docs/digests.json
# being restored before each run, every GitHub Actions execution started with an
# empty history and the HTML only ever showed one entry.  The fix (restoring
# docs/digests.json from the digest-cache branch before running) depends entirely
# on generate_html_report correctly loading a pre-existing file written by an
# earlier process — which is what these tests exercise.

PRIOR_ENTRY = {
    "timestamp": "t0",
    "trigger": "github_actions",
    "item_count": 2,
    "model": "gemini-2.5-flash",
    "latency_seconds": 10.0,
    "sources": [],
    "content": "prior digest",
}

class TestDigestHistoryAccumulation:
    def _seed(self, docs: Path, entries: list):
        """Write a digests.json to docs/ as the workflow's cache-restore step would."""
        docs.mkdir(exist_ok=True)
        (docs / "digests.json").write_text(json.dumps(entries))

    def test_accumulates_when_digests_json_pre_seeded(self, tmp_path):
        docs = tmp_path / "docs"
        self._seed(docs, [PRIOR_ENTRY])

        digest.generate_html_report(docs, "new digest", "t1", SAMPLE_ITEMS)

        data = json.loads((docs / "digests.json").read_text())
        assert len(data) == 2
        assert data[0]["timestamp"] == "t1"    # newest first
        assert data[0]["content"] == "new digest"
        assert data[1]["timestamp"] == "t0"    # prior entry preserved

    def test_fresh_run_without_prior_history(self, tmp_path):
        docs = tmp_path / "docs"
        # No digests.json on disk — first-ever run

        digest.generate_html_report(docs, "first digest", "t1", SAMPLE_ITEMS)

        data = json.loads((docs / "digests.json").read_text())
        assert len(data) == 1
        assert data[0]["content"] == "first digest"

    def test_corrupted_digests_json_treated_as_empty(self, tmp_path):
        docs = tmp_path / "docs"
        self._seed(docs, [])
        (docs / "digests.json").write_text("not valid json {{{{")

        digest.generate_html_report(docs, "new digest", "t1", SAMPLE_ITEMS)

        data = json.loads((docs / "digests.json").read_text())
        assert len(data) == 1
        assert data[0]["content"] == "new digest"

    def test_html_renders_all_accumulated_entries(self, tmp_path):
        docs = tmp_path / "docs"
        self._seed(docs, [PRIOR_ENTRY])

        digest.generate_html_report(docs, "new news", "t1", SAMPLE_ITEMS)

        html = (docs / "index.html").read_text()
        assert "new news" in html
        assert "prior digest" in html

    def test_multiple_pre_seeded_entries_all_preserved(self, tmp_path):
        docs = tmp_path / "docs"
        prior = [
            {**PRIOR_ENTRY, "timestamp": f"t{i}", "content": f"digest {i}"}
            for i in range(3)
        ]
        self._seed(docs, prior)

        digest.generate_html_report(docs, "latest", "t_new", SAMPLE_ITEMS)

        data = json.loads((docs / "digests.json").read_text())
        assert len(data) == 4
        assert data[0]["timestamp"] == "t_new"
        assert [d["timestamp"] for d in data[1:]] == ["t0", "t1", "t2"]


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
