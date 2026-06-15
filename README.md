# Mneme Codex Adapter

Codex adapter utilities for [Mneme Universal Context Service](https://github.com/johnnykor82/mneme-universal-context-service).

This package provides:

- Codex transcript import into Mneme REST ingestion.
- Codex hook capture, validation, dry-run, and REST ingestion commands.
- Codex context-preview preparation files for inspection.
- A repo-local `mneme-memory` skill and Codex setup snippets.

It does not replace Codex prompt context automatically. Current Codex command
hooks can capture/ingest events and prepare preview files; automatic prompt
insertion still requires a supported host lifecycle hook.

## Install

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install "git+https://github.com/johnnykor82/mneme-codex-adapter.git"
```

The adapter depends on the public Mneme core package.

## Run Mneme Core

```bash
export MNEME_AUTH_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
mneme serve --db .local/mneme.db --token "$MNEME_AUTH_TOKEN"
```

Optional MCP server:

```bash
mneme mcp --base-url http://127.0.0.1:8765 --token "$MNEME_AUTH_TOKEN"
```

## Adapter CLI

```bash
mneme-codex codex-ingest --input adapters/codex/transcript.example.json --token "$MNEME_AUTH_TOKEN"
mneme-codex codex-hook-capture --input - --event Stop --output .local/mneme-codex-hooks.jsonl
mneme-codex codex-hook-validate --input .local/mneme-codex-hooks.jsonl
mneme-codex codex-hook-ingest --input hook.json --event Stop --dry-run
```

See:

- [adapters/codex/MNEME_CODEX_MCP_USAGE.md](adapters/codex/MNEME_CODEX_MCP_USAGE.md)
- [adapters/codex/MNEME_CODEX_INGEST_USAGE.md](adapters/codex/MNEME_CODEX_INGEST_USAGE.md)
- [adapters/codex/MNEME_CODEX_HOOKS_USAGE.md](adapters/codex/MNEME_CODEX_HOOKS_USAGE.md)

## Tests

```bash
python -m pip install -e ".[test]"
python -m pytest -q
python -m compileall -q mneme_codex_adapter tests
```

## License

Apache License 2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).
