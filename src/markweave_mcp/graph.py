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

SKIP_DIRECTORIES = {"graphify-out", ".obsidian", ".git", ".trash"}


class GraphClient:
    def __init__(
        self,
        executable: str,
        graph_path: Path,
        timeout: float = DEFAULT_TIMEOUT,
        max_output_bytes: int = DEFAULT_MAX_OUTPUT_BYTES,
    ) -> None:
        self._executable = executable
        self._graph_path = Path(graph_path)
        self._timeout = timeout
        self._max_output_bytes = max_output_bytes

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
            return {
                "available": False,
                "graph_path": str(self._graph_path),
                "generated_at": None,
                "latest_markdown_mtime": _iso(_latest_markdown_mtime(vault_root)),
                "stale": True,
            }

        graph_mtime = self._graph_path.stat().st_mtime
        newest_note = _latest_markdown_mtime(vault_root)
        return {
            "available": True,
            "graph_path": str(self._graph_path),
            "generated_at": _iso(graph_mtime),
            "latest_markdown_mtime": _iso(newest_note),
            "stale": newest_note is not None and newest_note > graph_mtime,
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


def _latest_markdown_mtime(vault_root: Path) -> float | None:
    newest = None
    for note in Path(vault_root).rglob("*.md"):
        if SKIP_DIRECTORIES.intersection(note.parts):
            continue
        try:
            mtime = note.stat().st_mtime
        except OSError:
            continue
        if newest is None or mtime > newest:
            newest = mtime
    return newest


def _iso(timestamp: float | None) -> str | None:
    if timestamp is None:
        return None
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()
