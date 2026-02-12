"""Tests for vault.database module."""

import os
import tempfile

import pytest

from vault.database import BearerRecord, SecretRecord, SecretsDatabase


@pytest.fixture
def db():
    """Create a temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        yield SecretsDatabase(db_path)
    finally:
        os.unlink(db_path)


@pytest.fixture
def sample_bearer():
    return BearerRecord(
        id="bearer-1",
        token_hash="abc123hash",
        kek_encrypted=b"encrypted-kek",
        kek_nonce=b"kek-nonce---",  # 12 bytes
        salt=b"salt-16-bytes---",  # 16 bytes
        name="test-bearer",
        created_at="2025-01-01T00:00:00+00:00",
    )


@pytest.fixture
def sample_secret():
    return SecretRecord(
        id="secret-1",
        name="API_KEY",
        encrypted_value=b"encrypted-value",
        nonce=b"value-nonce-",  # 12 bytes
        dek_encrypted=b"encrypted-dek",
        dek_nonce=b"dek-nonce---",  # 12 bytes
        bearer_id="bearer-1",
        created_at="2025-01-01T00:00:00+00:00",
        updated_at="2025-01-01T00:00:00+00:00",
    )


class TestBearerOperations:
    def test_insert_and_retrieve(self, db, sample_bearer):
        db.insert_bearer(sample_bearer)
        result = db.get_bearer_by_token_hash("abc123hash")
        assert result is not None
        assert result.id == "bearer-1"
        assert result.name == "test-bearer"

    def test_retrieve_nonexistent(self, db):
        assert db.get_bearer_by_token_hash("nonexistent") is None

    def test_revoke(self, db, sample_bearer):
        db.insert_bearer(sample_bearer)
        assert db.revoke_bearer("bearer-1") is True
        record = db.get_bearer_by_token_hash("abc123hash")
        assert record.revoked_at is not None

    def test_revoke_nonexistent(self, db):
        assert db.revoke_bearer("nonexistent") is False

    def test_revoke_already_revoked(self, db, sample_bearer):
        db.insert_bearer(sample_bearer)
        assert db.revoke_bearer("bearer-1") is True
        assert db.revoke_bearer("bearer-1") is False

    def test_list_bearers(self, db, sample_bearer):
        db.insert_bearer(sample_bearer)
        second = BearerRecord(
            id="bearer-2",
            token_hash="def456hash",
            kek_encrypted=b"encrypted-kek-2",
            kek_nonce=b"kek-nonce-2-",
            salt=b"salt-16-bytes-2-",
            name="second-bearer",
            created_at="2025-01-02T00:00:00+00:00",
        )
        db.insert_bearer(second)
        bearers = db.list_bearers()
        assert len(bearers) == 2

    def test_duplicate_token_hash_fails(self, db, sample_bearer):
        db.insert_bearer(sample_bearer)
        duplicate = BearerRecord(
            id="bearer-2",
            token_hash="abc123hash",  # same hash
            kek_encrypted=b"other",
            kek_nonce=b"other-nonce-",
            salt=b"other-salt------",
            name="duplicate",
            created_at="2025-01-01T00:00:00+00:00",
        )
        with pytest.raises(Exception):
            db.insert_bearer(duplicate)


class TestSecretOperations:
    def test_insert_and_retrieve(self, db, sample_bearer, sample_secret):
        db.insert_bearer(sample_bearer)
        db.insert_secret(sample_secret)
        result = db.get_secret("API_KEY", "bearer-1")
        assert result is not None
        assert result.encrypted_value == b"encrypted-value"

    def test_retrieve_nonexistent(self, db, sample_bearer):
        db.insert_bearer(sample_bearer)
        assert db.get_secret("MISSING", "bearer-1") is None

    def test_retrieve_wrong_bearer(self, db, sample_bearer, sample_secret):
        db.insert_bearer(sample_bearer)
        db.insert_secret(sample_secret)
        assert db.get_secret("API_KEY", "other-bearer") is None

    def test_list_secrets(self, db, sample_bearer, sample_secret):
        db.insert_bearer(sample_bearer)
        db.insert_secret(sample_secret)
        second = SecretRecord(
            id="secret-2",
            name="DB_PASSWORD",
            encrypted_value=b"encrypted-pw",
            nonce=b"pw-nonce----",
            dek_encrypted=b"encrypted-dek-2",
            dek_nonce=b"dek-nonce-2-",
            bearer_id="bearer-1",
            created_at="2025-01-01T00:00:00+00:00",
            updated_at="2025-01-01T00:00:00+00:00",
        )
        db.insert_secret(second)
        secrets_list = db.list_secrets("bearer-1")
        assert len(secrets_list) == 2

    def test_update_secret(self, db, sample_bearer, sample_secret):
        db.insert_bearer(sample_bearer)
        db.insert_secret(sample_secret)
        updated = SecretRecord(
            id=sample_secret.id,
            name="API_KEY",
            encrypted_value=b"new-encrypted",
            nonce=b"new-nonce----",
            dek_encrypted=b"new-dek-enc",
            dek_nonce=b"new-dek-nonc",
            bearer_id="bearer-1",
            created_at=sample_secret.created_at,
            updated_at="2025-06-01T00:00:00+00:00",
        )
        assert db.update_secret(updated) is True
        result = db.get_secret("API_KEY", "bearer-1")
        assert result.encrypted_value == b"new-encrypted"
        assert result.updated_at == "2025-06-01T00:00:00+00:00"

    def test_delete_secret(self, db, sample_bearer, sample_secret):
        db.insert_bearer(sample_bearer)
        db.insert_secret(sample_secret)
        assert db.delete_secret("API_KEY", "bearer-1") is True
        assert db.get_secret("API_KEY", "bearer-1") is None

    def test_delete_nonexistent(self, db, sample_bearer):
        db.insert_bearer(sample_bearer)
        assert db.delete_secret("MISSING", "bearer-1") is False

    def test_unique_name_per_bearer(self, db, sample_bearer, sample_secret):
        db.insert_bearer(sample_bearer)
        db.insert_secret(sample_secret)
        duplicate = SecretRecord(
            id="secret-dup",
            name="API_KEY",  # same name, same bearer
            encrypted_value=b"other",
            nonce=b"other-nonce-",
            dek_encrypted=b"other-dek",
            dek_nonce=b"other-d-nonc",
            bearer_id="bearer-1",
            created_at="2025-01-01T00:00:00+00:00",
            updated_at="2025-01-01T00:00:00+00:00",
        )
        with pytest.raises(Exception):
            db.insert_secret(duplicate)
