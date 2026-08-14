"""Server configuration.

Everything here comes from the environment and is frozen at startup. The vault
root and graph path in particular are deliberately not reachable from any MCP
request — a client can address notes inside the vault, never choose the vault.
"""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

DEFAULT_MAX_RESULTS = 20
DEFAULT_MAX_SNIPPET = 200
DEFAULT_MAX_RESPONSE_BYTES = 64_000
DEFAULT_MAX_FILE_BYTES = 2 * 1024 * 1024
DEFAULT_GRAPH_TIMEOUT = 30.0
DEFAULT_GRAPHIFY_BIN = "graphify"
DEFAULT_STALE_AFTER_HOURS = 24.0


@dataclass(frozen=True)
class Settings:
    vault_root: Path
    graph_path: Path
    graphify_bin: str
    max_results: int
    max_snippet: int
    max_response_bytes: int
    max_file_bytes: int
    graph_timeout: float
    stale_after_hours: float


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    source = os.environ if env is None else env

    raw_vault = source.get("MARKWEAVE_VAULT")
    if not raw_vault:
        raise ValueError("MARKWEAVE_VAULT must be set to the vault root")

    vault_root = Path(raw_vault).expanduser()
    if not vault_root.is_dir():
        raise ValueError(f"MARKWEAVE_VAULT does not exist: {raw_vault}")
    vault_root = vault_root.resolve()

    raw_graph = source.get("MARKWEAVE_GRAPH")
    graph_path = (
        Path(raw_graph).expanduser()
        if raw_graph
        else vault_root / "graphify-out" / "graph.json"
    )

    return Settings(
        vault_root=vault_root,
        graph_path=graph_path,
        graphify_bin=source.get("MARKWEAVE_GRAPHIFY_BIN", DEFAULT_GRAPHIFY_BIN),
        max_results=int(source.get("MARKWEAVE_MAX_RESULTS", DEFAULT_MAX_RESULTS)),
        max_snippet=int(source.get("MARKWEAVE_MAX_SNIPPET", DEFAULT_MAX_SNIPPET)),
        max_response_bytes=int(
            source.get("MARKWEAVE_MAX_RESPONSE_BYTES", DEFAULT_MAX_RESPONSE_BYTES)
        ),
        max_file_bytes=int(source.get("MARKWEAVE_MAX_FILE_BYTES", DEFAULT_MAX_FILE_BYTES)),
        graph_timeout=float(source.get("MARKWEAVE_GRAPH_TIMEOUT", DEFAULT_GRAPH_TIMEOUT)),
        stale_after_hours=float(
            source.get("MARKWEAVE_STALE_AFTER_HOURS", DEFAULT_STALE_AFTER_HOURS)
        ),
    )
