"""Filesystem path helpers."""

import os
import platform
from pathlib import Path


APP_DIRNAME = "ai-digest"


def user_config_dir() -> Path:
    system = platform.system()
    if system == "Darwin":
        return Path.home() / "Library" / "Application Support" / APP_DIRNAME
    if system == "Windows":
        root = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(root) / APP_DIRNAME
    root = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(root) / APP_DIRNAME


def user_state_dir() -> Path:
    system = platform.system()
    if system == "Darwin":
        return Path.home() / "Library" / "Logs" / APP_DIRNAME
    if system == "Windows":
        root = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(root) / APP_DIRNAME
    root = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
    return Path(root) / APP_DIRNAME


def ensure_user_state_dir() -> Path:
    path = user_state_dir()
    path.mkdir(parents=True, exist_ok=True)
    return path


def ensure_user_config_dir() -> Path:
    path = user_config_dir()
    path.mkdir(parents=True, exist_ok=True)
    return path


def user_documents_dir() -> Path:
    system = platform.system()
    if system == "Darwin":
        return Path.home() / "Documents" / APP_DIRNAME
    if system == "Windows":
        # Usually {User}\Documents, but can be redirected.
        # Simple default for now, similar to other path helpers.
        return Path.home() / "Documents" / APP_DIRNAME
    # Linux/others: XDG_DOCUMENTS_DIR is ideal but often not set.
    return Path.home() / "Documents" / APP_DIRNAME


def default_log_file() -> Path:
    return user_state_dir() / "ai-digest.log"
