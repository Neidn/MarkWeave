import hashlib

import pytest

from markweave_mcp.errors import (
    FileTooLarge,
    NoteExists,
    NoteNotFound,
    PathOutsideVault,
    ShaMismatch,
)
from markweave_mcp.notes import append_note, create_note, read_note, update_note


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def test_create_note_writes_file_and_returns_sha(vault):
    result = create_note(vault, "new.md", "hello")

    assert (vault / "new.md").read_text(encoding="utf-8") == "hello"
    assert result["sha256"] == sha("hello")


def test_create_note_creates_parent_directories(vault):
    create_note(vault, "manual/쿠버네티스/guide.md", "body")

    assert (vault / "manual" / "쿠버네티스" / "guide.md").exists()


def test_create_note_fails_when_path_exists(vault):
    (vault / "taken.md").write_text("original", encoding="utf-8")

    with pytest.raises(NoteExists):
        create_note(vault, "taken.md", "replacement")

    assert (vault / "taken.md").read_text(encoding="utf-8") == "original"


def test_create_note_rejects_path_outside_vault(vault):
    with pytest.raises(PathOutsideVault):
        create_note(vault, "../escaped.md", "body")


def test_read_note_returns_content_and_matching_sha(vault):
    (vault / "note.md").write_text("내용", encoding="utf-8")

    result = read_note(vault, "note.md")

    assert result["content"] == "내용"
    assert result["sha256"] == sha("내용")
    assert result["size"] == len("내용".encode("utf-8"))


def test_read_note_missing_file_raises(vault):
    with pytest.raises(NoteNotFound):
        read_note(vault, "ghost.md")


def test_read_note_rejects_file_over_limit(vault):
    (vault / "big.md").write_text("x" * 100, encoding="utf-8")

    with pytest.raises(FileTooLarge):
        read_note(vault, "big.md", max_bytes=50)


def test_append_note_appends_with_correct_sha(vault):
    (vault / "log.md").write_text("line1\n", encoding="utf-8")

    append_note(vault, "log.md", "line2\n", expected_sha256=sha("line1\n"))

    assert (vault / "log.md").read_text(encoding="utf-8") == "line1\nline2\n"


def test_append_note_with_wrong_sha_leaves_file_untouched(vault):
    (vault / "log.md").write_text("line1\n", encoding="utf-8")

    with pytest.raises(ShaMismatch):
        append_note(vault, "log.md", "line2\n", expected_sha256=sha("something else"))

    assert (vault / "log.md").read_text(encoding="utf-8") == "line1\n"


def test_append_note_missing_file_raises(vault):
    with pytest.raises(NoteNotFound):
        append_note(vault, "ghost.md", "x", expected_sha256=sha(""))


def test_update_note_replaces_content_with_correct_sha(vault):
    (vault / "note.md").write_text("old", encoding="utf-8")

    result = update_note(vault, "note.md", "new", expected_sha256=sha("old"))

    assert (vault / "note.md").read_text(encoding="utf-8") == "new"
    assert result["sha256"] == sha("new")


def test_update_note_with_wrong_sha_leaves_file_untouched(vault):
    (vault / "note.md").write_text("old", encoding="utf-8")

    with pytest.raises(ShaMismatch):
        update_note(vault, "note.md", "new", expected_sha256=sha("stale"))

    assert (vault / "note.md").read_text(encoding="utf-8") == "old"


def test_concurrent_external_edit_is_detected(vault):
    """Client reads, someone else edits, client writes with the now-stale sha."""
    (vault / "note.md").write_text("v1", encoding="utf-8")
    observed = read_note(vault, "note.md")["sha256"]

    (vault / "note.md").write_text("v2-from-obsidian", encoding="utf-8")

    with pytest.raises(ShaMismatch):
        update_note(vault, "note.md", "v3", expected_sha256=observed)

    assert (vault / "note.md").read_text(encoding="utf-8") == "v2-from-obsidian"


def test_write_leaves_no_temporary_files_behind(vault):
    create_note(vault, "note.md", "a")
    update_note(vault, "note.md", "b", expected_sha256=sha("a"))

    assert sorted(p.name for p in vault.iterdir()) == ["note.md"]


def test_update_rejects_payload_over_limit(vault):
    (vault / "note.md").write_text("old", encoding="utf-8")

    with pytest.raises(FileTooLarge):
        update_note(vault, "note.md", "x" * 100, expected_sha256=sha("old"), max_bytes=50)

    assert (vault / "note.md").read_text(encoding="utf-8") == "old"
