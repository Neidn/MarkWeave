"""Wrapper around the graphify CLI.

graphify owns the graph; MarkWeave only reads it. Commands run with shell=False
and a fixed argv layout, so client-supplied text is always an inert positional
argument. The graph path comes from configuration and is never a tool parameter.

Output is returned as text rather than parsed: graphify emits prose for humans,
and parsing it would couple this server to another project's formatting.
"""

import subprocess
from datetime import datetime, timezone
from pathlib import Path

from .errors import GraphTimeout, GraphUnavailable

DEFAULT_TIMEOUT = 30.0
DEFAULT_MAX_OUTPUT_BYTES = 64_000
DEFAULT_BUDGET = 2000

# Any edit makes some note newer than the graph, so "newer than the graph" alone
# would report stale almost always and mean nothing. Report the lag instead, and
# only call it stale once the graph has fallen behind by more than this.
DEFAULT_STALE_AFTER_HOURS = 24.0

SKIP_DIRECTORIES = {"graphify-out", ".obsidian", ".git", ".trash"}


class GraphClient:
    def __init__(
        self,
        executable: str,
        graph_path: Path,
        timeout: float = DEFAULT_TIMEOUT,
        max_output_bytes: int = DEFAULT_MAX_OUTPUT_BYTES,
        stale_after_hours: float = DEFAULT_STALE_AFTER_HOURS,
    ) -> None:
        self._executable = executable
        self._graph_path = Path(graph_path)
        self._timeout = timeout
        self._max_output_bytes = max_output_bytes
        self._stale_after_hours = stale_after_hours

    def query(
        self,
        question: str,
        budget: int = DEFAULT_BUDGET,
        dfs: bool = False,
        context: list[str] | None = None,
    ) -> dict:
        argv = ["query", question, *self._graph_flag(), "--budget", str(budget)]
        if dfs:
            argv.append("--dfs")
        for item in context or []:
            argv += ["--context", item]
        return self._run(argv)

    def explain(self, node: str) -> dict:
        return self._run(["explain", node, *self._graph_flag()])

    def path(self, source: str, target: str) -> dict:
        return self._run(["path", source, target, *self._graph_flag()])

    def affected(
        self, node: str, relation: str | None = None, depth: int | None = None
    ) -> dict:
        argv = ["affected", node, *self._graph_flag()]
        if relation:
            argv += ["--relation", relation]
        if depth is not None:
            argv += ["--depth", str(depth)]
        return self._run(argv)

    def god_nodes(self, top: int = 10) -> dict:
        return self._run(["god-nodes", *self._graph_flag(), "--top", str(top)])

    def status(self, vault_root: Path) -> dict:
        """Never raises: a broken graph must not disable the vault tools."""
        if not self._graph_path.is_file():
            newest, _ = _note_mtimes(vault_root, since=None)
            return {
                "available": False,
                "graph_path": str(self._graph_path),
                "generated_at": None,
                "latest_markdown_mtime": _iso(newest),
                "notes_newer_than_graph": None,
                "lag_hours": None,
                "stale_after_hours": self._stale_after_hours,
                "stale": True,
            }

        graph_mtime = self._graph_path.stat().st_mtime
        newest_note, newer_count = _note_mtimes(vault_root, since=graph_mtime)
        lag_hours = 0.0
        if newest_note is not None and newest_note > graph_mtime:
            lag_hours = round((newest_note - graph_mtime) / 3600, 2)

        return {
            "available": True,
            "graph_path": str(self._graph_path),
            "generated_at": _iso(graph_mtime),
            "latest_markdown_mtime": _iso(newest_note),
            "notes_newer_than_graph": newer_count,
            "lag_hours": lag_hours,
            "stale_after_hours": self._stale_after_hours,
            "stale": lag_hours > self._stale_after_hours,
        }

    def _graph_flag(self) -> list[str]:
        return ["--graph", str(self._graph_path)]

    def _run(self, argv: list[str]) -> dict:
        if not self._graph_path.is_file():
            raise GraphUnavailable(f"graph not found at {self._graph_path}")

        try:
            completed = subprocess.run(
                [self._executable, *argv],
                capture_output=True,
                text=True,
                timeout=self._timeout,
                shell=False,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise GraphTimeout(
                f"graphify exceeded {self._timeout}s running {argv[0]!r}"
            ) from exc
        except OSError as exc:
            raise GraphUnavailable(f"could not run graphify: {exc}") from exc

        ok = completed.returncode == 0
        raw = completed.stdout if ok else (completed.stderr or completed.stdout)
        text, truncated = _clip(raw, self._max_output_bytes)

        return {
            "ok": ok,
            "text": text,
            "truncated": truncated,
            "graph_generated_at": _iso(self._graph_path.stat().st_mtime),
        }


def _clip(text: str, limit: int) -> tuple[str, bool]:
    if len(text) <= limit:
        return text, False
    return text[:limit], True


def _note_mtimes(vault_root: Path, since: float | None) -> tuple[float | None, int]:
    """Return the newest note mtime and how many notes are newer than `since`."""
    newest = None
    newer = 0
    for note in Path(vault_root).rglob("*.md"):
        if SKIP_DIRECTORIES.intersection(note.parts):
            continue
        try:
            mtime = note.stat().st_mtime
        except OSError:
            continue
        if newest is None or mtime > newest:
            newest = mtime
        if since is not None and mtime > since:
            newer += 1
    return newest, newer


def _iso(timestamp: float | None) -> str | None:
    if timestamp is None:
        return None
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()
