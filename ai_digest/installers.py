"""Platform-specific installer helpers."""

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ai_digest.settings import AppConfig

from ai_digest.constants import DEFAULT_CHECK_INTERVAL, LOG_FILE, SCRIPT_DIR as REPO_ROOT
from ai_digest.paths import ensure_user_state_dir

NETWORK_TEST_URL = "https://www.apple.com/library/test/success.html"

MACOS_WAKEUP_FILE = Path.home() / ".wakeup"
MACOS_LAUNCHD_PLIST = Path.home() / "Library" / "LaunchAgents" / "com.ai-digest.plist"
LINUX_SYSTEMD_DIR = Path.home() / ".config" / "systemd" / "user"
WINDOWS_TASK_NAME = "AILandscapeDigest"


def render_macos_wakeup_script(
    python_executable: str,
    python_path: str,
    log_file: Path,
    launcher: str,
    launcher_args: list,
    pythonpath_extra: str = "",
) -> str:
    quoted_python_path = python_path.replace('"', '\\"')
    pythonpath_line = ""
    if pythonpath_extra:
        pythonpath_line = f'export PYTHONPATH="{pythonpath_extra}"\n'
    launch_target = " ".join([f'"{launcher}"', *[f'"{arg}"' for arg in launcher_args]])
    return f"""#!/bin/bash
# Triggered by sleepwatcher on lid open.

PYTHON_BIN="{python_executable}"
LOG_FILE="{log_file}"
NETWORK_TEST_URL="{NETWORK_TEST_URL}"
export PATH="{quoted_python_path}"
{pythonpath_line}

{{
  echo ""
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] wake trigger start"
  echo "PATH=$PATH"

# Wait until a user is logged into the GUI console before doing anything.
# Prevents notifications from appearing on the lock/login screen.
until who | grep -q "console"; do
  sleep 2
done

python3 -c '
import sys
import urllib.request

try:
    with urllib.request.urlopen("'"$NETWORK_TEST_URL"'", timeout=3) as response:
        sys.exit(0 if response.status < 400 else 1)
except Exception:
    sys.exit(1)
' >/dev/null 2>&1

if [ $? -ne 0 ]; then
  osascript -e 'display notification "Waiting for internet connection..." with title "AI Landscape Digest"' >/dev/null 2>&1
  until python3 -c '
import sys
import urllib.request

try:
    with urllib.request.urlopen("'"$NETWORK_TEST_URL"'", timeout=3) as response:
        sys.exit(0 if response.status < 400 else 1)
except Exception:
    sys.exit(1)
' >/dev/null 2>&1; do
    sleep 1
  done
fi

DIGEST_TRIGGER=wake "$PYTHON_BIN" {launch_target}
status=$?
echo "[$(date '+%Y-%m-%d %H:%M:%S')] wake trigger exit status=$status"
exit $status
}} >>"$LOG_FILE" 2>&1
"""


def render_linux_systemd_service(
    python_executable: str,
    python_path: str,
    log_file: Path,
    launcher: str,
    launcher_args: list,
) -> str:
    exec_start = " ".join([python_executable, launcher, *launcher_args])
    return f"""[Unit]
Description=AI Landscape Digest

[Service]
Type=oneshot
Environment=PATH={python_path}
Environment=DIGEST_TRIGGER=automatic
ExecStart={exec_start}
StandardOutput=append:{log_file}
StandardError=append:{log_file}
"""


def render_macos_launchd_plist(
    python_executable: str,
    python_path: str,
    log_file: Path,
    launcher: str,
    launcher_args: list,
    interval_seconds: int,
    pythonpath_extra: str = "",
) -> str:
    program_arguments = "\n".join(
        [
            f"        <string>{python_executable}</string>",
            f"        <string>{launcher}</string>",
            *[f"        <string>{arg}</string>" for arg in launcher_args],
        ]
    )
    env_vars = f"""        <key>PATH</key>
        <string>{python_path}</string>
        <key>DIGEST_TRIGGER</key>
        <string>automatic</string>"""
    if pythonpath_extra:
        env_vars += f"""
        <key>PYTHONPATH</key>
        <string>{pythonpath_extra}</string>"""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.ai-digest</string>
    <key>ProgramArguments</key>
    <array>
{program_arguments}
    </array>
    <key>EnvironmentVariables</key>
    <dict>
{env_vars}
    </dict>
    <key>StartInterval</key>
    <integer>{interval_seconds}</integer>
    <key>RunAtLoad</key>
    <false/>
    <key>StandardOutPath</key>
    <string>{log_file}</string>
    <key>StandardErrorPath</key>
    <string>{log_file}</string>
