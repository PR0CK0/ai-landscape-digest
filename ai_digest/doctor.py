"""Environment diagnostics."""

import platform
import shutil
import sys
from pathlib import Path

from ai_digest.paths import default_log_file


def _status(label: str, ok: bool, detail: str) -> str:
    prefix = "OK" if ok else "WARN"
    return f"{prefix:<4} {label:<18} {detail}"


def doctor_report(config_override=None) -> str:
    lines = []
    system = platform.system()

    if config_override:
        root = Path(config_override).resolve().parent
        config_file = Path(config_override).resolve()
    else:
        from ai_digest.constants import SCRIPT_DIR
        root = SCRIPT_DIR
        config_file = root / "config.yaml"
    seen_file = root / "seen_items.json"
    docs_dir = root / "docs"
    log_file = default_log_file()

    lines.append(_status("platform", True, f"{system} / Python {sys.version.split()[0]}"))
    lines.append(_status("config", config_file.exists(), str(config_file)))
    lines.append(_status("seen-state", seen_file.exists(), str(seen_file)))
    lines.append(_status("docs-dir", docs_dir.exists(), str(docs_dir)))
    lines.append(_status("log-file", log_file.parent.exists(), str(log_file)))

    for tool in ["claude", "gemini", "codex", "ollama"]:
        path = shutil.which(tool)
        lines.append(_status(f"cli:{tool}", path is not None, path or "not found"))

    if system == "Darwin":
        lines.append(_status("brew", shutil.which("brew") is not None, shutil.which("brew") or "not found"))
        lines.append(_status("osascript", shutil.which("osascript") is not None, shutil.which("osascript") or "not found"))
        lines.append(_status("sleepwatcher", shutil.which("sleepwatcher") is not None, shutil.which("sleepwatcher") or "not found"))
        wakeup = Path.home() / ".wakeup"
        lines.append(_status("wakeup-hook", wakeup.exists(), str(wakeup)))
        plist = Path.home() / "Library" / "LaunchAgents" / "com.ai-digest.plist"
        lines.append(_status("launchd-timer", plist.exists(), str(plist)))
    elif system == "Linux":
        lines.append(_status("systemctl", shutil.which("systemctl") is not None, shutil.which("systemctl") or "not found"))
    elif system == "Windows":
        lines.append(_status("schtasks", shutil.which("schtasks") is not None, shutil.which("schtasks") or "not found"))

    return "\n".join(lines)
