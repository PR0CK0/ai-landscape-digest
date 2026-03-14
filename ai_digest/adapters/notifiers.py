"""Notification adapters."""

import platform
import subprocess
from typing import Optional, Protocol


class Notifier(Protocol):
    def send(self, title: str, message: str, action_label: Optional[str] = None, action_path: Optional[str] = None):
        ...

    def open_path(self, path: str):
        ...


class NullNotifier:
    def send(self, title: str, message: str, action_label: Optional[str] = None, action_path: Optional[str] = None):
        del title, message, action_label, action_path

    def open_path(self, path: str):
        del path


class MacOSNotifier:
    def send(self, title: str, message: str, action_label: Optional[str] = None, action_path: Optional[str] = None):
        if action_label and action_path:
            # Use display alert for interactivity. It's modal but we run it via osascript.
            # We use 'with timeout' to prevent it hanging the CLI forever if ignored.
            script = f'''
                tell application "System Events"
                    display alert "{title}" message "{message}" buttons {{"Close", "{action_label}"}} default button "{action_label}" giving up after 60
                    if button returned of result is "{action_label}" then
                        do shell script "open '{action_path}'"
                    end if
                end tell
            '''
            try:
                # Run in background to not block the main process if possible,
                # but osascript is usually fast.
                subprocess.Popen(["osascript", "-e", script])
            except Exception:
                pass
        else:
            script = f'display notification "{message}" with title "{title}"'
            try:
                subprocess.run(["osascript", "-e", script])
            except Exception:
                pass

    def open_path(self, path: str):
        try:
            subprocess.run(["open", path])
        except Exception:
            pass


def build_notifier() -> Notifier:
    if platform.system() == "Darwin":
        return MacOSNotifier()
    return NullNotifier()
