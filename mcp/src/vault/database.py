"""SQLite storage layer for encrypted secrets and bearer records."""

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class BearerRecord:
    id: str
    token_hash: str
    kek_encrypted: bytes
    kek_nonce: bytes
    salt: bytes
    name: str
    created_at: str
    revoked_at: str | None = None


@dataclass
class SecretRecord:
    id: str
    name: str
    encrypted_value: bytes
    nonce: bytes
    dek_encrypted: bytes
    dek_nonce: bytes
    bearer_id: str
    created_at: str
    updated_at: str


class SecretsDatabase:
    """SQLite-backed storage for encrypted secrets and bearer tokens."""

    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_db(self) -> None:
        with self._get_conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS bearers (
                    id TEXT PRIMARY KEY,
                    token_hash TEXT UNIQUE NOT NULL,
                    kek_encrypted BLOB NOT NULL,
                    kek_nonce BLOB NOT NULL,
                    salt BLOB NOT NULL,
                    name TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    revoked_at TEXT
                );

                CREATE TABLE IF NOT EXISTS secrets (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    encrypted_value BLOB NOT NULL,
                    nonce BLOB NOT NULL,
                    dek_encrypted BLOB NOT NULL,
                    dek_nonce BLOB NOT NULL,
                    bearer_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (bearer_id) REFERENCES bearers(id),
                    UNIQUE(name, bearer_id)
                );

                CREATE INDEX IF NOT EXISTS idx_bearers_token_hash
                    ON bearers(token_hash);
                CREATE INDEX IF NOT EXISTS idx_secrets_bearer_name
                    ON secrets(name, bearer_id);
            """)

    # ── Bearer operations ──────────────────────────────────────────

    def insert_bearer(self, bearer: BearerRecord) -> None:
        with self._get_conn() as conn:
            conn.execute(
                "INSERT INTO bearers "
                "(id, token_hash, kek_encrypted, kek_nonce, salt, name, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    bearer.id,
                    bearer.token_hash,
                    bearer.kek_encrypted,
                    bearer.kek_nonce,
                    bearer.salt,
                    bearer.name,
                    bearer.created_at,
                ),
            )

    def get_bearer_by_token_hash(self, token_hash: str) -> BearerRecord | None:
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT id, token_hash, kek_encrypted, kek_nonce, salt, "
                "name, created_at, revoked_at "
                "FROM bearers WHERE token_hash = ?",
                (token_hash,),
            ).fetchone()
        if row is None:
            return None
        return BearerRecord(*row)

    def revoke_bearer(self, bearer_id: str) -> bool:
        now = datetime.now(timezone.utc).isoformat()
        with self._get_conn() as conn:
            cursor = conn.execute(
                "UPDATE bearers SET revoked_at = ? "
                "WHERE id = ? AND revoked_at IS NULL",
                (now, bearer_id),
            )
            return cursor.rowcount > 0

    def list_bearers(self) -> list[BearerRecord]:
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT id, token_hash, kek_encrypted, kek_nonce, salt, "
                "name, created_at, revoked_at FROM bearers"
            ).fetchall()
        return [BearerRecord(*row) for row in rows]

    # ── Secret operations ──────────────────────────────────────────

    def insert_secret(self, secret: SecretRecord) -> None:
        with self._get_conn() as conn:
            conn.execute(
                "INSERT INTO secrets "
                "(id, name, encrypted_value, nonce, dek_encrypted, "
                "dek_nonce, bearer_id, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    secret.id,
                    secret.name,
                    secret.encrypted_value,
                    secret.nonce,
                    secret.dek_encrypted,
                    secret.dek_nonce,
                    secret.bearer_id,
                    secret.created_at,
                    secret.updated_at,
                ),
            )

    def get_secret(self, name: str, bearer_id: str) -> SecretRecord | None:
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT id, name, encrypted_value, nonce, dek_encrypted, "
                "dek_nonce, bearer_id, created_at, updated_at "
                "FROM secrets WHERE name = ? AND bearer_id = ?",
                (name, bearer_id),
            ).fetchone()
        if row is None:
            return None
        return SecretRecord(*row)

    def list_secrets(self, bearer_id: str) -> list[SecretRecord]:
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT id, name, encrypted_value, nonce, dek_encrypted, "
                "dek_nonce, bearer_id, created_at, updated_at "
                "FROM secrets WHERE bearer_id = ?",
                (bearer_id,),
            ).fetchall()
        return [SecretRecord(*row) for row in rows]

    def update_secret(self, secret: SecretRecord) -> bool:
        with self._get_conn() as conn:
            cursor = conn.execute(
                "UPDATE secrets SET encrypted_value = ?, nonce = ?, "
                "dek_encrypted = ?, dek_nonce = ?, updated_at = ? "
                "WHERE name = ? AND bearer_id = ?",
                (
                    secret.encrypted_value,
                    secret.nonce,
                    secret.dek_encrypted,
                    secret.dek_nonce,
                    secret.updated_at,
                    secret.name,
                    secret.bearer_id,
                ),
            )
            return cursor.rowcount > 0

    def delete_secret(self, name: str, bearer_id: str) -> bool:
        with self._get_conn() as conn:
            cursor = conn.execute(
                "DELETE FROM secrets WHERE name = ? AND bearer_id = ?",
                (name, bearer_id),
            )
            return cursor.rowcount > 0
