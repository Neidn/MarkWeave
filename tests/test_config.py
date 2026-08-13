import pytest

from markweave_mcp.config import Settings, load_settings


def test_reads_vault_from_environment(vault):
    settings = load_settings({"MARKWEAVE_VAULT": str(vault)})

    assert settings.vault_root == vault.resolve()


def test_missing_vault_variable_is_an_error():
    with pytest.raises(ValueError, match="MARKWEAVE_VAULT"):
        load_settings({})


def test_nonexistent_vault_is_an_error(tmp_path):
    with pytest.raises(ValueError, match="does not exist"):
        load_settings({"MARKWEAVE_VAULT": str(tmp_path / "ghost")})


def test_graph_path_defaults_to_graphify_out_inside_vault(vault):
    settings = load_settings({"MARKWEAVE_VAULT": str(vault)})

    assert settings.graph_path == vault.resolve() / "graphify-out" / "graph.json"


def test_graph_path_can_be_overridden(vault, tmp_path):
    elsewhere = tmp_path / "custom.json"

    settings = load_settings(
        {"MARKWEAVE_VAULT": str(vault), "MARKWEAVE_GRAPH": str(elsewhere)}
    )

    assert settings.graph_path == elsewhere


def test_limits_have_defaults(vault):
    settings = load_settings({"MARKWEAVE_VAULT": str(vault)})

    assert settings.max_results > 0
    assert settings.max_snippet > 0
    assert settings.max_file_bytes > 0
    assert settings.graph_timeout > 0


def test_limits_are_read_from_environment(vault):
    settings = load_settings(
        {
            "MARKWEAVE_VAULT": str(vault),
            "MARKWEAVE_MAX_RESULTS": "3",
            "MARKWEAVE_GRAPH_TIMEOUT": "1.5",
        }
    )

    assert settings.max_results == 3
    assert settings.graph_timeout == 1.5


def test_settings_are_frozen(vault):
    settings = load_settings({"MARKWEAVE_VAULT": str(vault)})

    with pytest.raises(Exception):
        settings.vault_root = "/somewhere/else"


def test_settings_type_is_exported():
    assert Settings is not None
