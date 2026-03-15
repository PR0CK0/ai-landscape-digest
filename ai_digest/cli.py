"""CLI parsing."""

import argparse

from ai_digest.constants import CONFIG_FILE


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ai-digest")
    parser.add_argument(
        "command",
        nargs="?",
        default="run",
        choices=["run", "install-trigger", "uninstall-trigger", "purge", "doctor"],
        help="Command to run.",
    )
    parser.add_argument(
        "--trigger",
        default=None,
        choices=["wake", "manual", "automatic", "github_actions"],
        help="Override the trigger label for this run.",
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Path to config.yaml. Defaults to auto-resolving repo mode or user mode.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Ignore seen_items.json and treat fetched items as new for this run.",
    )
    parser.add_argument(
        "--no-notify",
        action="store_true",
        help="Disable desktop notifications for this run.",
    )
    return parser


def parse_args(argv=None):
    return build_parser().parse_args(argv)
