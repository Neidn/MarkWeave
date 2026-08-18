# MarkWeave MCP

An MCP server that exposes an existing Obsidian vault and its existing Graphify graph as tools. Kiro Crew is the first client; any MCP-capable agent can connect to the same server.

The vault is the source of truth. `graph.json` is derived data that MarkWeave only reads — it never rebuilds the graph, and writing a note never triggers a graphify run.

## Tools

**Vault**

| Tool | Arguments |
|---|---|
| `search_notes` | `query`, `limit?`, `folder?` |
| `read_note` | `path` |
| `create_note` | `path`, `content` |
| `append_note` | `path`, `content`, `expected_sha256` |
| `update_note` | `path`, `content`, `expected_sha256` |
| `move_note` | `source`, `destination`, `expected_sha256` |

**Graph** — `query_graph`, `explain_node`, `graph_path`, `affected_nodes`, `god_nodes`, `graph_status`.

There is deliberately no delete, bulk-update, graph-rebuild, or shell tool. `move_note` handles renaming too, since a rename is a move within one folder.

## Safety

- Paths are vault-relative. `..`, absolute paths, non-`.md` files, and symlinks leading outside the vault are rejected after `realpath` resolution.
- `append_note`, `update_note`, and `move_note` require the note's current SHA-256. If the file changed on disk — Obsidian, Dropbox sync, another agent — the write is refused and nothing is modified.
- `move_note` never overwrites: an existing destination is an error. A case-only or NFC/NFD-only rename is still allowed, because on macOS the destination "already exists" only in the sense that it is the same file.
- Writes go to a temporary file in the target's own directory and land via `os.replace`, so a reader never sees a partial note.
- graphify runs with `shell=False` and a fixed argument list. The graph path comes from configuration; no tool parameter can change it.
- A missing, stale, or failing graph never disables the vault tools.

## Configuration

Environment only — none of these are reachable from an MCP request.

| Variable | Default |
|---|---|
| `MARKWEAVE_VAULT` | *(required)* |
| `MARKWEAVE_GRAPH` | `$MARKWEAVE_VAULT/graphify-out/graph.json` |
| `MARKWEAVE_GRAPHIFY_BIN` | `graphify` |
| `MARKWEAVE_MAX_RESULTS` | `20` |
| `MARKWEAVE_MAX_SNIPPET` | `200` |
| `MARKWEAVE_MAX_RESPONSE_BYTES` | `64000` |
| `MARKWEAVE_MAX_FILE_BYTES` | `2097152` |
| `MARKWEAVE_GRAPH_TIMEOUT` | `30` |
| `MARKWEAVE_STALE_AFTER_HOURS` | `24` |
| `MARKWEAVE_HOST` / `MARKWEAVE_PORT` / `MARKWEAVE_PATH` | `0.0.0.0` / `8000` / `/mcp` |

## Running

```bash
cp .env.example .env          # set MARKWEAVE_VAULT_HOST and KIROCREW_NETWORK
docker compose up -d --build
```

The service publishes no port. Kiro Crew reaches it on the shared Docker network:

```
http://markweave-mcp:8000/mcp
```

Register that URL as a Streamable HTTP MCP server in Kiro Crew, then allow only the tools that agent needs.

To debug locally, uncomment the `ports` block in `docker-compose.yml` and point MCP Inspector at `http://127.0.0.1:8000/mcp`.

### Without Docker

```bash
uv sync
MARKWEAVE_VAULT=/path/to/vault uv run markweave-mcp
```

## Development

```bash
uv sync
uv run pytest                      # whole suite
uv run pytest tests/test_paths.py  # one file
uv run pytest -k sha256            # one behaviour
```

Tests build real vaults in temporary directories and fake graphify with a small shell script, so no real graph or graphify install is needed.

## Keeping the graph fresh

MarkWeave never runs graphify. Refresh on the host when you want it:

```bash
graphify update /path/to/vault
```

`graph_status` reports how far the graph has fallen behind:

```json
{"notes_newer_than_graph": 3, "lag_hours": 1.4, "stale_after_hours": 24, "stale": false}
```

Any edit makes some note newer than the graph, so "newer than the graph" on its own would report stale almost always. `stale` turns true only once `lag_hours` exceeds `MARKWEAVE_STALE_AFTER_HOURS`.

The graphify version pinned in the `Dockerfile` should match the host version that builds the graph.
