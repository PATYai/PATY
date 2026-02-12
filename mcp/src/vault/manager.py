"""Secrets manager: business logic combining crypto + database.

This module ties together the encryption layer and the storage layer
to provide a complete secrets management API with bearer-based access control.
"""

import os
import uuid
from datetime import datetime, timezone

from .crypto import (
    SALT_SIZE,
    decrypt,
    derive_master_key,
    encrypt,
    generate_bearer_token,
    generate_key,
    hash_token,
)
from .database import BearerRecord, SecretRecord, SecretsDatabase


class SecretsManager:
    """Encrypted secrets manager with envelope encryption and bearer auth.

    Security model:
        - Each bearer gets a unique Key Encryption Key (KEK)
        - KEKs are encrypted at rest by a Server Master Key (SMK)
        - Each secret gets a unique Data Encryption Key (DEK)
        - DEKs are encrypted by the bearer's KEK
        - Bearer tokens are stored as SHA-256 hashes (never plaintext)

    To decrypt a secret you need:
        1. A valid (non-revoked) bearer token
        2. The server master passphrase (env var)
    Both are required; neither alone is sufficient.
    """

    def __init__(self, db: SecretsDatabase, master_passphrase: str):
        self._db = db
        self._master_passphrase = master_passphrase

    def _get_smk(self, salt: bytes) -> bytes:
        """Derive the Server Master Key from the passphrase and a per-bearer salt."""
        return derive_master_key(self._master_passphrase, salt)

    def _decrypt_kek(self, bearer: BearerRecord) -> bytes:
        """Decrypt a bearer's KEK using the server master key."""
        smk = self._get_smk(bearer.salt)
        return decrypt(smk, bearer.kek_encrypted, bearer.kek_nonce)

    def authenticate(self, token: str) -> BearerRecord | None:
        """Authenticate a bearer token. Returns the record if valid."""
        token_hash_val = hash_token(token)
        record = self._db.get_bearer_by_token_hash(token_hash_val)
        if record is None or record.revoked_at is not None:
            return None
        return record

    # ── Admin operations ───────────────────────────────────────────

    def create_bearer(self, name: str) -> tuple[str, str]:
        """Create a new authorized bearer.

        Returns:
            (bearer_id, bearer_token) — the token is shown once and cannot
            be recovered. Store it securely.
        """
        bearer_id = str(uuid.uuid4())
        token = generate_bearer_token()
        token_hash_val = hash_token(token)

        # Generate a unique KEK for this bearer
        kek = generate_key()

        # Encrypt the KEK with a per-bearer SMK derivation
        salt = os.urandom(SALT_SIZE)
        smk = self._get_smk(salt)
        kek_encrypted, kek_nonce = encrypt(smk, kek)

        now = datetime.now(timezone.utc).isoformat()
        self._db.insert_bearer(
            BearerRecord(
                id=bearer_id,
                token_hash=token_hash_val,
                kek_encrypted=kek_encrypted,
                kek_nonce=kek_nonce,
                salt=salt,
                name=name,
                created_at=now,
            )
        )
        return bearer_id, token

    def revoke_bearer(self, bearer_id: str) -> dict:
        """Revoke a bearer. Secrets remain but become inaccessible."""
        if self._db.revoke_bearer(bearer_id):
            return {"success": True, "bearer_id": bearer_id}
        return {"success": False, "error": "Bearer not found or already revoked"}

    def list_bearers(self) -> dict:
        """List all bearers (metadata only, no keys)."""
        records = self._db.list_bearers()
        return {
            "bearers": [
                {
                    "id": r.id,
                    "name": r.name,
                    "created_at": r.created_at,
                    "revoked": r.revoked_at is not None,
                    "revoked_at": r.revoked_at,
                }
                for r in records
            ],
            "count": len(records),
        }

    # ── Secret operations ──────────────────────────────────────────

    def store_secret(self, token: str, name: str, value: str) -> dict:
        """Encrypt and store a secret. Updates in-place if the name exists."""
        bearer = self.authenticate(token)
        if bearer is None:
            return {"success": False, "error": "Unauthorized"}

        kek = self._decrypt_kek(bearer)

        # Envelope encrypt: DEK wraps the value, KEK wraps the DEK
        dek = generate_key()
        encrypted_value, value_nonce = encrypt(dek, value.encode("utf-8"))
        dek_encrypted, dek_nonce = encrypt(kek, dek)

        now = datetime.now(timezone.utc).isoformat()

        existing = self._db.get_secret(name, bearer.id)
        if existing:
            updated = SecretRecord(
                id=existing.id,
                name=name,
                encrypted_value=encrypted_value,
                nonce=value_nonce,
                dek_encrypted=dek_encrypted,
                dek_nonce=dek_nonce,
                bearer_id=bearer.id,
                created_at=existing.created_at,
                updated_at=now,
            )
            self._db.update_secret(updated)
            return {"success": True, "name": name, "action": "updated"}

        self._db.insert_secret(
            SecretRecord(
                id=str(uuid.uuid4()),
                name=name,
                encrypted_value=encrypted_value,
                nonce=value_nonce,
                dek_encrypted=dek_encrypted,
                dek_nonce=dek_nonce,
                bearer_id=bearer.id,
                created_at=now,
                updated_at=now,
            )
        )
        return {"success": True, "name": name, "action": "created"}

    def get_secret(self, token: str, name: str) -> dict:
        """Decrypt and return a secret value."""
        bearer = self.authenticate(token)
        if bearer is None:
            return {"success": False, "error": "Unauthorized"}

        record = self._db.get_secret(name, bearer.id)
        if record is None:
            return {"success": False, "error": f"Secret '{name}' not found"}

        # Unwrap: KEK → DEK → plaintext
        kek = self._decrypt_kek(bearer)
        dek = decrypt(kek, record.dek_encrypted, record.dek_nonce)
        plaintext = decrypt(dek, record.encrypted_value, record.nonce)

        return {
            "success": True,
            "name": name,
            "value": plaintext.decode("utf-8"),
            "created_at": record.created_at,
            "updated_at": record.updated_at,
        }

    def list_secrets(self, token: str) -> dict:
        """List secret names (never values) for the authenticated bearer."""
        bearer = self.authenticate(token)
        if bearer is None:
            return {"success": False, "error": "Unauthorized"}

        records = self._db.list_secrets(bearer.id)
        return {
            "success": True,
            "secrets": [
                {
                    "name": r.name,
                    "created_at": r.created_at,
                    "updated_at": r.updated_at,
                }
                for r in records
            ],
            "count": len(records),
        }

    def delete_secret(self, token: str, name: str) -> dict:
        """Delete a secret permanently."""
        bearer = self.authenticate(token)
        if bearer is None:
            return {"success": False, "error": "Unauthorized"}

        if self._db.delete_secret(name, bearer.id):
            return {"success": True, "name": name}
        return {"success": False, "error": f"Secret '{name}' not found"}
