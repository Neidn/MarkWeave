"""Pure-Python note search.

The corpus is small enough (hundreds of notes, single-digit megabytes) that a
full scan costs a fraction of a second, so there is no index to build, keep
warm, or invalidate. Revisit only if the vault grows by an order of magnitude.
"""

from pathlib import Path

from .errors import PathOutsideVault
from .paths import nfc

DEFAULT_LIMIT = 20
DEFAULT_MAX_SNIPPET = 200

SKIP_DIRECTORIES = {"graphify-out", ".obsidian", ".git", ".trash", "images"}

FILENAME_MATCH_SCORE = 100.0


def search_notes(
    vault_root: Path,
    query: str,
    limit: int = DEFAULT_LIMIT,
    folder: str | None = None,
    max_snippet: int = DEFAULT_MAX_SNIPPET,
) -> list[dict]:
    """Return notes matching query, filename matches ranked above body matches."""
    if not query or not query.strip():
        raise ValueError("query must not be empty")

    root = Path(vault_root).resolve()
    scope = _resolve_folder(root, folder)
    needle = nfc(query).casefold()

    results = []
    for note in _walk_notes(scope):
        relative = note.relative_to(root).as_posix()
        try:
            body = note.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue

        score, snippet = _score(nfc(body), nfc(relative), needle, max_snippet)
        if score == 0:
            continue

        results.append(
            {
                "path": relative,
                "title": _title(body, note),
                "snippet": snippet,
                "mtime": note.stat().st_mtime,
                "score": score,
            }
        )

    results.sort(key=lambda r: (-r["score"], r["path"]))
    return results[:limit]


def _resolve_folder(root: Path, folder: str | None) -> Path:
    if folder is None:
        return root

    scope = (root / nfc(folder)).resolve()
    if scope != root and root not in scope.parents:
        raise PathOutsideVault(f"folder escapes the vault: {folder!r}")
    return scope


def _walk_notes(scope: Path):
    if not scope.is_dir():
        return
    for path in sorted(scope.rglob("*.md")):
        if SKIP_DIRECTORIES.intersection(path.parts):
            continue
        if path.is_file():
            yield path


def _score(body: str, relative: str, needle: str, max_snippet: int) -> tuple[float, str]:
    folded_body = body.casefold()
    in_filename = needle in Path(relative).name.casefold()
    occurrences = folded_body.count(needle)

    if not in_filename and occurrences == 0:
        return 0.0, ""

    score = occurrences + (FILENAME_MATCH_SCORE if in_filename else 0.0)
    return score, _snippet(body, folded_body, needle, max_snippet)


def _snippet(body: str, folded_body: str, needle: str, max_snippet: int) -> str:
    index = folded_body.find(needle)
    if index == -1:
        return body[:max_snippet].strip()

    pad = max(0, (max_snippet - len(needle)) // 2)
    start = max(0, index - pad)
    return body[start : start + max_snippet].strip()


def _title(body: str, note: Path) -> str:
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            heading = stripped.lstrip("#").strip()
            if heading:
                return heading
    return note.stem
