import hashlib
import unicodedata

import pytest

from markweave_mcp.errors import (
    NoteExists,
    NoteNotFound,
    NotMarkdown,
    PathOutsideVault,
    ShaMismatch,
)
from markweave_mcp.notes import move_note


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def test_move_note_relocates_file_and_keeps_content(vault):
    (vault / "inbox.md").write_text("body", encoding="utf-8")

    result = move_note(vault, "inbox.md", "archive/2026/inbox.md", sha("body"))

    assert not (vault / "inbox.md").exists()
    assert (vault / "archive" / "2026" / "inbox.md").read_text(encoding="utf-8") == "body"
    assert result["path"] == "archive/2026/inbox.md"
    assert result["source"] == "inbox.md"
    assert result["sha256"] == sha("body")


def test_move_note_creates_missing_destination_directories(vault):
    (vault / "note.md").write_text("x", encoding="utf-8")

    move_note(vault, "note.md", "회의록/2026/08/note.md", sha("x"))

    assert (vault / "회의록" / "2026" / "08" / "note.md").exists()


def test_move_note_renames_within_same_folder(vault):
    (vault / "notes").mkdir()
    (vault / "notes" / "old.md").write_text("keep", encoding="utf-8")

    move_note(vault, "notes/old.md", "notes/new.md", sha("keep"))

    assert not (vault / "notes" / "old.md").exists()
    assert (vault / "notes" / "new.md").read_text(encoding="utf-8") == "keep"


def test_move_note_rejects_wrong_sha(vault):
    (vault / "note.md").write_text("current", encoding="utf-8")

    with pytest.raises(ShaMismatch):
        move_note(vault, "note.md", "moved.md", sha("stale"))

    assert (vault / "note.md").exists()
    assert not (vault / "moved.md").exists()


def test_move_note_rejects_missing_source(vault):
    with pytest.raises(NoteNotFound):
        move_note(vault, "ghost.md", "somewhere.md", sha(""))


def test_move_note_refuses_to_overwrite_existing_destination(vault):
    (vault / "a.md").write_text("source", encoding="utf-8")
    (vault / "b.md").write_text("destination", encoding="utf-8")

    with pytest.raises(NoteExists):
        move_note(vault, "a.md", "b.md", sha("source"))

    assert (vault / "a.md").read_text(encoding="utf-8") == "source"
    assert (vault / "b.md").read_text(encoding="utf-8") == "destination"


def test_move_note_allows_case_only_rename(vault):
    """On APFS the destination "exists" because it is the same file — not a collision.

    Asserted against the real directory entry, not `(vault / "README.md").exists()`:
    a case-insensitive filesystem answers that true whatever case is stored, so the
    obvious assertion would pass without the rename having happened at all.
    """
    (vault / "readme.md").write_text("same file", encoding="utf-8")

    move_note(vault, "readme.md", "README.md", sha("same file"))

    names = [p.name for p in vault.iterdir()]
    assert names == ["README.md"]
    assert (vault / "README.md").read_text(encoding="utf-8") == "same file"


def test_move_note_allows_normalization_only_rename(vault):
    """NFD -> NFC of the same Korean name is one file on macOS, so this is a rename."""
    name = "한글노트.md"
    (vault / unicodedata.normalize("NFD", name)).write_text("본문", encoding="utf-8")

    move_note(
        vault,
        unicodedata.normalize("NFD", name),
        unicodedata.normalize("NFC", name),
        sha("본문"),
    )

    matches = [p for p in vault.iterdir() if unicodedata.normalize("NFC", p.name) == name]
    assert len(matches) == 1
    assert matches[0].read_text(encoding="utf-8") == "본문"


def test_move_note_rejects_destination_outside_vault(vault):
    (vault / "note.md").write_text("body", encoding="utf-8")

    with pytest.raises(PathOutsideVault):
        move_note(vault, "note.md", "../escaped.md", sha("body"))

    assert (vault / "note.md").exists()


def test_move_note_rejects_non_markdown_destination(vault):
    (vault / "note.md").write_text("body", encoding="utf-8")

    with pytest.raises(NotMarkdown):
        move_note(vault, "note.md", "note.txt", sha("body"))

    assert (vault / "note.md").exists()


def test_move_note_to_its_own_path_is_a_noop(vault):
    (vault / "same.md").write_text("body", encoding="utf-8")

    result = move_note(vault, "same.md", "same.md", sha("body"))

    assert (vault / "same.md").read_text(encoding="utf-8") == "body"
    assert result["path"] == "same.md"


def test_move_note_leaves_source_untouched_when_destination_is_invalid(vault):
    (vault / "note.md").write_text("body", encoding="utf-8")

    with pytest.raises(PathOutsideVault):
        move_note(vault, "note.md", "/absolute.md", sha("body"))

    assert (vault / "note.md").read_text(encoding="utf-8") == "body"
