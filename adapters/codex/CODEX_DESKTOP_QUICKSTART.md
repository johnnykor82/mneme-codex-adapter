# Codex Desktop Quickstart

This guide installs Mneme for one macOS user account so Codex Desktop can use
Mneme memory tools from any project on that machine.

It does not enable automatic Codex prompt replacement. Current Codex support is
MCP memory tools plus direct-ingest Codex hooks that write events through the
adapter to Mneme REST.

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
files and install user-level direct-ingest hooks, then install the
`mneme-memory` Codex skill:

```bash
"$MNEME_CODEX_HOME/.venv/bin/mneme-codex" setup codex-desktop \
  --global \
  --install-root "$MNEME_CODEX_HOME" \
  --python "$MNEME_CODEX_HOME/.venv/bin/python"
"$MNEME_CODEX_HOME/.venv/bin/mneme-codex" skill install \
  --target-dir "$HOME/.codex/skills"
```

This creates local files under `$MNEME_CODEX_HOME`, including:

- `.local/mneme.env` with `MNEME_AUTH_TOKEN`;
- `.local/mneme.db` path for the daemon;
- `mneme.toml` for non-secret daemon/provider settings;
- `bin/mneme-serve`;
- `bin/mneme-mcp`;
- `codex/mcp_config.toml.snippet`;
- `codex/hooks.write.json` with the same direct-ingest hooks installed into
  `$HOME/.codex/hooks.json`;
- `codex/hooks.capture.example.json` as an optional diagnostic fallback.

The setup command does not print the token. The installed hooks use
`--install-root "$MNEME_CODEX_HOME"` so the adapter reads the local token from
`.local/mneme.env`; the bearer token is not embedded in Codex config.
The skill install writes `mneme-memory` to
`$HOME/.codex/skills/mneme-memory/SKILL.md`. This skill is required for the
expected Codex behavior in fresh sessions: it tells the agent when to call Mneme
MCP tools at session start, resume, after compaction, and during long work.
If `~/.codex/skills` is a symlink to a shared skills folder, install it there
once and verify each machine sees it after Codex restart.

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

## 6. Approve And Verify Hooks

`setup codex-desktop --global` writes direct-ingest hooks to:

```bash
$HOME/.codex/hooks.json
```

Codex treats hooks as local command execution. Approve the 5 Mneme hooks in
Codex settings, then open a fresh Codex session. The active commands should use
`codex-hook-ingest`, `--install-root "$MNEME_CODEX_HOME"`, and no literal
bearer token.

After restart, send a normal prompt in Codex and verify it appears in Mneme
through MCP search. If MCP is not available yet, run:

```bash
"$MNEME_CODEX_HOME/.venv/bin/mneme-codex" doctor \
  --install-root "$MNEME_CODEX_HOME"
```

Capture-only hooks remain available for debugging unusual Codex payloads:

```bash
"$MNEME_CODEX_HOME/.venv/bin/mneme-codex" codex-hook-render-config \
  --mode capture \
  --python "$MNEME_CODEX_HOME/.venv/bin/python" \
  --capture-output "$MNEME_CODEX_HOME/.local/mneme-codex-hooks.jsonl" \
  --output "$MNEME_CODEX_HOME/codex/hooks.capture.local.json"
"$MNEME_CODEX_HOME/.venv/bin/mneme-codex" codex-hook-validate \
  --input "$MNEME_CODEX_HOME/.local/mneme-codex-hooks.jsonl"
```

## 7. Configure Providers

The default install starts in minimal local mode. For production-like semantic
memory, configure embeddings, reranking, and LLM enrichment, then verify all
three before relying on recall quality. A healthy daemon and visible MCP tools
prove the minimal path; they do not prove all provider layers are active.

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
`supports_reranking`, and `supports_llm_enrichment`. Also check provider
details from `/v1/capabilities`: `available` is configuration/credential based,
while `live_status` and `live_health_checked` show observed provider outcomes in
the current daemon process.

Full-provider acceptance checks:

- `fetch_event` reports `ingestion.embedding_status: INDEXED` for a new event;
- the session cost report shows `embedding_items > 0`;
- search results show reranking when a reranker is configured;
- LLM enrichment increments `enrichment_calls` without enrichment failures.

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
- It does not bypass Codex hook approval; the user still approves local commands.
- It does not sync daemon tokens or databases across machines.
