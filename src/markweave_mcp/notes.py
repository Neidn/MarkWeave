"""Reading and writing notes.

Every mutation is guarded by a SHA-256 comparison and lands via an atomic
rename from a temporary file in the same directory, so a concurrent editor
(Obsidian, Dropbox sync) can never be silently overwritten and a reader can
never observe a half-written note.
"""

import hashlib
import os
import tempfile
from pathlib import Path

from .errors import FileTooLarge, NoteExists, NoteNotFound, ShaMismatch
from .paths import resolve_note_path

DEFAULT_MAX_BYTES = 2 * 1024 * 1024


def sha256_of(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def read_note(vault_root: Path, path: str, max_bytes: int = DEFAULT_MAX_BYTES) -> dict:
    target = resolve_note_path(vault_root, path)
    if not target.is_file():
        raise NoteNotFound(f"no note at {path!r}")

    stat = target.stat()
    if stat.st_size > max_bytes:
        raise FileTooLarge(f"{path!r} is {stat.st_size} bytes, limit is {max_bytes}")

    content = target.read_text(encoding="utf-8")
    return {
        "path": path,
        "content": content,
        "sha256": sha256_of(content),
        "size": stat.st_size,
        "mtime": stat.st_mtime,
    }


def create_note(
    vault_root: Path, path: str, content: str, max_bytes: int = DEFAULT_MAX_BYTES
) -> dict:
    target = resolve_note_path(vault_root, path)
    if target.exists():
        raise NoteExists(f"{path!r} already exists")

    _check_size(path, content, max_bytes)
    target.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(target, content)
    return {"path": path, "sha256": sha256_of(content)}


def append_note(
    vault_root: Path,
    path: str,
    content: str,
    expected_sha256: str,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> dict:
    target, current = _load_for_write(vault_root, path, expected_sha256)
    merged = current + content
    _check_size(path, merged, max_bytes)
    _atomic_write(target, merged)
    return {"path": path, "sha256": sha256_of(merged)}


def update_note(
    vault_root: Path,
    path: str,
    content: str,
    expected_sha256: str,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> dict:
    target, _ = _load_for_write(vault_root, path, expected_sha256)
    _check_size(path, content, max_bytes)
    _atomic_write(target, content)
    return {"path": path, "sha256": sha256_of(content)}


def move_note(
    vault_root: Path,
    source: str,
    destination: str,
    expected_sha256: str,
) -> dict:
    """Move or rename a note. Content is never altered.

    A rename is just a move within the same folder, so one function covers both.
    The SHA-256 guard is kept even though the bytes do not change: it proves the
    caller has actually read the note it is relocating, and it refuses to move a
    file that some other editor has changed in the meantime.

    Deliberately not paired with a delete tool — a move is reversible, so a wrong
    one costs a second move, while a wrong delete costs the note.
    """
    src, current = _load_for_write(vault_root, source, expected_sha256)
    dst = resolve_note_path(vault_root, destination)

    # `dst.exists()` is true for a case-only or normalization-only rename on
    # macOS, because APFS looks names up case- and NFC/NFD-insensitively while
    # still storing what was written. Rejecting on existence alone would make
    # `readme.md` -> `README.md`, or NFD -> NFC of one Korean name, look like a
    # collision with another note. samefile() distinguishes "the same inode under
    # another spelling" from "a different note already sitting there".
    if dst.exists() and not src.samefile(dst):
        raise NoteExists(f"{destination!r} already exists")

    dst.parent.mkdir(parents=True, exist_ok=True)
    os.replace(src, dst)
    return {
        "source": source,
        "path": destination,
        "sha256": sha256_of(current),
    }


def _load_for_write(vault_root: Path, path: str, expected_sha256: str) -> tuple[Path, str]:
    target = resolve_note_path(vault_root, path)
    if not target.is_file():
        raise NoteNotFound(f"no note at {path!r}")

    current = target.read_text(encoding="utf-8")
    actual = sha256_of(current)
    if actual != expected_sha256:
        raise ShaMismatch(
            f"{path!r} changed on disk: expected {expected_sha256}, found {actual}"
        )
    return target, current


def _check_size(path: str, content: str, max_bytes: int) -> None:
    size = len(content.encode("utf-8"))
    if size > max_bytes:
        raise FileTooLarge(f"{path!r} would be {size} bytes, limit is {max_bytes}")


def _atomic_write(target: Path, content: str) -> None:
    """Write via a temp file in the target's own directory, then rename over it."""
    fd, tmp_name = tempfile.mkstemp(dir=target.parent, prefix=".markweave-", suffix=".tmp")
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, target)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
