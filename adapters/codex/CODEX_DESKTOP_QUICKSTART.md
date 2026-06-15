# Codex Desktop Quickstart

This guide installs Mneme for one macOS user account so Codex Desktop can use
Mneme memory tools from any project on that machine.

It does not enable automatic Codex prompt replacement. Current Codex support is
MCP memory tools plus explicit hook capture/ingest commands.

This installs a user-global Mneme daemon plus Codex MCP server config. It is
not currently packaged as a Codex Desktop marketplace plugin.

If you want a Codex agent to do the installation for you, ask it to read
[`CODEX_AGENT_INSTALL.md`](../../CODEX_AGENT_INSTALL.md) before it runs
commands.

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
- `mneme.toml` for non-secret daemon/provider settings;
- `bin/mneme-serve`;
- `bin/mneme-mcp`;
- `codex/mcp_config.toml.snippet`;
- capture-only hook examples.

The command does not print the token and does not edit Codex config.

## 3. Start Mneme

Recommended macOS path:

```bash
"$MNEME_CODEX_HOME/.venv/bin/mneme-codex" service install \
  --install-root "$MNEME_CODEX_HOME" \
  --start
```

Check the service and daemon:

```bash
curl -sS http://127.0.0.1:8765/v1/health
"$MNEME_CODEX_HOME/.venv/bin/mneme-codex" doctor \
  --install-root "$MNEME_CODEX_HOME"
"$MNEME_CODEX_HOME/.venv/bin/mneme-codex" service status \
  --install-root "$MNEME_CODEX_HOME"
```

Expected readiness is `READY` after the daemon is running and the local token is
loaded from `.local/mneme.env`.

Foreground fallback for troubleshooting:

```bash
"$MNEME_CODEX_HOME/bin/mneme-serve"
```

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
  --install-root "$MNEME_CODEX_HOME" \
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

## 7. Configure Providers

The default install starts in minimal local mode. For production-like semantic
memory, configure embeddings and verify them before relying on recall quality.
Reranker and LLM enrichment are optional quality layers.

Put non-secret settings in:

```bash
"$MNEME_CODEX_HOME/mneme.toml"
```

Put API keys only in:

```bash
"$MNEME_CODEX_HOME/.local/mneme.env"
```

Common env names:

```bash
MNEME_REQUIRE_EMBEDDINGS=true
MNEME_EMBEDDINGS_ENABLED=true
MNEME_EMBEDDING_PROVIDER=openai_compatible
MNEME_EMBEDDING_MODEL=<embedding-model>
MNEME_EMBEDDING_BASE_URL=<provider-base-url>
MNEME_EMBEDDING_API_KEY=<secret>
MNEME_RERANKER_ENABLED=true
MNEME_RERANKER_PROVIDER=<reranker-provider>
MNEME_RERANKER_MODEL=<reranker-model>
MNEME_RERANKER_BASE_URL=<provider-base-url>
MNEME_RERANKER_API_KEY=<secret>
MNEME_LLM_ENRICHMENT_ENABLED=true
MNEME_LLM_PROVIDER=openai_compatible
MNEME_LLM_MODEL=<llm-model>
MNEME_LLM_BASE_URL=<provider-base-url>
MNEME_LLM_API_KEY=<secret>
```

Restart after changes:

```bash
"$MNEME_CODEX_HOME/.venv/bin/mneme-codex" service stop \
  --install-root "$MNEME_CODEX_HOME"
"$MNEME_CODEX_HOME/.venv/bin/mneme-codex" service start \
  --install-root "$MNEME_CODEX_HOME"
"$MNEME_CODEX_HOME/.venv/bin/mneme-codex" doctor \
  --install-root "$MNEME_CODEX_HOME"
```

In `doctor`, check `provider_capabilities.supports_embeddings`,
`supports_reranking`, and `supports_llm_enrichment`.

## Troubleshooting

| Symptom | Likely Cause | Fix |
|---|---|---|
| `Could not resolve host: github.com` | Network/sandbox blocked GitHub | Allow network or run install in a normal terminal. |
| pip cannot fetch `setuptools` | Network/sandbox blocked PyPI | Allow network or preinstall dependencies. |
| `operation not permitted` binding `127.0.0.1:8765` | Sandbox blocks local bind | Start `bin/mneme-serve` outside the sandbox. |
| Service fails to start | launchd rejected the plist or daemon crashed | Run `mneme-codex service logs --install-root "$MNEME_CODEX_HOME"`. |
| Codex cannot see Mneme tools | MCP config not installed or Codex not restarted | Add the snippet and open a fresh Codex session. |
| `401` from Mneme | Missing/wrong token | Run `mneme-codex doctor`; do not print the token. |
| Hooks produce no data | Hooks not trusted or not active | Review `.codex/hooks.json`, approve in Codex, start a new session. |

## What This Does Not Do

- It does not globally modify every project.
- It does not replace Codex prompt context automatically.
- It does not enable hook writes by default.
- It does not sync daemon tokens or databases across machines.
