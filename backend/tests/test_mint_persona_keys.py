import importlib.util
import json
import os
import stat
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# Load the mint_persona_keys module from scripts
spec = importlib.util.spec_from_file_location(
    "mint_persona_keys",
    Path(__file__).resolve().parent.parent.parent / "scripts" / "mint_persona_keys.py",
)
mint_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mint_module)


class FakeSecurity:
    """Fake Elasticsearch Security API for testing."""

    def __init__(self, old_key_ids=None):
        self.old_key_ids = old_key_ids or []
        self.created_ids = []
        self.invalidated_ids = []
        self.fail_on_create_index = None  # If set, fail when creating this key index (0-based)

    def get_api_key(self, name=None, owner=None):
        """Return existing keys by name pattern."""
        old_keys = [{"id": kid, "name": f"glassbox-old-{i}"} for i, kid in enumerate(self.old_key_ids)]
        return {"api_keys": old_keys}

    def create_api_key(self, name=None, role_descriptors=None, expiration=None):
        """Create a fake API key."""
        create_idx = len(self.created_ids)
        if self.fail_on_create_index is not None and create_idx == self.fail_on_create_index:
            raise Exception(f"Simulated failure on key {create_idx}")
        key_id = f"new-key-{create_idx}"
        self.created_ids.append(key_id)
        return {"id": key_id, "encoded": f"fake-encoded-key-{create_idx}"}

    def invalidate_api_key(self, ids=None):
        """Track invalidated keys."""
        self.invalidated_ids.extend(ids or [])


class FakeEs:
    """Fake Elasticsearch client for testing."""

    def __init__(self, old_key_ids=None):
        self.security = FakeSecurity(old_key_ids=old_key_ids)


def test_mint_happy_path():
    """Happy path: 5 keys created, file written, old keys invalidated after write."""
    with tempfile.TemporaryDirectory() as tmpdir:
        out_path = Path(tmpdir) / "test_keys.json"
        old_key_ids = ["old-1", "old-2"]
        es = FakeEs(old_key_ids=old_key_ids)

        result = mint_module.mint(es, out_path)

        # Check that all 5 persona names are returned
        assert set(result) == {"employee", "manager", "hr", "exec", "catalog"}

        # Check file exists and has correct content
        assert out_path.exists()
        with open(out_path) as f:
            keys = json.load(f)
        assert set(keys.keys()) == {"employee", "manager", "hr", "exec", "catalog"}
        assert keys["employee"] == "fake-encoded-key-0"
        assert keys["catalog"] == "fake-encoded-key-4"

        # Check file mode is 0o600
        file_mode = stat.S_IMODE(os.stat(out_path).st_mode)
        assert file_mode == 0o600

        # Check that old keys were invalidated
        assert set(es.security.invalidated_ids) == {"old-1", "old-2"}

        # Check that new keys were NOT invalidated
        assert not any(kid in es.security.invalidated_ids for kid in es.security.created_ids)


def test_mint_pre_existing_0644_file_becomes_0600():
    """Pre-existing 0644 file should be chmod'd to 0o600."""
    with tempfile.TemporaryDirectory() as tmpdir:
        out_path = Path(tmpdir) / "test_keys.json"
        # Create a pre-existing file with 0o644 mode
        out_path.write_text('{"old": "data"}')
        os.chmod(out_path, 0o644)
        assert stat.S_IMODE(os.stat(out_path).st_mode) == 0o644

        es = FakeEs(old_key_ids=[])
        mint_module.mint(es, out_path)

        # File mode should now be 0o600
        file_mode = stat.S_IMODE(os.stat(out_path).st_mode)
        assert file_mode == 0o600


def test_mint_create_fails_on_third_key():
    """If key creation fails on 3rd key, first 2 are invalidated, old keys untouched."""
    with tempfile.TemporaryDirectory() as tmpdir:
        out_path = Path(tmpdir) / "test_keys.json"
        old_key_ids = ["old-1"]
        es = FakeEs(old_key_ids=old_key_ids)
        es.security.fail_on_create_index = 2  # Fail on the 3rd key (0-indexed)

        with pytest.raises(Exception, match="Simulated failure on key 2"):
            mint_module.mint(es, out_path)

        # Check that first 2 new keys were invalidated (cleanup on failure)
        assert "new-key-0" in es.security.invalidated_ids
        assert "new-key-1" in es.security.invalidated_ids

        # Check that old keys were NOT invalidated
        assert "old-1" not in es.security.invalidated_ids

        # Check that file was not written
        assert not out_path.exists()


def test_mint_file_write_failure():
    """If file write fails (parent is a regular file), new keys are invalidated, old keys untouched."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a regular file where we want the directory
        bad_parent = Path(tmpdir) / "not_a_dir"
        bad_parent.write_text("I am a file")
        out_path = bad_parent / "test_keys.json"

        old_key_ids = ["old-1"]
        es = FakeEs(old_key_ids=old_key_ids)

        with pytest.raises(Exception):
            mint_module.mint(es, out_path)

        # Check that new keys were invalidated (cleanup on failure)
        assert "new-key-0" in es.security.invalidated_ids

        # Check that old keys were NOT invalidated
        assert "old-1" not in es.security.invalidated_ids


def test_mint_no_old_keys():
    """First run with no old keys should work fine."""
    with tempfile.TemporaryDirectory() as tmpdir:
        out_path = Path(tmpdir) / "test_keys.json"
        es = FakeEs(old_key_ids=[])

        result = mint_module.mint(es, out_path)

        assert set(result) == {"employee", "manager", "hr", "exec", "catalog"}
        assert out_path.exists()
        # No old keys to invalidate
        assert len(es.security.invalidated_ids) == 0


def test_main_settings_error_prints_readable_error(capsys, monkeypatch):
    """main() with Settings raising should return 1 and print ClassName: message."""
    def mock_settings():
        raise ValueError("missing .env file")

    monkeypatch.setattr(mint_module, "Settings", mock_settings)

    result = mint_module.main()

    assert result == 1
    captured = capsys.readouterr()
    assert "ValueError: missing .env file" in captured.err
    # Ensure no traceback (no "Traceback" keyword)
    assert "Traceback" not in captured.err


def test_main_no_key_values_in_output(capsys, monkeypatch):
    """main() output should never contain actual key values."""
    # Mock Settings and Elasticsearch
    with tempfile.TemporaryDirectory() as tmpdir:
        out_path = Path(tmpdir) / "persona_keys.json"

        mock_settings = MagicMock()
        mock_settings.return_value.obs_es_url = "http://fake:9200"
        mock_settings.return_value.obs_es_admin_key = "fake-key"
        mock_settings.return_value.persona_keys_path = str(out_path)

        monkeypatch.setattr(mint_module, "Settings", mock_settings)
        monkeypatch.setattr(mint_module, "Elasticsearch", lambda *args, **kwargs: FakeEs(old_key_ids=[]))

        result = mint_module.main()

        assert result == 0
        captured = capsys.readouterr()
        # Check that no fake-encoded values appear in output
        assert "fake-encoded" not in captured.out
        assert "fake-encoded" not in captured.err
