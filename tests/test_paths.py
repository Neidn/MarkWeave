import unicodedata

import pytest

from markweave_mcp.errors import NotMarkdown, PathOutsideVault
from markweave_mcp.paths import resolve_note_path


def test_accepts_nested_markdown_path(vault):
    (vault / "manual").mkdir()
    target = vault / "manual" / "guide.md"
    target.write_text("hi", encoding="utf-8")

    assert resolve_note_path(vault, "manual/guide.md") == target


def test_rejects_parent_directory_escape(vault):
    with pytest.raises(PathOutsideVault):
        resolve_note_path(vault, "../outside.md")


def test_rejects_parent_directory_escape_in_middle(vault):
    with pytest.raises(PathOutsideVault):
        resolve_note_path(vault, "manual/../../outside.md")


def test_rejects_absolute_path(vault):
    with pytest.raises(PathOutsideVault):
        resolve_note_path(vault, "/etc/passwd.md")


def test_rejects_non_markdown_extension(vault):
    with pytest.raises(NotMarkdown):
        resolve_note_path(vault, "notes/secrets.txt")


def test_rejects_empty_path(vault):
    with pytest.raises(PathOutsideVault):
        resolve_note_path(vault, "")


def test_rejects_symlink_pointing_outside_vault(vault, tmp_path):
    outside = tmp_path / "outside.md"
    outside.write_text("secret", encoding="utf-8")
    (vault / "escape.md").symlink_to(outside)

    with pytest.raises(PathOutsideVault):
        resolve_note_path(vault, "escape.md")


def test_allows_symlink_staying_inside_vault(vault):
    real = vault / "real.md"
    real.write_text("ok", encoding="utf-8")
    (vault / "alias.md").symlink_to(real)

    assert resolve_note_path(vault, "alias.md") == real


def test_nfc_query_matches_nfd_filename_on_disk(vault):
    """macOS stores Korean filenames decomposed; MCP clients send composed."""
    nfd_name = unicodedata.normalize("NFD", "쿠버네티스.md")
    nfc_name = unicodedata.normalize("NFC", "쿠버네티스.md")
    assert nfd_name != nfc_name

    (vault / nfd_name).write_text("k8s", encoding="utf-8")

    resolved = resolve_note_path(vault, nfc_name)
    assert resolved.read_text(encoding="utf-8") == "k8s"


def test_nonexistent_path_still_resolves_for_creation(vault):
    """create_note needs a resolved target before the file exists."""
    assert resolve_note_path(vault, "new/note.md") == vault / "new" / "note.md"
