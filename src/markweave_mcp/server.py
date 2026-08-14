"""MCP tool registration.

This module wires tools to the modules that do the work and holds no logic of
its own. Vault root and graph path are closed over from Settings, so no tool
signature exposes them.
"""

from fastmcp import FastMCP
from mcp.types import ToolAnnotations

from . import notes, search
from .config import Settings, load_settings
from .graph import GraphClient

INSTRUCTIONS = """MarkWeave exposes an Obsidian vault and its Graphify graph.

Search or query the graph before answering questions about past notes. Record
only explicit memory requests, settled decisions, and tasks. Before changing an
existing note, call read_note to obtain its current sha256 and pass it back as
expected_sha256 — a mismatch means someone else edited the file. Never claim a
note was written unless the tool returned successfully; report the path it
returned.
"""


# Annotations tell any MCP client which tools mutate the vault, so a client can
# gate them without relying on its own per-server allowlist. Kiro Crew rewrites
# its allowlist on every restart, which is exactly why this belongs server-side.
READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True)

# create_note refuses to touch an existing path, so it cannot destroy anything.
CREATES = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False)

# append_note and update_note change notes that already exist.
MUTATES = ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False)


def build_server(settings: Settings) -> FastMCP:
    mcp = FastMCP("markweave", instructions=INSTRUCTIONS)
    vault = settings.vault_root
    graph = GraphClient(
        executable=settings.graphify_bin,
        graph_path=settings.graph_path,
        timeout=settings.graph_timeout,
        max_output_bytes=settings.max_response_bytes,
        stale_after_hours=settings.stale_after_hours,
    )

    @mcp.tool(annotations=READ_ONLY)
    def search_notes(query: str, limit: int | None = None, folder: str | None = None) -> list[dict]:
        """Search note filenames and bodies. Optionally scope to a vault folder."""
        return search.search_notes(
            vault,
            query,
            limit=limit or settings.max_results,
            folder=folder,
            max_snippet=settings.max_snippet,
        )

    @mcp.tool(annotations=READ_ONLY)
    def read_note(path: str) -> dict:
        """Read a note and its current sha256, required for any later edit."""
        return notes.read_note(vault, path, max_bytes=settings.max_file_bytes)

    @mcp.tool(annotations=CREATES)
    def create_note(path: str, content: str) -> dict:
        """Create a new note. Fails if the path already exists."""
        return notes.create_note(vault, path, content, max_bytes=settings.max_file_bytes)

    @mcp.tool(annotations=MUTATES)
    def append_note(path: str, content: str, expected_sha256: str) -> dict:
        """Append to a note, only if its sha256 still matches expected_sha256."""
        return notes.append_note(
            vault, path, content, expected_sha256, max_bytes=settings.max_file_bytes
        )

    @mcp.tool(annotations=MUTATES)
    def update_note(path: str, content: str, expected_sha256: str) -> dict:
        """Replace a note's contents, only if its sha256 still matches expected_sha256."""
        return notes.update_note(
            vault, path, content, expected_sha256, max_bytes=settings.max_file_bytes
        )

    @mcp.tool(annotations=READ_ONLY)
    def query_graph(
        question: str,
        budget: int = 2000,
        dfs: bool = False,
        context: list[str] | None = None,
    ) -> dict:
        """Traverse the note graph to answer a question about how notes relate."""
        return graph.query(question, budget=budget, dfs=dfs, context=context)

    @mcp.tool(annotations=READ_ONLY)
    def explain_node(node: str) -> dict:
        """Explain one graph node and its neighbours in plain language."""
        return graph.explain(node)

    @mcp.tool(annotations=READ_ONLY)
    def graph_path(source: str, target: str) -> dict:
        """Show the shortest path between two nodes in the graph."""
        return graph.path(source, target)

    @mcp.tool(annotations=READ_ONLY)
    def affected_nodes(node: str, relation: str | None = None, depth: int | None = None) -> dict:
        """List nodes impacted by a given node, traversing edges in reverse."""
        return graph.affected(node, relation=relation, depth=depth)

    @mcp.tool(annotations=READ_ONLY)
    def god_nodes(top: int = 10) -> dict:
        """List the most connected nodes — the hubs of the vault."""
        return graph.god_nodes(top=top)

    @mcp.tool(annotations=READ_ONLY)
    def graph_status() -> dict:
        """Report graph availability and whether it is older than the newest note."""
        return graph.status(vault)

    return mcp


def main() -> None:
    import os

    build_server(load_settings()).run(
        transport="http",
        host=os.environ.get("MARKWEAVE_HOST", "0.0.0.0"),
        port=int(os.environ.get("MARKWEAVE_PORT", "8000")),
        path=os.environ.get("MARKWEAVE_PATH", "/mcp"),
    )


if __name__ == "__main__":
    main()
