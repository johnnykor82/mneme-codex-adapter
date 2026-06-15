# Mneme Codex Ingest Usage

This is an offline/reference Codex transcript ingestion path. It imports a provided JSON transcript file into the Mneme REST daemon so existing MCP memory tools have stored events to search and fetch.

It does not modify live Codex configuration, does not hook the current Codex process, and does not claim automatic prompt replacement.

## Start Mneme

Run the REST daemon explicitly:

```bash
mneme serve --db /path/to/mneme.db --token "$MNEME_AUTH_TOKEN"
```

## Import a Transcript

Use a local transcript JSON file:

```bash
mneme-codex codex-ingest --input transcript.json --base-url http://127.0.0.1:8765 --token "$MNEME_AUTH_TOKEN"
```

For the Codex Desktop global install, let the adapter read the token from the
install root instead:

```bash
mneme-codex codex-ingest \
  --install-root "$HOME/.mneme-codex" \
  --input "$HOME/.mneme-codex/.local/mneme-codex-sample-transcript.json"
```

An example file is available at `adapters/codex/transcript.example.json` in a
source checkout. If you installed with the Codex Desktop quickstart,
`mneme-codex setup codex-desktop --global` also writes
`.local/mneme-codex-sample-transcript.json` inside the install root.

The importer normalizes the transcript into:

- `POST /v1/sessions/start`
- `POST /v1/events`
- `POST /v1/turns/complete` when turn completion data is present

MCP remains read-side memory tooling. After import, Codex or another MCP client can use `context_search`, `recall_recent`, `fetch_event`, and the other Mneme MCP tools to inspect the stored memory.

## Transcript Shape

```json
{
  "session": {
    "session_id": "codex-session-1",
    "agent_id": "codex",
    "runtime": "CODEX",
    "project_id": "mneme",
    "started_at": "2026-06-12T12:00:00Z"
  },
  "turns": [
    {
      "turn_id": "turn-1",
      "started_at": "2026-06-12T12:00:00Z",
      "completed_at": "2026-06-12T12:00:30Z",
      "messages": [
        {"role": "USER", "text": "Continue the work."},
        {"role": "ASSISTANT", "text": "I will continue."}
      ]
    }
  ]
}
```

The adapter generates stable event ids when a message omits `event_id`. Re-importing the same transcript should count as duplicate ingestion rather than storing duplicate events.
