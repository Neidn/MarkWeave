import unicodedata

import pytest

from markweave_mcp.errors import PathOutsideVault
from markweave_mcp.search import search_notes


def write(vault, rel, body):
    target = vault / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body, encoding="utf-8")
    return target


def paths(results):
    return [r["path"] for r in results]


def test_finds_note_by_body_substring(vault):
    write(vault, "manual/k8s.md", "# Guide\n쿠버네티스 클러스터 구축\n")
    write(vault, "manual/other.md", "unrelated\n")

    results = search_notes(vault, "클러스터")

    assert paths(results) == ["manual/k8s.md"]


def test_finds_note_by_filename(vault):
    write(vault, "manual/terraform.md", "no body match here\n")

    results = search_notes(vault, "terraform")

    assert paths(results) == ["manual/terraform.md"]


def test_match_is_case_insensitive(vault):
    write(vault, "note.md", "Deploy ArgoCD now\n")

    assert paths(search_notes(vault, "argocd")) == ["note.md"]


def test_nfc_query_matches_nfd_content(vault):
    """Korean text saved decomposed still matches a composed query."""
    write(vault, "note.md", unicodedata.normalize("NFD", "쿠버네티스"))

    results = search_notes(vault, unicodedata.normalize("NFC", "쿠버네티스"))

    assert paths(results) == ["note.md"]


def test_folder_scope_excludes_other_folders(vault):
    write(vault, "acme/customer.md", "VPC 마이그레이션\n")
    write(vault, "개인메모/job.md", "VPC 마이그레이션\n")

    results = search_notes(vault, "마이그레이션", folder="acme")

    assert paths(results) == ["acme/customer.md"]


def test_folder_outside_vault_is_rejected(vault):
    with pytest.raises(PathOutsideVault):
        search_notes(vault, "anything", folder="../..")


def test_limit_caps_result_count(vault):
    for i in range(5):
        write(vault, f"note{i}.md", "common term\n")

    assert len(search_notes(vault, "common", limit=2)) == 2


def test_snippet_is_capped(vault):
    write(vault, "note.md", "x" * 500 + " needle " + "y" * 500)

    result = search_notes(vault, "needle", max_snippet=80)[0]

    assert len(result["snippet"]) <= 80
    assert "needle" in result["snippet"]


def test_graphify_output_is_not_searched(vault):
    write(vault, "graphify-out/GRAPH_REPORT.md", "쿠버네티스 report\n")
    write(vault, "real.md", "쿠버네티스 note\n")

    assert paths(search_notes(vault, "쿠버네티스")) == ["real.md"]


def test_non_markdown_files_are_ignored(vault):
    (vault / "notes.txt").write_text("secret term", encoding="utf-8")

    assert search_notes(vault, "secret") == []


def test_title_comes_from_first_heading(vault):
    write(vault, "note.md", "# 실제 제목\n\nbody term\n")

    assert search_notes(vault, "term")[0]["title"] == "실제 제목"


def test_title_falls_back_to_filename(vault):
    write(vault, "no-heading.md", "body term\n")

    assert search_notes(vault, "term")[0]["title"] == "no-heading"


def test_filename_match_outranks_body_match(vault):
    write(vault, "argocd.md", "unrelated body\n")
    write(vault, "other.md", "argocd mentioned once\n")

    assert paths(search_notes(vault, "argocd"))[0] == "argocd.md"


def test_empty_query_is_rejected(vault):
    with pytest.raises(ValueError):
        search_notes(vault, "   ")
