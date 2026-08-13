import pytest


@pytest.fixture
def vault(tmp_path):
    """A real on-disk vault root."""
    root = tmp_path / "vault"
    root.mkdir()
    return root
