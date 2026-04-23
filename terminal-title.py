#!/usr/bin/env python3
"""ai-terminal-title — UserPromptSubmit hook for Claude Code and OpenAI Codex CLI.

Behavior:
  Turn 1, Turn 1 + k*N → background LLM summary over the rolling prompt buffer
  Other turns          → no-op

Turn 1 fires the LLM worker immediately, so the tab label arrives ~1-2s into
the first response rather than stalling the user. If the LLM call fails or
no agent CLI is on PATH, the worker falls back to a truncated latest prompt.

Uses the coding agent's own CLI (`claude -p`, `codex exec`) so no API key is
required — token cost falls on the user's existing subscription. Recursion into
the hook from the summarizer call is blocked via AI_TITLE_INTERNAL=1.

Env vars:
  AI_TITLE_EVERY       LLM rename cadence after turn 1 (default 5)
  AI_TITLE_MODE        auto | trunc (default auto — LLM; trunc = deterministic)
  AI_TITLE_MODEL       override model; defaults: claude-haiku-4-5 | gpt-5-mini
  AI_TITLE_BUFFER      rolling prompt buffer size fed to the LLM (default 8)
  AI_TITLE_MAX         max title length (default 60)
  AI_TITLE_PREFIX      literal prefix prepended to every title
  AI_TITLE_NO_TAG      "1" disables the [C]/[X] agent tag
  AI_TITLE_DEBUG       "1" appends trace logs to AI_TITLE_LOG
  AI_TITLE_LOG         debug log path (default /tmp/ai-terminal-title.log)
  AI_TITLE_STATE_DIR   per-session state dir (default ~/.cache/ai-terminal-title)
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

LOG_PATH = Path(os.environ.get("AI_TITLE_LOG", "/tmp/ai-terminal-title.log"))
DEBUG = os.environ.get("AI_TITLE_DEBUG") == "1"


def log(msg: str) -> None:
    if not DEBUG:
        return
    try:
        with LOG_PATH.open("a") as f:
            f.write(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}\n")
    except OSError:
        pass


def write_title(title: str) -> None:
    try:
        with open("/dev/tty", "w") as tty:
            tty.write(f"\033]2;{title}\007")
            tty.flush()
    except OSError as e:
        log(f"dev tty write failed: {e}")


def detect_agent(payload: dict) -> str:
    probe = (
        str(payload.get("hook_event_name") or "")
        + " "
        + str(payload.get("transcript_path") or "")
    ).lower()
    return "codex" if "codex" in probe else "claude"


def tag_for(agent: str) -> str:
    if os.environ.get("AI_TITLE_NO_TAG") == "1":
        return ""
    return {"claude": "[C] ", "codex": "[X] "}.get(agent, "")


def session_id_for(payload: dict) -> str:
    sid = payload.get("session_id")
    if sid:
        return str(sid)
    transcript = str(payload.get("transcript_path") or payload.get("cwd") or "unknown")
    return hashlib.sha1(transcript.encode()).hexdigest()[:16]


def state_path(session_id: str) -> Path:
    base = Path(
        os.environ.get(
            "AI_TITLE_STATE_DIR", os.path.expanduser("~/.cache/ai-terminal-title")
        )
    )
    base.mkdir(parents=True, exist_ok=True)
    return base / f"{session_id}.json"


def load_state(path: Path) -> dict:
    if not path.exists():
        return {"turn": 0, "prompts": [], "agent": ""}
    try:
        return json.loads(path.read_text())
    except Exception:
        return {"turn": 0, "prompts": [], "agent": ""}


def save_state(path: Path, state: dict) -> None:
    path.write_text(json.dumps(state))


def clean_title(raw: str, limit: int) -> str:
    line = raw.strip().splitlines()[0] if raw.strip() else ""
    line = line.strip().strip('"').strip("'").strip("`").strip()
    line = re.sub(r"[\x00-\x1f]", "", line)
    return line[:limit]


def summarize_with_claude(instruction: str, model: str) -> str:
    env = {**os.environ, "AI_TITLE_INTERNAL": "1"}
    result = subprocess.run(
        ["claude", "-p", "--model", model],
        input=instruction,
        capture_output=True,
        text=True,
        timeout=45,
        env=env,
    )
    return result.stdout or ""


def summarize_with_codex(instruction: str, model: str) -> str:
    env = {**os.environ, "AI_TITLE_INTERNAL": "1"}
    result = subprocess.run(
        ["codex", "exec", "--model", model, "-"],
        input=instruction,
        capture_output=True,
        text=True,
        timeout=45,
        env=env,
    )
    return result.stdout or ""


def run_llm_worker(state_file: Path) -> None:
    if not state_file.exists():
        return
    state = load_state(state_file)
    prompts = state.get("prompts", [])
    if not prompts:
        return
    agent = state.get("agent") or "claude"

    rolled = "\n\n".join(f"[Turn {i + 1}] {p}" for i, p in enumerate(prompts))
    instruction = (
        "Below are the user's recent messages in a coding session. Emit ONLY a "
        "short terminal tab title (max 6 words, no quotes, no trailing "
        "punctuation, no emoji) that captures the current focus. Output just "
        "the title text, nothing else, no preamble.\n\n" + rolled
    )

    raw = ""
    try:
        if agent == "claude" and shutil.which("claude"):
            raw = summarize_with_claude(
                instruction, os.environ.get("AI_TITLE_MODEL", "claude-haiku-4-5")
            )
        elif agent == "codex" and shutil.which("codex"):
            raw = summarize_with_codex(
                instruction, os.environ.get("AI_TITLE_MODEL", "gpt-5-mini")
            )
        else:
            log(f"no CLI found for agent {agent}, falling back to truncation")
    except subprocess.TimeoutExpired:
        log("llm timeout, falling back")
    except Exception as e:
        log(f"llm error: {e}")

    limit = int(os.environ.get("AI_TITLE_MAX", "60"))
    title = clean_title(raw, limit) if raw else prompts[-1][:limit]
    if not title:
        return

    prefix = os.environ.get("AI_TITLE_PREFIX", "")
    tag = tag_for(agent)
    final = f"{prefix}{tag}{title}"[: limit + len(prefix) + len(tag)]
    write_title(final)
    log(f"llm worker wrote: {final}")


def spawn_llm_worker(state_file: Path) -> None:
    env = {**os.environ, "AI_TITLE_INTERNAL": "1"}
    subprocess.Popen(
        [sys.executable, os.path.realpath(__file__), "--llm-worker", str(state_file)],
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def main() -> None:
    if "--llm-worker" in sys.argv:
        run_llm_worker(Path(sys.argv[-1]))
        return

    # Recursion guard for nested agent invocations that share env.
    if os.environ.get("AI_TITLE_INTERNAL") == "1":
        return

    payload_raw = sys.stdin.read()
    log(f"hook fired, bytes={len(payload_raw)}")
    if not payload_raw.strip():
        return
    try:
        payload = json.loads(payload_raw)
    except Exception as e:
        log(f"json parse error: {e}")
        return

    prompt = re.sub(r"\s+", " ", str(payload.get("prompt") or "")).strip()
    if not prompt:
        return

    agent = detect_agent(payload)
    session_id = session_id_for(payload)
    sfile = state_path(session_id)
    state = load_state(sfile)
    state["turn"] = int(state.get("turn", 0)) + 1
    buf = int(os.environ.get("AI_TITLE_BUFFER", "8"))
    state["prompts"] = (state.get("prompts", []) + [prompt])[-buf:]
    state["agent"] = agent
    save_state(sfile, state)

    turn = state["turn"]
    limit = int(os.environ.get("AI_TITLE_MAX", "60"))
    prefix = os.environ.get("AI_TITLE_PREFIX", "")
    tag = tag_for(agent)
    mode = os.environ.get("AI_TITLE_MODE", "auto").lower()
    every = max(1, int(os.environ.get("AI_TITLE_EVERY", "5")))

    if mode == "trunc":
        write_title(f"{prefix}{tag}{prompt[:limit]}")
        log(f"trunc mode: {prompt[:limit]}")
        return

    if turn == 1 or (turn - 1) % every == 0:
        spawn_llm_worker(sfile)
        log(f"spawned llm worker (turn {turn})")


if __name__ == "__main__":
    main()
