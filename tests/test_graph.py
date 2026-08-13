import json
import os
import time

import pytest

from markweave_mcp.errors import GraphTimeout, GraphUnavailable
from markweave_mcp.graph import GraphClient


@pytest.fixture
def graph_file(tmp_path):
    path = tmp_path / "graphify-out" / "graph.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"nodes": [], "links": []}), encoding="utf-8")
    return path


def fake_graphify(tmp_path, body):
    script = tmp_path / "fake-graphify"
    script.write_text("#!/bin/sh\n" + body, encoding="utf-8")
    script.chmod(0o755)
    return script


def echo_args_client(tmp_path, graph_file, **kwargs):
    """A client whose graphify prints each argument on its own line."""
    script = fake_graphify(tmp_path, 'for a in "$@"; do echo "$a"; done\n')
    return GraphClient(executable=str(script), graph_path=graph_file, **kwargs)


def test_query_passes_fixed_argv(tmp_path, graph_file):
    client = echo_args_client(tmp_path, graph_file)

    result = client.query("쿠버네티스 무엇", budget=500)

    assert result["ok"] is True
    assert result["text"].splitlines() == [
        "query",
        "쿠버네티스 무엇",
        "--graph",
        str(graph_file),
        "--budget",
        "500",
    ]


def test_shell_metacharacters_are_passed_literally(tmp_path, graph_file):
    """No shell: a query containing shell syntax stays one inert argument."""
    client = echo_args_client(tmp_path, graph_file)
    hostile = '"; rm -rf / #$(whoami)`id`'

    result = client.query(hostile)

    assert hostile in result["text"].splitlines()


def test_explain_builds_expected_argv(tmp_path, graph_file):
    client = echo_args_client(tmp_path, graph_file)

    lines = client.explain("Index")["text"].splitlines()

    assert lines[:2] == ["explain", "Index"]
    assert "--graph" in lines


def test_path_builds_expected_argv(tmp_path, graph_file):
    client = echo_args_client(tmp_path, graph_file)

    lines = client.path("A", "B")["text"].splitlines()

    assert lines[:3] == ["path", "A", "B"]


def test_affected_includes_optional_flags(tmp_path, graph_file):
    client = echo_args_client(tmp_path, graph_file)

    lines = client.affected("X", relation="references", depth=3)["text"].splitlines()

    assert lines[:2] == ["affected", "X"]
    assert "--relation" in lines and "references" in lines
    assert "--depth" in lines and "3" in lines


def test_god_nodes_includes_top(tmp_path, graph_file):
    client = echo_args_client(tmp_path, graph_file)

    lines = client.god_nodes(top=5)["text"].splitlines()

    assert lines[0] == "god-nodes"
    assert "--top" in lines and "5" in lines


def test_nonzero_exit_returns_not_ok_without_raising(tmp_path, graph_file):
    script = fake_graphify(tmp_path, 'echo "boom" >&2\nexit 3\n')
    client = GraphClient(executable=str(script), graph_path=graph_file)

    result = client.query("anything")

    assert result["ok"] is False
    assert "boom" in result["text"]


def test_timeout_raises_graph_timeout(tmp_path, graph_file):
    script = fake_graphify(tmp_path, "sleep 5\n")
    client = GraphClient(executable=str(script), graph_path=graph_file, timeout=0.3)

    with pytest.raises(GraphTimeout):
        client.query("anything")


def test_output_is_truncated_at_limit(tmp_path, graph_file):
    script = fake_graphify(tmp_path, 'head -c 5000 /dev/zero | tr "\\0" "a"\n')
    client = GraphClient(executable=str(script), graph_path=graph_file, max_output_bytes=100)

    result = client.query("anything")

    assert result["truncated"] is True
    assert len(result["text"]) <= 100


def test_missing_graph_file_raises_before_running(tmp_path):
    missing = tmp_path / "graphify-out" / "graph.json"
    client = GraphClient(executable="/nonexistent/graphify", graph_path=missing)

    with pytest.raises(GraphUnavailable):
        client.query("anything")


def test_status_reports_available_and_generated_at(tmp_path, graph_file, vault):
    client = GraphClient(executable="/unused", graph_path=graph_file)

    status = client.status(vault)

    assert status["available"] is True
    assert status["graph_path"] == str(graph_file)
    assert status["generated_at"].startswith("20")


def test_status_reports_stale_when_note_is_newer_than_graph(tmp_path, graph_file, vault):
    note = vault / "fresh.md"
    note.write_text("new", encoding="utf-8")
    future = time.time() + 60
    os.utime(note, (future, future))

    status = GraphClient(executable="/unused", graph_path=graph_file).status(vault)

    assert status["stale"] is True


def test_status_not_stale_when_graph_is_newer(tmp_path, graph_file, vault):
    (vault / "old.md").write_text("old", encoding="utf-8")
    future = time.time() + 60
    os.utime(graph_file, (future, future))

    status = GraphClient(executable="/unused", graph_path=graph_file).status(vault)

    assert status["stale"] is False


def test_status_reports_unavailable_instead_of_raising(tmp_path, vault):
    missing = tmp_path / "nope" / "graph.json"

    status = GraphClient(executable="/unused", graph_path=missing).status(vault)

    assert status["available"] is False
    assert status["generated_at"] is None
