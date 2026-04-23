# ai-terminal-title

A `UserPromptSubmit` hook that auto-renames your terminal tab to a short
summary of whatever you're working on in **Claude Code** or **OpenAI Codex
CLI**. Zero API key needed — it shells out to the agent's own CLI
(`claude -p`, `codex exec`) so summarization runs on your existing login.

Same script, both agents, pure-Python, no dependencies beyond `python3`.

## Why

When you run multiple agent sessions in Cursor / VS Code / iTerm tabs, the
tab titles all look the same (`codex-aarch64-ap`, `zsh`, etc.) and you lose
track of which tab is doing what. Manual renaming is friction — and
Cursor's right-click rename is flaky.

## How it works

Both Claude Code and Codex CLI fire a `UserPromptSubmit` hook before each
turn and pass a JSON payload on `stdin` that includes the user's prompt.
The hook:

1. **Turn 1** → emits an instant deterministic title (first 60 chars of
   your prompt, no LLM wait, no cost).
2. **Every N turns after** (default `N=5`) → spawns a **detached
   background worker** that rolls up the last N prompts, shells out to
   `claude -p --model claude-haiku-4-5` or `codex exec --model gpt-5-mini`
   for a summary, and updates the title when it returns. Hook itself
   returns in <50ms so it never blocks your turn.
3. **Off-cycle turns** → no-op (or deterministic every turn with
   `AI_TITLE_EVERY_TURN=1`).

The summary call uses the user's existing CLI auth, so there's **no extra
configuration, no API key, no separate subscription**. Token cost falls on
your existing Claude or Codex plan (~1 cent per hour of heavy use).

Agent is detected from the hook payload and prefixed as `[C]` (Claude) or
`[X]` (Codex) so you can tell sessions apart at a glance.

## Requirements

- `python3` (ships with macOS and most Linux distros)
- Claude Code **and/or** Codex CLI (both supported, side by side)
- A terminal that honours OSC-2: iTerm2, Terminal.app, Alacritty, Kitty,
  Cursor / VS Code integrated terminal (see config tweak below)

## Install

```bash
git clone https://github.com/Kibitz117/ai-terminal-title.git ~/.ai-terminal-title
chmod +x ~/.ai-terminal-title/terminal-title.py
```

### Claude Code

Edit `~/.claude/settings.json` and add the hook under
`hooks.UserPromptSubmit`:

```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "/ABSOLUTE/PATH/TO/terminal-title.py",
            "timeout": 3
          }
        ]
      }
    ]
  }
}
```

Full example at [`examples/claude-settings.json`](examples/claude-settings.json).

### Codex CLI

> **Important:** Codex ships with `tui.terminal_title = ["spinner", "project"]`
> which makes the CLI continuously re-render the tab title and clobber any
> OSC escape this hook emits. You **must** disable it or the rename will be
> invisible.

1. Enable hooks and disable Codex's own title writer in `~/.codex/config.toml`:

   ```toml
   [features]
   codex_hooks = true

   [tui]
   terminal_title = []
   ```

2. Create `~/.codex/hooks.json`:

   ```json
   {
     "hooks": {
       "UserPromptSubmit": [
         {
           "hooks": [
             {
               "type": "command",
               "command": "/ABSOLUTE/PATH/TO/terminal-title.py",
               "timeout": 3
             }
           ]
         }
       ]
     }
   }
   ```

   Full example at [`examples/codex-hooks.json`](examples/codex-hooks.json).

3. Restart the Codex CLI.

### Cursor / VS Code

The integrated terminal shows the running process name by default and
**ignores OSC titles** until you tell it otherwise. Flip it to display the
sequence in your user settings (`Cmd+Shift+P` → *Preferences: Open User
Settings (JSON)*):

```json
"terminal.integrated.tabs.title": "${sequence}",
"terminal.integrated.tabs.description": "${process}"
```

Setting names are identical in Cursor and VS Code (Cursor is a fork). iTerm2,
Terminal.app, Alacritty, and Kitty honour OSC titles out of the box.

## Configuration

Set via env vars in the hook's `command` line, e.g.:

```json
"command": "AI_TITLE_EVERY=3 AI_TITLE_PREFIX='🤖 ' /path/to/terminal-title.py"
```

| Env var               | Default | Description                                          |
| --------------------- | ------- | ---------------------------------------------------- |
| `AI_TITLE_EVERY`      | `5`     | LLM rename cadence after turn 1.                     |
| `AI_TITLE_MODE`       | `auto`  | `auto` (LLM if CLI found) \| `llm` \| `trunc`.       |
| `AI_TITLE_MODEL`      | agent-specific | Override summarization model.                 |
| `AI_TITLE_BUFFER`     | `8`     | Rolling prompt buffer size fed to the LLM.           |
| `AI_TITLE_MAX`        | `60`    | Max characters in the emitted title.                 |
| `AI_TITLE_PREFIX`     | (none)  | Literal string prepended to every title.             |
| `AI_TITLE_NO_TAG`     | (unset) | Set to `1` to drop the `[C]`/`[X]` agent tag.        |
| `AI_TITLE_EVERY_TURN` | (unset) | Set to `1` to rename deterministically every turn.   |
| `AI_TITLE_DEBUG`      | (unset) | Set to `1` to append trace logs to `AI_TITLE_LOG`.   |
| `AI_TITLE_LOG`        | `/tmp/ai-terminal-title.log` | Debug log path.                 |
| `AI_TITLE_STATE_DIR`  | `~/.cache/ai-terminal-title` | Per-session state dir.          |

## Smoke test

```bash
AI_TITLE_DEBUG=1 ./terminal-title.py \
  <<<'{"prompt":"refactor the bot pipeline","hook_event_name":"UserPromptSubmit","session_id":"test"}'
cat /tmp/ai-terminal-title.log
```

In a real terminal the tab should flash to `[C] refactor the bot pipeline`.

## Troubleshooting

- **Title doesn't change in Cursor/VS Code** — add the
  `terminal.integrated.tabs.title` setting above.
- **Codex: hook fires but title snaps back to `codex-…`** — you forgot
  `tui.terminal_title = []` in `config.toml`. Codex's default title writer
  wins any race against the OSC escape.
- **Codex hook never fires** — confirm `codex_hooks = true` is set and
  restart the CLI. Codex hooks are experimental and require the feature flag.
- **Title never updates past turn 1** — turn on `AI_TITLE_DEBUG=1` and check
  `/tmp/ai-terminal-title.log`. Common cause: `claude` / `codex` CLI not on
  `PATH` when the hook runs (GUI terminal sessions sometimes have trimmed
  PATH). Absolute-path them in `AI_TITLE_MODEL` config or add them to
  the hook command: `"command": "PATH=/usr/local/bin:$PATH /path/to/terminal-title.py"`.
- **Codex 0.117.0–0.121.x**: hook stdout is swallowed in the TUI path
  ([#15984](https://github.com/openai/codex/issues/15984)). This hook
  bypasses that by writing straight to `/dev/tty`, so it is unaffected —
  but other hooks that rely on stdout developer-context may be.

## Prior art

Inspired by [bluzername/claude-code-terminal-title](https://github.com/bluzername/claude-code-terminal-title),
which covers Claude Code only. This project adds Codex CLI support, a
shared script, and LLM-summarized titles using the agent's own login.

## License

MIT — see [LICENSE](LICENSE).
