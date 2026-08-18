import asyncio

from markweave_mcp.config import load_settings
from markweave_mcp.server import build_server

EXPECTED_TOOLS = {
    "search_notes",
    "read_note",
    "create_note",
    "append_note",
    "update_note",
    "move_note",
    "query_graph",
    "explain_node",
    "graph_path",
    "affected_nodes",
    "god_nodes",
    "graph_status",
}

# move_note was added deliberately (a move is reversible); delete stays out.
# rename_note is absent because move_note covers renaming — a rename is a move
# within one folder — not because renaming is disallowed.
EXCLUDED_TOOLS = {
    "delete_note",
    "rename_note",
    "bulk_update",
    "graph_rebuild",
    "shell_execute",
}


def tool_names(vault):
    settings = load_settings({"MARKWEAVE_VAULT": str(vault)})
    server = build_server(settings)
    return {tool.name for tool in asyncio.run(server.list_tools())}


def test_exposes_exactly_the_designed_tools(vault):
    assert tool_names(vault) == EXPECTED_TOOLS


def test_does_not_expose_destructive_tools(vault):
    assert tool_names(vault) & EXCLUDED_TOOLS == set()


def test_graph_path_is_not_a_tool_parameter(vault):
    """The graph location is configuration; a client must never set it."""
    settings = load_settings({"MARKWEAVE_VAULT": str(vault)})
    server = build_server(settings)

    for tool in asyncio.run(server.list_tools()):
        properties = (tool.parameters or {}).get("properties", {})
        assert "graph" not in properties
        assert "graph_path" not in properties


def test_vault_root_is_not_a_tool_parameter(vault):
    settings = load_settings({"MARKWEAVE_VAULT": str(vault)})
    server = build_server(settings)

    for tool in asyncio.run(server.list_tools()):
        properties = (tool.parameters or {}).get("properties", {})
        assert "vault" not in properties
        assert "vault_root" not in properties


def test_write_tools_require_expected_sha256(vault):
    settings = load_settings({"MARKWEAVE_VAULT": str(vault)})
    server = build_server(settings)
    tools = {tool.name: tool for tool in asyncio.run(server.list_tools())}

    for name in ("append_note", "update_note", "move_note"):
        required = (tools[name].parameters or {}).get("required", [])
        assert "expected_sha256" in required


READ_TOOLS = {
    "search_notes",
    "read_note",
    "query_graph",
    "explain_node",
    "graph_path",
    "affected_nodes",
    "god_nodes",
    "graph_status",
}

WRITE_TOOLS = {"create_note", "append_note", "update_note", "move_note"}


def tools_by_name(vault):
    settings = load_settings({"MARKWEAVE_VAULT": str(vault)})
    server = build_server(settings)
    return {t.name: t for t in asyncio.run(server.list_tools())}


def test_read_tools_are_annotated_read_only(vault):
    tools = tools_by_name(vault)

    for name in READ_TOOLS:
        annotations = tools[name].annotations
        assert annotations is not None, f"{name} has no annotations"
        assert annotations.readOnlyHint is True, name


def test_write_tools_are_not_annotated_read_only(vault):
    tools = tools_by_name(vault)

    for name in WRITE_TOOLS:
        assert tools[name].annotations.readOnlyHint is not True, name


def test_mutating_tools_are_flagged_destructive(vault):
    """append_note and update_note change existing notes; create_note cannot."""
    tools = tools_by_name(vault)

    for name in ("append_note", "update_note"):
        assert tools[name].annotations.destructiveHint is True, name


def test_create_note_is_not_destructive(vault):
    """create_note fails on an existing path, so it never destroys anything."""
    tools = tools_by_name(vault)

    assert tools["create_note"].annotations.destructiveHint is False


def test_write_tools_are_not_idempotent(vault):
    tools = tools_by_name(vault)

    assert tools["append_note"].annotations.idempotentHint is False
