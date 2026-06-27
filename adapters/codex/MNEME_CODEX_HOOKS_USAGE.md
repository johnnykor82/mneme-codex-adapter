# Codex Hooks Usage

`mneme-codex setup codex-desktop --global` installs user-level direct-ingest hooks by default.
The hooks call the Codex adapter, and the adapter writes events to Mneme Core
through REST.

```text
Codex hook event -> mneme-codex codex-hook-ingest -> Mneme REST -> MCP/REST reads
```

MCP remains read-only for Codex. Hook writes use REST ingestion and do not
replace Codex prompt context automatically.

## Installed Write Hooks

Setup writes:

```bash
$HOME/.codex/hooks.json
```

It also writes a copy of the same config to:

```bash
$MNEME_CODEX_HOME/codex/hooks.write.json
```

Each installed command uses the virtualenv Python runner and the install root,
for example:

```bash
$MNEME_CODEX_HOME/.venv/bin/python -m mneme_codex_adapter.cli codex-hook-ingest \
  --input - \
  --event UserPromptSubmit \
  --base-url http://127.0.0.1:8765 \
  --install-root "$MNEME_CODEX_HOME" \
  --timeout 10
```

The hook command does not embed the bearer token. The adapter resolves it from
`$MNEME_CODEX_HOME/.local/mneme.env`.

Codex still treats hooks as local command execution. The user must approve the installed hooks in Codex settings and open a fresh session before they run.

## Verification

After setup, service start, hook approval, and Codex restart:

1. Send a normal prompt in Codex.
2. Use Mneme MCP `resolve_session` for the current project/session.
3. Search for that prompt with `context_search`.

A working install stores the prompt as a `CODEX_HOOK` event. `PostToolUse`,
`PostCompact`, `Stop`, and `SessionStart` events should follow the same path
when Codex emits them.

`mneme-codex doctor --install-root "$MNEME_CODEX_HOME"` should report `READY`
once the daemon and token are reachable.

## Rendering Hooks Manually

Normally setup is enough. To render the same write hooks without installing
them:

```bash
mneme-codex codex-hook-render-config \
  --mode write \
  --python "$MNEME_CODEX_HOME/.venv/bin/python" \
  --base-url http://127.0.0.1:8765 \
  --install-root "$MNEME_CODEX_HOME" \
  --output "$MNEME_CODEX_HOME/codex/hooks.write.json"
```

Use `--skip-user-hooks` on setup only when a machine must not install Codex
hooks automatically:

```bash
mneme-codex setup codex-desktop \
  --global \
  --install-root "$MNEME_CODEX_HOME" \
  --python "$MNEME_CODEX_HOME/.venv/bin/python" \
  --skip-user-hooks
```

## Capture-Only Fallback

Capture-only remains available for diagnosing a new or unusual Codex hook
payload shape. It is no longer the default GitHub install path.

```bash
mneme-codex codex-hook-render-config \
  --mode capture \
  --python "$MNEME_CODEX_HOME/.venv/bin/python" \
  --capture-output "$MNEME_CODEX_HOME/.local/mneme-codex-hooks.jsonl" \
  --output "$MNEME_CODEX_HOME/codex/hooks.capture.local.json"

mneme-codex codex-hook-validate \
  --input "$MNEME_CODEX_HOME/.local/mneme-codex-hooks.jsonl"
```

For one-off payload checks, dry-run normalization is still useful:

```bash
mneme-codex codex-hook-ingest --input hook.json --event Stop --dry-run
```

To replay a capture file into a local daemon:

```bash
mneme-codex codex-hook-import-capture \
  --input "$MNEME_CODEX_HOME/.local/mneme-codex-hooks.jsonl" \
  --base-url http://127.0.0.1:8765 \
  --install-root "$MNEME_CODEX_HOME"
```

## Context Preview File

Current documented Codex command hooks do not provide a prompt/context-build
hook that can replace the model input. This adapter can prepare a context
preview file for inspection, but automatic prompt insertion remains unsupported.
Codex prompt injection is not supported by current command hooks.

```bash
mneme-codex codex-hook-prepare-preview \
  --input hook.json \
  --event UserPromptSubmit \
  --output "$MNEME_CODEX_HOME/.local/mneme-codex-context-preview.jsonl" \
  --base-url http://127.0.0.1:8765 \
  --install-root "$MNEME_CODEX_HOME"
```

The preview record includes the `/v1/context/prepare` request, the prepared
Mneme response, trace id, warnings, and a marker that Codex prompt injection is
not supported by current command hooks.

## Trust Boundary

Codex hooks are local command execution. Review the generated commands before
approval. Keep tokens in `$MNEME_CODEX_HOME/.local/mneme.env`; do not paste
bearer tokens into hook files, shared docs, or project repositories.

If multiple Codex machines share files through symlinks, still approve and
verify hooks per machine. Hook approval, local paths, tokens, daemon reachability,
provider availability, and databases are machine-local.
