# MarkWeave MCP — Design

Date: 2026-08-13
Status: approved (sections 1–2 approved in conversation; 3–4 recorded here at user request to proceed)
Supersedes nothing. Implements `docs/markweave-mcp-minimal-plan-v2.md` with the deviations recorded below.

## Goal

A small MCP server exposing an existing Obsidian vault and its existing Graphify graph as MCP tools. Kiro Crew (running in Docker on this Mac) is the first client. The server owns path safety, search, safe writes, and graph queries — nothing else.

## Ground truth discovered

| Fact | Value |
|---|---|
| Vault root | `/Users/seoyeongki/Dropbox/personal/backup/메모/obsidian/dropbox` |
| Markdown files | 445 notes, 3.7 MB of text (the 104 MB total is images) |
| Graph | `graphify-out/graph.json`, 3.3 MB, 2308 nodes / 2771 links / 60 hyperedges |
| graphify | PyPI `graphifyy` 0.9.35, pure Python, at `~/.local/bin/graphify` |
| ripgrep | **not installed** — `rg` on this machine is only a shell shim |
| Vault folders | `acme/`, `TODO(할 일)/`, `개인메모/`, `manual/`, `personal/`, `images/`, `Ink/` |

The vault's own `CLAUDE.md` names `앱/remotely-save/obsidian` as canonical. That is stale and wrong; the path above is authoritative.

## Deviations from the plan

1. **No ripgrep.** A pure-Python scan of the whole corpus takes 0.22 s. Dropping ripgrep removes a binary dependency, a subprocess, a timeout, and an output cap. Plan §6 assumed ripgrep; SQLite FTS5 stays excluded as the plan says.
2. **Six graph tools, not one.** graphify exposes `query`, `explain`, `path`, `affected`, `god-nodes`; all are wrapped, plus `graph_status`. Plan §5 listed only `query_graph`.
3. **NFC normalization is mandatory.** macOS stores Korean filenames as NFD; MCP JSON carries NFC. Not normalizing means `"쿠버네티스.md"` fails to match the identical file on disk.
4. **No HTTP auth.** The container sits on Kiro Crew's internal Docker network (`npm-proxy`) with no published port, which is the condition under which plan §10.4 says auth is unnecessary.
5. **FastMCP 3.4.7 as the server framework.** The official `mcp` SDK is at 2.0.0, where the vendored `mcp.server.fastmcp` module no longer exists and the equivalent is `mcp.server.MCPServer`. The standalone FastMCP project is a separate, current package (3.4.7) and is what this server builds on; `mcp` comes in transitively.

## Architecture

One container, one process, seven modules:

| Module | Responsibility |
|---|---|
| `config.py` | Env-only settings; frozen at startup |
| `errors.py` | The error taxonomy below, as exception types |
| `paths.py` | Vault-relative path validation and NFC handling |
| `search.py` | Pure-Python note scan and snippet extraction |
| `notes.py` | Read, create, append, update; sha256; atomic replace |
| `graph.py` | Fixed-argv graphify subprocess wrapper |
| `server.py` | Tool registration and schemas only — no logic |

Deployment: `python:3.14-slim`, `uv tool install graphifyy==0.9.35` pinned to match the host that builds the graph. Vault bind-mounted read-write at `/vault`; `graphify-out/` rides along inside it. Joined to Kiro Crew's `npm-proxy` Docker network as `markweave-mcp`, reachable at `http://markweave-mcp:8000/mcp`. No published host port outside development.

Config, from environment only, never from an MCP request: `MARKWEAVE_VAULT`, `MARKWEAVE_GRAPH`, `MARKWEAVE_MAX_RESULTS`, `MARKWEAVE_MAX_SNIPPET`, `MARKWEAVE_MAX_RESPONSE_BYTES`, `MARKWEAVE_MAX_FILE_BYTES`, `MARKWEAVE_GRAPH_TIMEOUT`.

## Tools

Vault: `search_notes(query, limit?, folder?)`, `read_note(path)`, `create_note(path, content)`, `append_note(path, content, expected_sha256)`, `update_note(path, content, expected_sha256)`.

Graph: `query_graph`, `explain_node`, `graph_path`, `affected_nodes`, `god_nodes`, `graph_status`.

Graph tools return `{ok, text, truncated, graph_generated_at}` — graphify emits prose, and parsing it would couple the server to another project's output formatting.

Excluded, per plan §5.2: `delete_note`, `move_note`, `rename_note`, `bulk_update`, `graph_rebuild`, `shell_execute`, arbitrary file reads.

## 3. Safety and error handling

**Path validation**, applied to every path argument in order: reject absolute paths and any segment equal to `..`; NFC-normalize; join to the vault root; `realpath` the result; assert the result is inside the vault root; assert a `.md` suffix. `realpath` after joining is what catches a symlink inside the vault pointing outside it — a lexical check alone does not.

**Write safety.** `create_note` fails if the target exists. `append_note` and `update_note` read the file, compute sha256, and compare against `expected_sha256`; a mismatch returns a conflict error and writes nothing. All writes go to a temp file created in the *same directory* as the target, then `os.replace` — same filesystem, so the rename is atomic. Parent directories are created only inside the vault.

**Subprocess safety.** graphify is invoked as an argv list with `shell=False`. The subcommand is selected from a fixed dict; `--graph` comes from config. User text is a positional element, never interpolated. Timeout enforced; stdout and stderr are capped and marked `truncated` when clipped.

**Failure isolation.** A missing, stale, corrupt, or timing-out graph must never affect the five vault tools. `graph_status` reports `{available, graph_path, generated_at, latest_markdown_mtime, stale}` and returns `available: false` rather than raising.

**Error taxonomy**, each mapping to a distinct MCP error message: `PathOutsideVault`, `NotMarkdown`, `NoteNotFound`, `NoteExists`, `ShaMismatch`, `FileTooLarge`, `GraphUnavailable`, `GraphTimeout`.

## 4. Testing

`pytest`, with each test building a real temporary vault on disk — no mocking of the filesystem, since the filesystem semantics (symlinks, atomic rename, NFD filenames) are precisely what is under test. graphify is faked with a small executable script for subprocess tests, so the suite needs neither the real binary nor the 3.3 MB graph.

Required cases, from plan §15 plus the deviations:

- `../` and absolute paths rejected
- symlink inside the vault pointing outside rejected
- non-`.md` write rejected
- NFD filename on disk found by NFC query
- `create_note` on an existing path fails
- `append_note` / `update_note` with a wrong sha256 returns a conflict and leaves the file byte-identical
- concurrent-write simulation: read, external modification, then write with the stale sha → conflict
- search respects `folder`, result limit, and snippet cap
- graphify timeout returns a tool error while the server stays up
- graphify non-zero exit returns `ok: false`, not an exception
- `graph_status` reports `stale: true` when a note is newer than the graph
- every vault tool still works with `MARKWEAVE_GRAPH` pointing at a nonexistent file

## Out of scope

Everything in plan §16, plus: no scheduler, no filesystem watcher, no automatic graphify runs after writes. Graph refresh stays manual on the host.

## Cleanup of the previous implementation

The earlier MarkWeave is being discarded, not migrated. To be removed after a backup tarball: `~/.local/share/markweave/` (15.5 MB SQLite with FTS5 and a `sessions` table), `~/.config/markweave/`, `~/Library/CloudStorage/Dropbox/앱/markweave/`, the empty `.markweave-doctor/` in the vault, and `graphify-out/markweave-overlay.json` (229 KB, 347 structural nodes, generated 2026-08-11).
