#!/usr/bin/env python3
"""
Ollama model eval — benchmark summarization speed and output quality.

Usage:
    python3 eval/eval_models.py                        # test all pulled models
    python3 eval/eval_models.py ministral-3:3b         # test specific model(s)
    python3 eval/eval_models.py ministral-3:3b qwen2.5:1.5b

Runs each model N times (default 3) and reports:
  - median / min / max wall-clock time
  - raw output for quality inspection

Recommended models to pull (non-thinking, fast, good quality):
    ollama pull qwen2.5:0.5b      # ~400 MB  — fastest, lower quality
    ollama pull qwen2.5:1.5b      # ~1.0 GB  — good balance, target <5s
    ollama pull llama3.2:1b       # ~1.3 GB  — solid quality, target ~5s
    ollama pull gemma3:1b         # ~1.0 GB  — Google, good instruction following
    ollama pull smollm2:1.7b      # ~1.1 GB  — designed for fast inference

NOTE: Avoid qwen3.x models — they are "thinking" models that leak chain-of-thought
      and are much slower than their size suggests.
"""

import statistics
import subprocess
import sys
import time

RUNS = 3  # runs per model — median is reported

# ── Representative payload ───────────────────────────────────────────────────
# ~37 items — representative of a normal fetch (not --force with 85 items)
INSTRUCTION = (
    "Write ultra-compact markdown for developers. "
    "No version numbers. No intro. No outro. "
    "Group by tool or source with short headings. "
    "One bullet per tool. If a tool has multiple changes, list them comma-separated on that one line. "
    "Each bullet: tool name then comma-separated changes, 2-8 words total. "
    "Use at most 10 bullets total. "
    "Add a BREAKING section only for real breakage."
)

SAMPLE_ITEMS = """\
[Claude Code] slash commands rework, /memory command, worktree support, hook system, ExitWorktree tool
[Claude Code] voice push-to-talk added, bash auto-approval mode
[Claude Code] MCP server hooks, sparse worktree paths, autoMemoryDirectory setting
[Gemini CLI] nightly v0.35.0: chat resume footer, A2A timeout fix
[Gemini CLI] v0.34.0: thinking UI overhaul, streaming improvements
[Gemini CLI] v0.33.0: docs fixes, SVG styling in output
[Codex CLI] alpha-24: Rust 2023-10 edition updates, WASM build optimization
[Codex CLI] alpha-23: improved error context in API responses, JSON schema validation
[Codex CLI] alpha-22: --debug flag added to CLI
[Aider] GPT-5 support added, Grok-4 integration
[Aider] Gemini 2.5 Lite support, MoonShot/Kimi-K2 model routing
[Aider] /clear confirmation prompt, /undo line truncation fix
[Ollama] v0.18.0: cloud models auto-tag, Claude compaction window support
[Ollama] thinking levels parsing, extended context length support
[Anthropic SDK] v0.84.0: array_format changed to brackets, MCP tools helpers added
[Anthropic SDK] v0.83.0: top-level cache control for automatic caching
[Anthropic SDK] v0.82.0: UserLocation type fixes
[OpenAI SDK] v2.28.0: custom voices API, character endpoint
[OpenAI SDK] v2.27.0: Sora API edits, video export support
[OpenAI SDK] v2.25.0: GPT-5.4 support, tools rework
[OpenAI Blog] GPT-5.4 Pro and Thinking variants announced
[OpenAI Blog] o3 reasoning model released for API
[Hugging Face] Storage Buckets launched for dataset hosting
[Hugging Face] Granite 4.0 speech model, LeRobot v0.5.0
[Last Week in AI] Gemini 3.1 Flash Lite: 1/8 cost of Pro
[Last Week in AI] DOD deal with Anthropic raises supply chain concerns
[Latent Space] RAG vs hybrid search agents design patterns
[Latent Space] Claude prompt caching economics analysis\
"""

PROMPT = f"{INSTRUCTION}\n\nItems:\n{SAMPLE_ITEMS}"


def list_pulled_models() -> list[str]:
    result = subprocess.run(["ollama", "list"], capture_output=True, text=True)
    models = []
    for line in result.stdout.splitlines()[1:]:  # skip header
        parts = line.split()
        if parts:
            models.append(parts[0])
    return models


def run_model(model: str) -> tuple[float, str]:
    start = time.perf_counter()
    result = subprocess.run(
        ["ollama", "run", model, PROMPT],
        capture_output=True, text=True, timeout=180,
    )
    elapsed = time.perf_counter() - start
    if result.returncode != 0:
        return elapsed, f"[ERROR] {result.stderr.strip()}"
    return elapsed, result.stdout.strip()


def bar(seconds: float, max_seconds: float = 30.0, width: int = 28) -> str:
    filled = int(min(seconds / max_seconds, 1.0) * width)
    return "█" * filled + "░" * (width - filled)


def speed_label(med: float) -> str:
    if med <= 5.0:
        return "✓ target"
    if med <= 8.0:
        return "~ close"
    return "✗ slow"


def main():
    pulled = list_pulled_models()

    if len(sys.argv) > 1:
        models = sys.argv[1:]
        missing = [m for m in models if m not in pulled]
        if missing:
            for m in missing:
                print(f"  ⚠  {m} not pulled — run: ollama pull {m}")
            models = [m for m in models if m in pulled]
    else:
        models = pulled

    if not models:
        print("No models to evaluate. Pull one first: ollama pull <model>")
        return

    print(f"\n{'─' * 72}")
    print(f"  ai-digest model eval  |  {RUNS} runs each  |  {len(SAMPLE_ITEMS.splitlines())} items  |  models: {len(models)}")
    print(f"{'─' * 72}\n")

    results = []

    for model in models:
        times = []
        last_output = ""

        for i in range(RUNS):
            print(f"  {model:<28}  run {i+1}/{RUNS}...", end="\r", flush=True)
            try:
                elapsed, output = run_model(model)
                times.append(elapsed)
                last_output = output
            except subprocess.TimeoutExpired:
                print(f"  {model:<28}  TIMEOUT (>180s)")
                break

        if not times:
            continue

        med = statistics.median(times)
        mn = min(times)
        mx = max(times)
        results.append((model, med, mn, mx, last_output))

        print(f"  {model:<28}  {bar(med)}  {med:>5.1f}s  (min {mn:.1f}  max {mx:.1f})")

    if not results:
        return

    # ── Summary ───────────────────────────────────────────────────────────────
    print(f"\n{'─' * 72}")
    print("  SUMMARY  (fastest first)")
    print(f"{'─' * 72}")
    for model, med, mn, mx, _ in sorted(results, key=lambda x: x[1]):
        print(f"  {model:<28}  {med:>5.1f}s median   {speed_label(med)}")

    # ── Output samples ─────────────────────────────────────────────────────────
    print(f"\n{'─' * 72}")
    print("  OUTPUT SAMPLES  (fastest first — judge quality here)")
    print(f"{'─' * 72}")
    for model, med, _, _, output in sorted(results, key=lambda x: x[1]):
        width = 72 - len(model) - len(f"  ── {model} ({med:.1f}s) ")
        print(f"\n  ── {model} ({med:.1f}s) {'─' * max(width, 2)}")
        for line in output.splitlines():
            print(f"  {line}")

    print(f"\n{'─' * 72}\n")


if __name__ == "__main__":
    main()