</dict>
</plist>
"""


def render_linux_systemd_timer(interval_seconds: int) -> str:
    return f"""[Unit]
Description=Run AI Landscape Digest periodically

[Timer]
OnBootSec=2min
OnUnitActiveSec={interval_seconds}s
Persistent=true

[Install]
WantedBy=timers.target
"""


def render_windows_task_xml(python_executable: str, launcher: str, launcher_args: list, interval_seconds: int) -> str:
    arguments = " ".join([f'"{launcher}"', *[f'"{arg}"' for arg in launcher_args]])
    return f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <Triggers>
    <LogonTrigger>
      <Enabled>true</Enabled>
      <Repetition>
        <Interval>PT{interval_seconds}S</Interval>
        <StopAtDurationEnd>false</StopAtDurationEnd>
      </Repetition>
    </LogonTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <StartWhenAvailable>true</StartWhenAvailable>
    <Enabled>true</Enabled>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{python_executable}</Command>
      <Arguments>{arguments}</Arguments>
    </Exec>
  </Actions>
</Task>
"""


def _python_env() -> tuple:
    python_path = os.environ.get("PATH", "")
    python_dir = str(Path(sys.executable).resolve().parent)
    full_path = os.pathsep.join(part for part in [python_dir, python_path] if part)
    return sys.executable, full_path


def _launcher_command(trigger: str) -> tuple:
    repo_entrypoint = REPO_ROOT / "digest.py"
    repo_src = REPO_ROOT / "src"
    if repo_entrypoint.exists():
        pythonpath_extra = str(repo_src) if repo_src.exists() else ""
        return str(repo_entrypoint), ["--trigger", trigger], pythonpath_extra
    return "-m", ["ai_digest", "--trigger", trigger], str(REPO_ROOT)


def ensure_sleepwatcher():
    if shutil.which("brew") is None:
        raise RuntimeError("Homebrew is required to install sleepwatcher automatically on macOS.")
    subprocess.run(["brew", "install", "sleepwatcher"], check=True)
    subprocess.run(["brew", "services", "start", "sleepwatcher"], check=True)


def install_macos_trigger(config: Optional["AppConfig"] = None):
    ensure_sleepwatcher()
    ensure_user_state_dir()
    python_executable, python_path = _python_env()
    launcher, launcher_args, pythonpath_extra = _launcher_command("wake")
    MACOS_WAKEUP_FILE.write_text(
        render_macos_wakeup_script(
            python_executable,
            python_path,
            LOG_FILE,
            launcher,
            launcher_args,
            pythonpath_extra,
        )
    )
    MACOS_WAKEUP_FILE.chmod(0o700)
    check_interval = config.check_interval if config else DEFAULT_CHECK_INTERVAL
    timer_enabled = check_interval > 0
    interval_seconds = check_interval if check_interval > 0 else DEFAULT_CHECK_INTERVAL
    if timer_enabled:
        _, launcher_args_auto_full, _ = _launcher_command("automatic")
        MACOS_LAUNCHD_PLIST.parent.mkdir(parents=True, exist_ok=True)
        MACOS_LAUNCHD_PLIST.write_text(
            render_macos_launchd_plist(
                python_executable,
                python_path,
                LOG_FILE,
                launcher,
                launcher_args_auto_full,
                interval_seconds,
                pythonpath_extra,
            )
        )
        MACOS_LAUNCHD_PLIST.chmod(0o644)
        subprocess.run(["launchctl", "load", str(MACOS_LAUNCHD_PLIST)])
        return f"Installed macOS wake trigger at {MACOS_WAKEUP_FILE} and launchd timer at {MACOS_LAUNCHD_PLIST}"
    return f"Installed macOS wake trigger at {MACOS_WAKEUP_FILE} (timer disabled; launchd plist not installed)"


