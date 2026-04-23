# ai-terminal-title

A tiny `UserPromptSubmit` hook that auto-renames your terminal tab to a short
summary of the latest prompt you sent to **Claude Code** or **OpenAI Codex
CLI**. Same script, both agents, zero dependencies beyond `bash` and
`python3`.

![demo placeholder](docs/demo.gif)

## Why

Running multiple agent sessions in Cursor / VS Code / iTerm tabs, you lose
track of which tab is working on what. Manually renaming tabs is friction —
and Cursor's right-click rename is flaky. This hook does it for you on every
turn.

## How it works

Both Claude Code and Codex CLI fire a `UserPromptSubmit` hook before each
turn and pass a JSON payload on `stdin` that includes the user's prompt.
The hook script reads that, slugifies the first ~60 chars, and emits an
[OSC-2](https://www.xfree86.org/current/ctlseqs.html) escape sequence to
`/dev/tty`. Compliant terminals pick it up and rename the tab.

Agent is detected from the `hook_event_name` / `transcript_path` fields and
prefixed as `[C]` (Claude) or `[X]` (Codex) so you can tell sessions apart.

## Requirements

- `bash`, `python3` (both come with macOS and most Linux distros)
- Claude Code **or** Codex CLI (both work, side by side)
- A terminal that honours OSC-2: iTerm2, Terminal.app, Alacritty, Kitty,
  Cursor / VS Code integrated terminal (see config tweak below)

## Install

```bash
git clone https://github.com/Kibitz117/ai-terminal-title.git ~/.ai-terminal-title
chmod +x ~/.ai-terminal-title/terminal-title.sh
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
            "command": "/ABSOLUTE/PATH/TO/terminal-title.sh",
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
               "command": "/ABSOLUTE/PATH/TO/terminal-title.sh",
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
ignores OSC titles. Flip it to display the sequence in your user settings:

```json
"terminal.integrated.tabs.title": "${sequence}",
"terminal.integrated.tabs.description": "${process}"
```

iTerm2, Terminal.app, Alacritty, and Kitty work out of the box.

## Configuration

| Env var            | Default | Description                                   |
| ------------------ | ------- | --------------------------------------------- |
| `AI_TITLE_MAX`     | `60`    | Max characters of the prompt to keep.         |
| `AI_TITLE_PREFIX`  | (none)  | Literal string prepended to every title.      |
| `AI_TITLE_NO_TAG`  | (unset) | Set to `1` to drop the `[C]`/`[X]` agent tag. |

Set them in the hook's `command` line, e.g.:

```json
"command": "AI_TITLE_PREFIX='🤖 ' AI_TITLE_MAX=40 /path/to/terminal-title.sh"
```

## Smoke test

```bash
echo '{"prompt":"refactor the bot pipeline","hook_event_name":"UserPromptSubmit"}' \
  | ./terminal-title.sh
```

Your terminal tab should briefly flash to `[C] refactor the bot pipeline`.

## Troubleshooting

- **Title doesn't change in Cursor/VS Code** — add the
  `terminal.integrated.tabs.title` setting above.
- **Title reverts between turns** — normal. Shell prompt / zsh themes often
  rewrite the title on each command. The hook resets it on the next prompt.
- **Codex hook never fires** — confirm `codex_hooks = true` is set and
  restart the CLI. Codex hooks are experimental and require the feature flag.
- **Codex: hook fires but title snaps back to `codex-…`** — you forgot
  `tui.terminal_title = []`. Codex's default title writer wins any race
  against the OSC escape.
- **Codex 0.117.0–0.121.x:** hook stdout is swallowed in the TUI path
  ([#15984](https://github.com/openai/codex/issues/15984)). This hook
  bypasses that by writing straight to `/dev/tty`, so it is unaffected —
  but other hooks that rely on stdout developer-context may be.
- **Want an LLM-generated title instead of truncation** — fork and swap the
  inline `python3` block for a call to your model of choice. Keep the hook
  under its timeout or the parent agent will warn.

## Prior art

Inspired by [bluzername/claude-code-terminal-title](https://github.com/bluzername/claude-code-terminal-title),
which covers Claude Code only. This project adds Codex CLI support and a
single shared script.

## License

MIT — see [LICENSE](LICENSE).
