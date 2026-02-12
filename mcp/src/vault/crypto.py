"""Cryptographic primitives for envelope encryption.

Key hierarchy:
    Server Master Key (SMK) - derived from env var passphrase via PBKDF2
        └── encrypts Key Encryption Key (KEK) - one per bearer
                └── encrypts Data Encryption Key (DEK) - one per secret
                        └── encrypts secret plaintext

All encryption uses AES-256-GCM (authenticated encryption with associated data).
"""

import hashlib
import os
import secrets

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

NONCE_SIZE = 12  # 96 bits, standard for AES-GCM
KEY_SIZE = 32  # 256 bits for AES-256
SALT_SIZE = 16  # 128 bits for PBKDF2
PBKDF2_ITERATIONS = 600_000  # OWASP 2023 recommendation for SHA-256


def derive_master_key(passphrase: str, salt: bytes) -> bytes:
    """Derive a 256-bit master key from a passphrase using PBKDF2-HMAC-SHA256."""
    kdf = PBKDF2HMAC(
        algorithm=SHA256(),
        length=KEY_SIZE,
        salt=salt,
        iterations=PBKDF2_ITERATIONS,
    )
    return kdf.derive(passphrase.encode("utf-8"))


def generate_key() -> bytes:
    """Generate a random 256-bit AES key."""
    return AESGCM.generate_key(bit_length=256)


def encrypt(key: bytes, plaintext: bytes) -> tuple[bytes, bytes]:
    """Encrypt plaintext with AES-256-GCM.

    Returns:
        Tuple of (ciphertext_with_tag, nonce).
    """
    nonce = os.urandom(NONCE_SIZE)
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(nonce, plaintext, None)
    return ciphertext, nonce


def decrypt(key: bytes, ciphertext: bytes, nonce: bytes) -> bytes:
    """Decrypt ciphertext with AES-256-GCM.

    Raises:
        cryptography.exceptions.InvalidTag: If authentication fails
            (wrong key, tampered ciphertext, or wrong nonce).
    """
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ciphertext, None)


def hash_token(token: str) -> str:
    """Produce a SHA-256 hex digest of a bearer token for storage."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generate_bearer_token() -> str:
    """Generate a cryptographically secure URL-safe bearer token (256 bits)."""
    return secrets.token_urlsafe(32)
