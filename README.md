# Mneme Codex Adapter

Codex adapter utilities for [Mneme Universal Context Service](https://github.com/johnnykor82/mneme-universal-context-service).

This package provides:

- Codex transcript import into Mneme REST ingestion.
- Codex direct-ingest hook setup plus capture, validation, dry-run, and REST ingestion commands.
- Codex context-preview preparation files for inspection.
- A `mneme-memory` Codex skill installer for long-session recall behavior.
- Codex Desktop MCP setup snippets and user-global runtime helpers.

It does not replace Codex prompt context automatically. Current Codex command
hooks can capture/ingest events and prepare preview files; automatic prompt
insertion still requires a supported host lifecycle hook.

This installs a user-global Mneme daemon, Codex MCP server config snippets,
the `mneme-memory` skill, and user-level direct-ingest Codex hooks. It is not
currently packaged as a Codex Desktop marketplace plugin.

## Install

Installing with a Codex agent? Ask it to read
[CODEX_AGENT_INSTALL.md](CODEX_AGENT_INSTALL.md) before it runs commands.

Recommended Codex Desktop path:

```bash
export MNEME_CODEX_HOME="$HOME/.mneme-codex"
python3 -m venv "$MNEME_CODEX_HOME/.venv"
"$MNEME_CODEX_HOME/.venv/bin/python" -m pip install \
  "git+https://github.com/johnnykor82/mneme-codex-adapter.git"
"$MNEME_CODEX_HOME/.venv/bin/mneme-codex" setup codex-desktop \
  --global \
  --install-root "$MNEME_CODEX_HOME" \
  --python "$MNEME_CODEX_HOME/.venv/bin/python"
"$MNEME_CODEX_HOME/.venv/bin/mneme-codex" skill install \
  --target-dir "$HOME/.codex/skills"
```

`setup codex-desktop --global` writes direct-ingest hooks to
`$HOME/.codex/hooks.json`. Codex still requires you to approve those local
command hooks in the UI and open a fresh session before they run.

Then install and start the user LaunchAgent:

```bash
"$MNEME_CODEX_HOME/.venv/bin/mneme-codex" service install \
  --install-root "$MNEME_CODEX_HOME" \
  --start
```

Check status:

```bash
"$MNEME_CODEX_HOME/.venv/bin/mneme-codex" doctor \
  --install-root "$MNEME_CODEX_HOME"
"$MNEME_CODEX_HOME/.venv/bin/mneme-codex" service status \
  --install-root "$MNEME_CODEX_HOME"
```

Full guide: [adapters/codex/CODEX_DESKTOP_QUICKSTART.md](adapters/codex/CODEX_DESKTOP_QUICKSTART.md).

Developer checkout path:

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install "git+https://github.com/johnnykor82/mneme-codex-adapter.git"
```

The adapter depends on the public Mneme core package.

## Compatibility

This adapter supports Mneme Core contract `>=0.7,<0.8`. The Core contract
version is published by Mneme Core through `/v1/health`, `/v1/capabilities`,
and OpenAPI `info.version`.

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
mneme-codex setup codex-desktop --global
mneme-codex skill install
mneme-codex doctor
mneme-codex status
mneme-codex service install --start
mneme-codex service status
mneme-codex codex-ingest --install-root "$HOME/.mneme-codex" --input adapters/codex/transcript.example.json
mneme-codex codex-hook-render-config --mode write --install-root "$HOME/.mneme-codex"
mneme-codex codex-hook-ingest --input hook.json --event Stop --dry-run
```

See:

- [adapters/codex/CODEX_DESKTOP_QUICKSTART.md](adapters/codex/CODEX_DESKTOP_QUICKSTART.md)
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
