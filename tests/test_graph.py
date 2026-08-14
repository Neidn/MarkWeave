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


def test_status_counts_a_newer_note_without_calling_it_stale(tmp_path, graph_file, vault):
    """One note a minute newer is lag to report, not a stale graph."""
    note = vault / "fresh.md"
    note.write_text("new", encoding="utf-8")
    future = time.time() + 60
    os.utime(note, (future, future))

    status = GraphClient(executable="/unused", graph_path=graph_file).status(vault)

    assert status["notes_newer_than_graph"] == 1
    assert status["stale"] is False


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


def test_status_reports_lag_hours_and_newer_note_count(tmp_path, graph_file, vault):
    for name in ("a.md", "b.md"):
        note = vault / name
        note.write_text("x", encoding="utf-8")
        future = time.time() + 3600
        os.utime(note, (future, future))
    old = vault / "old.md"
    old.write_text("x", encoding="utf-8")
    past = time.time() - 7200
    os.utime(old, (past, past))

    status = GraphClient(executable="/unused", graph_path=graph_file).status(vault)

    assert status["notes_newer_than_graph"] == 2
    assert status["lag_hours"] == pytest.approx(1.0, abs=0.1)


def test_recent_edit_is_not_stale_within_tolerance(tmp_path, graph_file, vault):
    """A note touched minutes after a rebuild must not read as stale."""
    note = vault / "fresh.md"
    note.write_text("x", encoding="utf-8")
    soon = time.time() + 360
    os.utime(note, (soon, soon))

    status = GraphClient(
        executable="/unused", graph_path=graph_file, stale_after_hours=24
    ).status(vault)

    assert status["stale"] is False
    assert status["notes_newer_than_graph"] == 1


def test_stale_once_lag_exceeds_tolerance(tmp_path, graph_file, vault):
    note = vault / "fresh.md"
    note.write_text("x", encoding="utf-8")
    much_later = time.time() + 48 * 3600
    os.utime(note, (much_later, much_later))

    status = GraphClient(
        executable="/unused", graph_path=graph_file, stale_after_hours=24
    ).status(vault)

    assert status["stale"] is True


def test_lag_is_zero_when_no_note_is_newer(tmp_path, graph_file, vault):
    note = vault / "old.md"
    note.write_text("x", encoding="utf-8")
    past = time.time() - 7200
    os.utime(note, (past, past))

    status = GraphClient(executable="/unused", graph_path=graph_file).status(vault)

    assert status["lag_hours"] == 0.0
    assert status["notes_newer_than_graph"] == 0
    assert status["stale"] is False


def test_missing_graph_reports_stale_with_no_lag(tmp_path, vault):
    status = GraphClient(
        executable="/unused", graph_path=tmp_path / "nope" / "graph.json"
    ).status(vault)

    assert status["available"] is False
    assert status["stale"] is True
    assert status["lag_hours"] is None
