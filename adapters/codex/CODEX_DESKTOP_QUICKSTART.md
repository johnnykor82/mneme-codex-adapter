# Codex Desktop Quickstart

This guide installs Mneme for one macOS user account so Codex Desktop can use
Mneme memory tools from any project on that machine.

It does not enable automatic Codex prompt replacement. Current Codex support is
MCP memory tools plus explicit hook capture/ingest commands.

## 1. Install The Adapter

Use a per-user install root. This keeps the daemon database, token, scripts, and
generated config snippets out of project repos.

```bash
export MNEME_CODEX_HOME="$HOME/.mneme-codex"
python3 -m venv "$MNEME_CODEX_HOME/.venv"
"$MNEME_CODEX_HOME/.venv/bin/python" -m pip install --upgrade pip
"$MNEME_CODEX_HOME/.venv/bin/python" -m pip install \
  "git+https://github.com/johnnykor82/mneme-codex-adapter.git"
```

## 2. Create Local Runtime Files

Run `mneme-codex setup codex-desktop --global` to create the per-user runtime
files:

```bash
"$MNEME_CODEX_HOME/.venv/bin/mneme-codex" setup codex-desktop \
  --global \
  --install-root "$MNEME_CODEX_HOME" \
  --python "$MNEME_CODEX_HOME/.venv/bin/python"
```

This creates local files under `$MNEME_CODEX_HOME`, including:

- `.local/mneme.env` with `MNEME_AUTH_TOKEN`;
- `.local/mneme.db` path for the daemon;
- `bin/mneme-serve`;
- `bin/mneme-mcp`;
- `codex/mcp_config.toml.snippet`;
- capture-only hook examples.

The command does not print the token and does not edit Codex config.

## 3. Start Mneme

Run this in a normal terminal, not inside a restricted command sandbox:

```bash
"$MNEME_CODEX_HOME/bin/mneme-serve"
```

In another terminal:

```bash
curl -sS http://127.0.0.1:8765/v1/health
"$MNEME_CODEX_HOME/.venv/bin/mneme-codex" doctor \
  --install-root "$MNEME_CODEX_HOME"
```

Expected readiness is `READY` after the daemon is running and the local token is
loaded from `.local/mneme.env`.

## 4. Configure Codex MCP

Open the generated snippet:

```bash
cat "$MNEME_CODEX_HOME/codex/mcp_config.toml.snippet"
```

Add that `mcp_servers.mneme` block to the Codex config for this machine, then
restart Codex Desktop or open a fresh session. The snippet points Codex at
`$MNEME_CODEX_HOME/bin/mneme-mcp`, which loads the local token from the env file.
Do not paste the token into shared docs or project repos.

In a fresh Codex session, verify that Mneme MCP tools are visible before relying
on memory recall.

## 5. Run A Smoke Ingest

The setup command writes a sample transcript, so this works even when the
adapter was installed by `pip` rather than cloned as a checkout:

```bash
"$MNEME_CODEX_HOME/.venv/bin/mneme-codex" codex-ingest \
  --input "$MNEME_CODEX_HOME/.local/mneme-codex-sample-transcript.json"
```

Then use Codex MCP tools, or call REST manually, to search for:

```text
Mneme Codex global install smoke event
```

## 6. Hooks Ladder

Do not jump straight to write hooks.

Use this order:

1. No hooks: manual transcript import only.
2. Capture-only hooks.
3. Validate captured payloads.
4. Dry-run normalize payloads.
5. Import captured file into a test daemon.
6. Enable write hooks only after local proof.

Render capture-only hooks:

```bash
"$MNEME_CODEX_HOME/.venv/bin/mneme-codex" codex-hook-render-config \
  --mode capture \
  --python "$MNEME_CODEX_HOME/.venv/bin/python" \
  --capture-output "$MNEME_CODEX_HOME/.local/mneme-codex-hooks.jsonl" \
  --output "$MNEME_CODEX_HOME/codex/hooks.capture.local.json"
```

Review the file before copying it into a project `.codex/hooks.json`. Codex may
ask you to approve hooks in the UI.

Validate captured hooks:

```bash
"$MNEME_CODEX_HOME/.venv/bin/mneme-codex" codex-hook-validate \
  --input "$MNEME_CODEX_HOME/.local/mneme-codex-hooks.jsonl"
```

## Troubleshooting

| Symptom | Likely Cause | Fix |
|---|---|---|
| `Could not resolve host: github.com` | Network/sandbox blocked GitHub | Allow network or run install in a normal terminal. |
| pip cannot fetch `setuptools` | Network/sandbox blocked PyPI | Allow network or preinstall dependencies. |
| `operation not permitted` binding `127.0.0.1:8765` | Sandbox blocks local bind | Start `bin/mneme-serve` outside the sandbox. |
| Codex cannot see Mneme tools | MCP config not installed or Codex not restarted | Add the snippet and open a fresh Codex session. |
| `401` from Mneme | Missing/wrong token | Run `mneme-codex doctor`; do not print the token. |
| Hooks produce no data | Hooks not trusted or not active | Review `.codex/hooks.json`, approve in Codex, start a new session. |

## What This Does Not Do

- It does not globally modify every project.
- It does not replace Codex prompt context automatically.
- It does not enable hook writes by default.
- It does not sync daemon tokens or databases across machines.
- It does not install a background service yet; keep `bin/mneme-serve` running
  while using Mneme.
