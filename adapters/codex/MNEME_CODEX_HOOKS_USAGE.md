# Codex Hooks Usage

This is the first safe hook-ingestion surface for Codex dogfood. It is disabled by default.
Local real Codex Desktop capture has been validated, but user-facing write
setup should still go through dry-run and a local REST-ingestion plus MCP-recall
smoke test before publication.
Real Codex hook payloads should still be revalidated per machine before writes.

## Capture First

Capture real Codex hook payloads into an untracked local JSONL file before
enabling writes:

```bash
mneme-codex codex-hook-capture --input - --event Stop --output .local/mneme-codex-hooks.jsonl
```

For a real local Codex hook rehearsal, generate a machine-local capture config
with an explicit Python runner. This avoids relying on Codex inheriting a shell
`PATH` that can find `mneme`:

```bash
.venv/bin/python -m mneme_codex_adapter.cli codex-hook-render-config \
  --mode capture \
  --python "$(pwd)/.venv/bin/python" \
  --output .local/codex_hooks.capture.local.json
```

Review the generated `.local/codex_hooks.capture.local.json` file before
trusting it in Codex. It may contain machine-local paths and should not be
committed. The generated JSON uses the official Codex hook shape with a
top-level `hooks` object.

For a trusted local project rehearsal, render the same capture config directly
to the project-local Codex hook path:

```bash
.venv/bin/python -m mneme_codex_adapter.cli codex-hook-render-config \
  --mode capture \
  --python "$(pwd)/.venv/bin/python" \
  --output .codex/hooks.json
```

`.codex/hooks.json` is intentionally gitignored because it can contain
machine-local paths. Start a new trusted Codex session in this project after
reviewing the generated file; Codex may ask you to review or trust the hooks
before they run.

Validate the captured payloads:

```bash
mneme-codex codex-hook-validate --input .local/mneme-codex-hooks.jsonl
```

The validation report does not include raw content. It checks whether payloads
carry enough stable fields for an enable-ready setup: session id or thread id,
project/cwd, capture timestamp, and usable Codex content fields such as
`prompt`, `tool_name`, `tool_input`, `tool_response`,
`last_assistant_message`, `source`, `cwd`, or `model`.

## Dry-Run First

Start with a JSON payload and inspect the normalized Mneme payloads:

```bash
mneme-codex codex-hook-ingest --input hook.json --event Stop --dry-run
```

Use `--input -` when a Codex command hook passes JSON on standard input:

```bash
mneme-codex codex-hook-ingest --input - --event PostCompact --dry-run
```

Dry-run first is required for new hook events. Confirm `session_id`, `turn_id`,
`project_id`, timestamp, useful content text, and event id stability before
enabling writes.

## Write Path

When verified, remove `--dry-run` and point the command at the local Mneme REST
daemon:

```bash
mneme-codex codex-hook-ingest \
  --input hook.json \
  --event Stop \
  --base-url http://127.0.0.1:8765 \
  --token "$MNEME_AUTH_TOKEN"
```

REST ingestion remains canonical. The command calls:

- `POST /v1/sessions/start`
- `POST /v1/events`

MCP remains read-only for this Codex slice. This command does not add an MCP
write tool and does not replace Codex prompt context.

To replay a local capture file into a test daemon:

```bash
mneme-codex codex-hook-import-capture \
  --input .local/mneme-codex-hooks.jsonl \
  --base-url http://127.0.0.1:8765 \
  --token "$MNEME_AUTH_TOKEN"
```

## Context Preview File

Current documented Codex command hooks include `UserPromptSubmit` and
`PreCompact`, but not a prompt/context-build hook that can replace the model
input. `prompt` and `agent` hook handlers are parsed but skipped today, so this
adapter treats automatic prompt insertion as unsupported.

Use `UserPromptSubmit` to ask Mneme what it would prepare, then write that
response to an untracked local JSONL file for inspection:

```bash
mneme-codex codex-hook-prepare-preview \
  --input .local/mneme-codex-hooks.jsonl \
  --event UserPromptSubmit \
  --output .local/mneme-codex-context-preview.jsonl \
  --base-url http://127.0.0.1:8765 \
  --token "$MNEME_AUTH_TOKEN"
```

The preview record includes the `/v1/context/prepare` request, the prepared
Mneme response, trace id, warnings, and a marker that Codex prompt injection is
not supported by current command hooks.

Render a per-machine hook config that prepares this preview automatically on
each submitted user prompt:

```bash
.venv/bin/python -m mneme_codex_adapter.cli codex-hook-render-context-preview-config \
  --python "$(pwd)/.venv/bin/python" \
  --preview-output .local/mneme-codex-context-preview.jsonl \
  --output .local/codex_hooks.context_preview.local.json
```

Review before copying or merging into `.codex/hooks.json`; changing
`.codex/hooks.json` requires Codex hook trust review again.

## Trust Boundary

Codex hooks are local command execution. Project-local hook files should be
reviewed and trusted by the user before use. Do not enable automatic writes from
unknown or untested payload formats.

## Multi-Machine Codex Setup

If two Codex machines share hook examples through symlinks, do not assume a hook
validated on one machine is installed, trusted, or safe on the other. Hook
approval, local paths, tokens, daemon reachability, and captured payload files
are per-machine.

For the second machine, repeat capture-only validation locally:

```bash
mneme-codex codex-hook-capture --input - --event Stop --output .local/mneme-codex-hooks.jsonl
mneme-codex codex-hook-validate --input .local/mneme-codex-hooks.jsonl
```

The current hook contract example is
`adapters/codex/codex_hooks.contract.example.json`. It intentionally keeps hook
commands in `--dry-run` mode until the validated write path has a local smoke
test.

For payload discovery, start from
`adapters/codex/codex_hooks.capture.example.json`. It captures raw hook payloads
to `.local/mneme-codex-hooks.jsonl` and performs no writes to Mneme.

You can also render a per-machine capture config on each machine:

```bash
.venv/bin/python -m mneme_codex_adapter.cli codex-hook-render-config \
  --mode capture \
  --python "$(pwd)/.venv/bin/python" \
  --output .local/codex_hooks.capture.local.json
```

## Future GitHub Users

Future GitHub users should be able to install Mneme, configure MCP, inspect hook
payloads with dry-run, then enable hook ingestion with copyable commands. Avoid
private local paths in reusable hook docs and examples.