def uninstall_macos_trigger():
    removed = []
    if MACOS_WAKEUP_FILE.exists():
        MACOS_WAKEUP_FILE.unlink()
        removed.append(str(MACOS_WAKEUP_FILE))
    if MACOS_LAUNCHD_PLIST.exists():
        subprocess.run(["launchctl", "unload", str(MACOS_LAUNCHD_PLIST)], check=False)
        MACOS_LAUNCHD_PLIST.unlink()
        removed.append(str(MACOS_LAUNCHD_PLIST))
    if removed:
        return "Removed macOS trigger files:\n" + "\n".join(removed)
    return f"No macOS trigger files found at {MACOS_WAKEUP_FILE} or {MACOS_LAUNCHD_PLIST}"


def install_linux_trigger(config: Optional["AppConfig"] = None):
    ensure_user_state_dir()
    python_executable, python_path = _python_env()
    launcher, launcher_args, _ = _launcher_command("automatic")
    LINUX_SYSTEMD_DIR.mkdir(parents=True, exist_ok=True)
    service_path = LINUX_SYSTEMD_DIR / "ai-landscape-digest.service"
    timer_path = LINUX_SYSTEMD_DIR / "ai-landscape-digest.timer"
    service_path.write_text(
        render_linux_systemd_service(
            python_executable,
            python_path,
            LOG_FILE,
            launcher,
            launcher_args,
        )
    )
    check_interval = config.check_interval if config else DEFAULT_CHECK_INTERVAL
    timer_enabled = check_interval > 0
    interval_seconds = check_interval if check_interval > 0 else DEFAULT_CHECK_INTERVAL
    if timer_enabled:
        timer_path.write_text(render_linux_systemd_timer(interval_seconds))
        if shutil.which("systemctl"):
            subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
            subprocess.run(["systemctl", "--user", "enable", "--now", timer_path.name], check=True)
        return f"Installed Linux systemd user timer at {timer_path}"
    return f"Installed Linux systemd service at {service_path} (timer disabled; timer unit not installed)"


def uninstall_linux_trigger():
    service_path = LINUX_SYSTEMD_DIR / "ai-landscape-digest.service"
    timer_path = LINUX_SYSTEMD_DIR / "ai-landscape-digest.timer"
    if shutil.which("systemctl"):
        subprocess.run(["systemctl", "--user", "disable", "--now", timer_path.name], check=False)
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=False)
    removed = []
    for path in [service_path, timer_path]:
        if path.exists():
            path.unlink()
            removed.append(str(path))
    if removed:
        return "Removed Linux trigger files:\n" + "\n".join(removed)
    return "No Linux trigger files were installed."


def install_windows_trigger(config: Optional["AppConfig"] = None):
    ensure_user_state_dir()
    xml_path = ensure_user_state_dir() / "windows-task.xml"
    launcher, launcher_args, _ = _launcher_command("automatic")
    check_interval = config.check_interval if config else DEFAULT_CHECK_INTERVAL
    timer_enabled = check_interval > 0
    interval_seconds = check_interval if check_interval > 0 else DEFAULT_CHECK_INTERVAL
    xml_path.write_text(
        render_windows_task_xml(sys.executable, launcher, launcher_args, interval_seconds),
        encoding="utf-16",
    )
    if timer_enabled:
        if shutil.which("schtasks"):
            subprocess.run(
                ["schtasks", "/Create", "/TN", WINDOWS_TASK_NAME, "/XML", str(xml_path), "/F"],
                check=True,
            )
        return f"Installed Windows scheduled task definition at {xml_path}"
    return f"Wrote Windows task XML at {xml_path} (timer disabled; task not registered with Task Scheduler)"


def uninstall_windows_trigger():
    if shutil.which("schtasks"):
        subprocess.run(["schtasks", "/Delete", "/TN", WINDOWS_TASK_NAME, "/F"], check=False)
    xml_path = ensure_user_state_dir() / "windows-task.xml"
    if xml_path.exists():
        xml_path.unlink()
        return f"Removed Windows task definition at {xml_path}"
    return "No Windows task definition was installed."


def install_trigger(config: Optional["AppConfig"] = None):
    system = platform.system()
    if system == "Darwin":
        return install_macos_trigger(config)
    if system == "Linux":
        return install_linux_trigger(config)
    if system == "Windows":
        return install_windows_trigger(config)
    raise RuntimeError(f"install-trigger is not implemented for {system}.")


def uninstall_trigger():
    system = platform.system()
    if system == "Darwin":
        return uninstall_macos_trigger()
    if system == "Linux":
        return uninstall_linux_trigger()
    if system == "Windows":
        return uninstall_windows_trigger()
    raise RuntimeError(f"uninstall-trigger is not implemented for {system}.")
