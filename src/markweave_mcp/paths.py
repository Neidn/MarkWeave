"""Vault-relative path validation.

Every path arriving from an MCP client passes through resolve_note_path before
it touches the filesystem.
"""

import unicodedata
from pathlib import Path, PurePosixPath

from .errors import NotMarkdown, PathOutsideVault

MARKDOWN_SUFFIX = ".md"


def nfc(text: str) -> str:
    """Compose Unicode. macOS writes filenames decomposed; MCP JSON carries composed."""
    return unicodedata.normalize("NFC", text)


def resolve_note_path(vault_root: Path, relative: str) -> Path:
    """Resolve a vault-relative path to an absolute path inside the vault.

    Raises PathOutsideVault if the path is empty, absolute, escapes the vault,
    or resolves through a symlink to a location outside it. Raises NotMarkdown
    if the path does not name a .md file.
    """
    if not relative or not relative.strip():
        raise PathOutsideVault("path must not be empty")

    composed = nfc(relative)
    pure = PurePosixPath(composed)

    if pure.is_absolute() or composed.startswith("/"):
        raise PathOutsideVault(f"path must be vault-relative: {relative!r}")
    if ".." in pure.parts:
        raise PathOutsideVault(f"path must not contain '..': {relative!r}")
    if pure.suffix.lower() != MARKDOWN_SUFFIX:
        raise NotMarkdown(f"only {MARKDOWN_SUFFIX} files are addressable: {relative!r}")

    root = Path(vault_root).resolve()
    candidate = _match_existing_name(root, pure)
    resolved = candidate.resolve()

    if resolved != root and root not in resolved.parents:
        raise PathOutsideVault(f"path escapes the vault: {relative!r}")

    return resolved


def _match_existing_name(root: Path, pure: PurePosixPath) -> Path:
    """Walk the path segment by segment, matching on-disk names by NFC equality.

    A filesystem that stores names decomposed (macOS) and one that compares
    bytes exactly (ext4 in the container) both work: if a literal join misses,
    fall back to the directory listing and compare composed forms.
    """
    current = root
    for segment in pure.parts:
        direct = current / segment
        if direct.exists() or not current.is_dir():
            current = direct
            continue
        current = _find_by_nfc(current, segment) or direct
    return current


def _find_by_nfc(directory: Path, segment: str) -> Path | None:
    target = nfc(segment)
    for entry in directory.iterdir():
        if nfc(entry.name) == target:
            return entry
    return None
