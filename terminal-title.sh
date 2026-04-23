#!/usr/bin/env bash
# ai-terminal-title
#
# A UserPromptSubmit hook for Claude Code and OpenAI Codex CLI that renames
# the controlling terminal tab to a short summary of the latest user prompt.
#
# Reads the hook JSON payload from stdin, extracts `.prompt`, and emits an
# OSC-2 escape sequence to /dev/tty. Terminals that honour OSC-0/2 (iTerm2,
# Terminal.app, Cursor / VS Code integrated terminal with `${sequence}` in
# `terminal.integrated.tabs.title`, Kitty, Alacritty, etc.) will relabel the
# tab each turn.
#
# Env vars:
#   AI_TITLE_MAX      max chars of the prompt to keep (default 60)
#   AI_TITLE_PREFIX   literal prefix prepended to every title (default "")
#   AI_TITLE_NO_TAG   set to "1" to disable the [C]/[X] agent tag
set -u

payload="$(cat)"
[ -z "$payload" ] && exit 0

title="$(printf '%s' "$payload" | python3 - <<'PY' 2>/dev/null
import json, os, re, sys
try:
    d = json.loads(sys.stdin.read())
except Exception:
    sys.exit(0)
text = d.get("prompt") or ""
text = re.sub(r"\s+", " ", text).strip()
if not text:
    sys.exit(0)
limit = int(os.environ.get("AI_TITLE_MAX", "60"))
prefix = os.environ.get("AI_TITLE_PREFIX", "")
no_tag = os.environ.get("AI_TITLE_NO_TAG", "") == "1"
probe = (d.get("hook_event_name", "") + " " + d.get("transcript_path", "")).lower()
agent = "codex" if "codex" in probe else "claude"
tag = "" if no_tag else {"claude": "[C] ", "codex": "[X] "}.get(agent, "")
print(f"{prefix}{tag}{text[:limit]}")
PY
)"

[ -z "$title" ] && exit 0

printf '\033]2;%s\007' "$title" > /dev/tty 2>/dev/null || true
exit 0
