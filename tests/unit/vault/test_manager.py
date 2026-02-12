"""Tests for vault.manager — end-to-end encryption roundtrip tests."""

import os
import tempfile

import pytest

from vault.database import SecretsDatabase
from vault.manager import SecretsManager


@pytest.fixture
def manager():
    """Create a SecretsManager backed by a temporary database."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        db = SecretsDatabase(db_path)
        yield SecretsManager(db, master_passphrase="test-master-key")
    finally:
        os.unlink(db_path)


@pytest.fixture
def bearer_token(manager):
    """Create a bearer and return its token."""
    _, token = manager.create_bearer("test-user")
    return token


class TestBearerLifecycle:
    def test_create_bearer(self, manager):
        bearer_id, token = manager.create_bearer("my-app")
        assert bearer_id
        assert token
        assert manager.authenticate(token) is not None

    def test_authenticate_invalid_token(self, manager):
        assert manager.authenticate("bogus-token") is None

    def test_revoke_bearer(self, manager):
        bearer_id, token = manager.create_bearer("revoke-me")
        assert manager.authenticate(token) is not None
        result = manager.revoke_bearer(bearer_id)
        assert result["success"] is True
        assert manager.authenticate(token) is None

    def test_revoke_nonexistent(self, manager):
        result = manager.revoke_bearer("no-such-id")
        assert result["success"] is False

    def test_list_bearers(self, manager):
        manager.create_bearer("first")
        manager.create_bearer("second")
        result = manager.list_bearers()
        assert result["count"] == 2
        names = {b["name"] for b in result["bearers"]}
        assert names == {"first", "second"}


class TestSecretOperations:
    def test_store_and_retrieve(self, manager, bearer_token):
        store_result = manager.store_secret(bearer_token, "MY_SECRET", "s3cret!")
        assert store_result["success"] is True
        assert store_result["action"] == "created"

        get_result = manager.get_secret(bearer_token, "MY_SECRET")
        assert get_result["success"] is True
        assert get_result["value"] == "s3cret!"

    def test_store_updates_existing(self, manager, bearer_token):
        manager.store_secret(bearer_token, "KEY", "v1")
        result = manager.store_secret(bearer_token, "KEY", "v2")
        assert result["action"] == "updated"

        get_result = manager.get_secret(bearer_token, "KEY")
        assert get_result["value"] == "v2"

    def test_get_nonexistent_secret(self, manager, bearer_token):
        result = manager.get_secret(bearer_token, "MISSING")
        assert result["success"] is False

    def test_unauthorized_store(self, manager):
        result = manager.store_secret("bad-token", "KEY", "value")
        assert result["success"] is False
        assert result["error"] == "Unauthorized"

    def test_unauthorized_get(self, manager):
        result = manager.get_secret("bad-token", "KEY")
        assert result["success"] is False

    def test_list_secrets(self, manager, bearer_token):
        manager.store_secret(bearer_token, "A", "1")
        manager.store_secret(bearer_token, "B", "2")
        result = manager.list_secrets(bearer_token)
        assert result["success"] is True
        assert result["count"] == 2
        names = {s["name"] for s in result["secrets"]}
        assert names == {"A", "B"}

    def test_list_secrets_unauthorized(self, manager):
        result = manager.list_secrets("bad-token")
        assert result["success"] is False

    def test_delete_secret(self, manager, bearer_token):
        manager.store_secret(bearer_token, "TEMP", "value")
        result = manager.delete_secret(bearer_token, "TEMP")
        assert result["success"] is True
        assert manager.get_secret(bearer_token, "TEMP")["success"] is False

    def test_delete_nonexistent(self, manager, bearer_token):
        result = manager.delete_secret(bearer_token, "NOPE")
        assert result["success"] is False

    def test_delete_unauthorized(self, manager):
        result = manager.delete_secret("bad-token", "KEY")
        assert result["success"] is False


class TestIsolation:
    """Verify that bearers cannot access each other's secrets."""

    def test_bearer_isolation(self, manager):
        _, token_a = manager.create_bearer("user-a")
        _, token_b = manager.create_bearer("user-b")

        manager.store_secret(token_a, "SHARED_NAME", "a-value")
        manager.store_secret(token_b, "SHARED_NAME", "b-value")

        result_a = manager.get_secret(token_a, "SHARED_NAME")
        result_b = manager.get_secret(token_b, "SHARED_NAME")
        assert result_a["value"] == "a-value"
        assert result_b["value"] == "b-value"

    def test_revoked_bearer_cannot_read(self, manager):
        bearer_id, token = manager.create_bearer("temp")
        manager.store_secret(token, "KEY", "value")
        manager.revoke_bearer(bearer_id)
        result = manager.get_secret(token, "KEY")
        assert result["success"] is False
        assert result["error"] == "Unauthorized"


class TestEncryptionAtRest:
    """Verify that raw database contents are encrypted."""

    def test_value_not_stored_plaintext(self, manager, bearer_token):
        manager.store_secret(bearer_token, "SENSITIVE", "plaintext-password")
        # Access the underlying DB directly
        bearer = manager.authenticate(bearer_token)
        record = manager._db.get_secret("SENSITIVE", bearer.id)
        assert b"plaintext-password" not in record.encrypted_value
        assert b"plaintext-password" not in record.dek_encrypted
