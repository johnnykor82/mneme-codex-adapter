# Codex Agent Install Instructions

This file is for users who want a Codex agent to install Mneme for them.

Give the agent this repository URL and ask it to read this file first:

```text
Install Mneme Codex adapter globally from:
https://github.com/johnnykor82/mneme-codex-adapter

Before doing anything, read CODEX_AGENT_INSTALL.md in that repository and follow it.
If anything fails, write a clear install feedback file to the path I provide.
Do not print or commit tokens.
```

## Agent Task

Install Mneme as a user-global Codex Desktop memory setup, not as a temporary
workspace-only experiment.

Use the full guide:

```text
adapters/codex/CODEX_DESKTOP_QUICKSTART.md
```

Default install root:

```bash
export MNEME_CODEX_HOME="$HOME/.mneme-codex"
```

## Required Steps

1. Create the install root and virtual environment.
2. Install this adapter from GitHub.
3. Run `mneme-codex setup codex-desktop --global`.
4. Start the daemon with `$MNEME_CODEX_HOME/bin/mneme-serve`.
5. Run `mneme-codex doctor --install-root "$MNEME_CODEX_HOME"`.
6. Show the user the generated MCP config snippet path.
7. Ask the user before editing any global Codex config.
8. Run the sample transcript smoke ingest.
9. Do not enable write hooks. Use capture/validate only unless the user explicitly approves write hooks later.

## Commands

```bash
export MNEME_CODEX_HOME="$HOME/.mneme-codex"
python3 -m venv "$MNEME_CODEX_HOME/.venv"
"$MNEME_CODEX_HOME/.venv/bin/python" -m pip install --upgrade pip
"$MNEME_CODEX_HOME/.venv/bin/python" -m pip install \
  "git+https://github.com/johnnykor82/mneme-codex-adapter.git"

"$MNEME_CODEX_HOME/.venv/bin/mneme-codex" setup codex-desktop \
  --global \
  --install-root "$MNEME_CODEX_HOME" \
  --python "$MNEME_CODEX_HOME/.venv/bin/python"
```

Start the daemon in a normal terminal:

```bash
"$MNEME_CODEX_HOME/bin/mneme-serve"
```

Verify from another terminal:

```bash
curl -sS http://127.0.0.1:8765/v1/health
"$MNEME_CODEX_HOME/.venv/bin/mneme-codex" doctor \
  --install-root "$MNEME_CODEX_HOME"
```

Smoke ingest:

```bash
"$MNEME_CODEX_HOME/.venv/bin/mneme-codex" codex-ingest \
  --input "$MNEME_CODEX_HOME/.local/mneme-codex-sample-transcript.json"
```

MCP config snippet:

```bash
cat "$MNEME_CODEX_HOME/codex/mcp_config.toml.snippet"
```

## Success Criteria

- `mneme-codex doctor` reports `READY` after the daemon is running.
- The install root contains `.local/mneme.env`, `bin/mneme-serve`, `bin/mneme-mcp`, and `codex/mcp_config.toml.snippet`.
- The sample transcript ingest succeeds.
- Codex MCP config is shown to the user without printing the token.
- Write hooks remain disabled.

## If Something Fails

Do not guess silently. Create an install feedback file in the path the user
provides. If the user did not provide a path, write `mneme-codex-install-feedback.md`
in the current workspace.

Use this structure:

```markdown
# Mneme Codex Install Feedback

## Environment
- OS:
- Python:
- Install root:
- Repository URL:
- Commit or date:

## What Worked

## What Failed

## Exact Commands Tried

## Error Output

## Suspected Cause

## Suggested Documentation Or Installer Fix
```

Never include bearer tokens, API keys, `.local/mneme.env` contents, or private
database contents in the feedback file.
