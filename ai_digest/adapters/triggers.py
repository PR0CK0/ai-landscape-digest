"""Trigger-specific runtime behavior."""

from dataclasses import dataclass
from typing import Callable, Optional, TYPE_CHECKING

NotifierFn = Callable[[str, str, Optional[str], Optional[str]], None]

if TYPE_CHECKING:
    from ai_digest.settings import AppConfig


@dataclass
class TriggerAdapter:
    name: str
    notifier: NotifierFn
    notifications_enabled: bool = True

    def notify(self, title: str, message: str, action_label: Optional[str] = None, action_path: Optional[str] = None):
        if self.notifications_enabled:
            self.notifier(title, message, action_label, action_path)

    def should_run(self, config: "AppConfig") -> bool:
        del config
        return True

    def on_skip(self, config: "AppConfig"):
        del config

    def on_start(self, config: "AppConfig"):
        del config

    def on_no_items(self, config: "AppConfig"):
        del config

    def on_error(self, config: "AppConfig"):
        del config

    def on_summarize(self, config: "AppConfig", backend: str, model: str):
        del config, backend, model

    def on_success(self, config: "AppConfig", item_count: int, backend: str):
        del config, item_count, backend

    def on_html_ready(self, config: "AppConfig", report_path: str):
        del config, report_path


@dataclass
class WakeTriggerAdapter(TriggerAdapter):
    due_fn: Callable[[int], bool] = None
    save_last_fetch_at_fn: Callable[[], None] = None
    interval_label_fn: Callable[[int], str] = None

    def should_run(self, config: "AppConfig") -> bool:
        if config.check_interval == 0:
            return True
        return self.due_fn(config.check_interval)

    def on_skip(self, config: "AppConfig"):
        label = self.interval_label_fn(config.check_interval)
        self.notify("AI Landscape Digest", f"Skipped: checked for new releases within {label}.")

    def on_start(self, config: "AppConfig"):
        del config
        self.notify("AI Landscape Digest", "Checking for new releases...")
        self.save_last_fetch_at_fn()

    def on_no_items(self, config: "AppConfig"):
        del config
        self.notify("AI Landscape Digest", "All caught up! No new releases.")

    def on_error(self, config: "AppConfig"):
        del config
        self.notify("AI Landscape Digest", "Summarization failed. Check terminal for details.")

    def on_summarize(self, config: "AppConfig", backend: str, model: str):
        del config
        label = model if model and model != "default" else backend
        self.notify("AI Landscape Digest", f"Summarizing with {label}...")

    def on_success(self, config: "AppConfig", item_count: int, backend: str):
        del config
        self.notify("AI Landscape Digest", f"{item_count} new items summarized with {backend}.")

    def on_html_ready(self, config: "AppConfig", report_path: str):
        del config
        self.notify("AI Landscape Digest", "Digest ready — click to open report.", "Open Report", report_path)


@dataclass
class TimerTriggerAdapter(WakeTriggerAdapter):
    """Scheduled interval timer — same throttle/state logic as wake, distinct notification copy."""

    def on_start(self, config: "AppConfig"):
        del config
        self.notify("AI Landscape Digest", "Scheduled check — looking for new releases...")
        self.save_last_fetch_at_fn()

    def on_skip(self, config: "AppConfig"):
        label = self.interval_label_fn(config.check_interval)
        self.notify("AI Landscape Digest", f"Scheduled check — already ran within {label}.")

    def on_no_items(self, config: "AppConfig"):
        del config
        self.notify("AI Landscape Digest", "Scheduled check — nothing new.")

    def on_error(self, config: "AppConfig"):
        del config
        self.notify("AI Landscape Digest", "Scheduled check failed. See logs.")

    def on_success(self, config: "AppConfig", item_count: int, backend: str):
        del config
        self.notify("AI Landscape Digest", f"{item_count} new items (scheduled) via {backend}.")

    def on_html_ready(self, config: "AppConfig", report_path: str):
        del config
        self.notify("AI Landscape Digest", "Scheduled digest ready — click to open.", "Open Report", report_path)


def build_trigger_adapter(trigger: str,
                          notifier: NotifierFn,
                          notifications_enabled: bool,
                          due_fn: Callable[[int], bool],
                          save_last_fetch_at_fn: Callable[[], None],
                          interval_label_fn: Callable[[int], str]) -> TriggerAdapter:
    kwargs = dict(
        notifier=notifier,
        notifications_enabled=notifications_enabled,
        due_fn=due_fn,
        save_last_fetch_at_fn=save_last_fetch_at_fn,
        interval_label_fn=interval_label_fn,
    )
    if trigger == "wake":
        return WakeTriggerAdapter(name=trigger, **kwargs)
    if trigger == "automatic":
        return TimerTriggerAdapter(name=trigger, **kwargs)
    return TriggerAdapter(name=trigger, notifier=notifier, notifications_enabled=notifications_enabled)
