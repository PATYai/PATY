"""Tests for vault.crypto module."""

import os

import pytest

from vault.crypto import (
    decrypt,
    derive_master_key,
    encrypt,
    generate_bearer_token,
    generate_key,
    hash_token,
)


class TestDeriveMasterKey:
    def test_deterministic_with_same_salt(self):
        salt = os.urandom(16)
        k1 = derive_master_key("passphrase", salt)
        k2 = derive_master_key("passphrase", salt)
        assert k1 == k2

    def test_different_with_different_salt(self):
        k1 = derive_master_key("passphrase", os.urandom(16))
        k2 = derive_master_key("passphrase", os.urandom(16))
        assert k1 != k2

    def test_different_with_different_passphrase(self):
        salt = os.urandom(16)
        k1 = derive_master_key("passphrase1", salt)
        k2 = derive_master_key("passphrase2", salt)
        assert k1 != k2

    def test_key_length(self):
        key = derive_master_key("test", os.urandom(16))
        assert len(key) == 32  # 256 bits


class TestEncryptDecrypt:
    def test_roundtrip(self):
        key = generate_key()
        plaintext = b"hello world"
        ciphertext, nonce = encrypt(key, plaintext)
        result = decrypt(key, ciphertext, nonce)
        assert result == plaintext

    def test_ciphertext_differs_from_plaintext(self):
        key = generate_key()
        plaintext = b"sensitive data"
        ciphertext, _ = encrypt(key, plaintext)
        assert ciphertext != plaintext

    def test_different_nonce_each_time(self):
        key = generate_key()
        _, nonce1 = encrypt(key, b"data")
        _, nonce2 = encrypt(key, b"data")
        assert nonce1 != nonce2

    def test_wrong_key_fails(self):
        key1 = generate_key()
        key2 = generate_key()
        ciphertext, nonce = encrypt(key1, b"secret")
        with pytest.raises(Exception):
            decrypt(key2, ciphertext, nonce)

    def test_tampered_ciphertext_fails(self):
        key = generate_key()
        ciphertext, nonce = encrypt(key, b"secret")
        tampered = bytearray(ciphertext)
        tampered[0] ^= 0xFF
        with pytest.raises(Exception):
            decrypt(key, bytes(tampered), nonce)

    def test_empty_plaintext(self):
        key = generate_key()
        ciphertext, nonce = encrypt(key, b"")
        assert decrypt(key, ciphertext, nonce) == b""

    def test_large_plaintext(self):
        key = generate_key()
        plaintext = os.urandom(1_000_000)  # 1 MB
        ciphertext, nonce = encrypt(key, plaintext)
        assert decrypt(key, ciphertext, nonce) == plaintext


class TestGenerateKey:
    def test_key_length(self):
        assert len(generate_key()) == 32

    def test_keys_are_unique(self):
        keys = {generate_key() for _ in range(100)}
        assert len(keys) == 100


class TestHashToken:
    def test_deterministic(self):
        assert hash_token("abc") == hash_token("abc")

    def test_different_tokens_different_hashes(self):
        assert hash_token("token1") != hash_token("token2")

    def test_hex_format(self):
        h = hash_token("test")
        assert len(h) == 64  # SHA-256 hex digest
        assert all(c in "0123456789abcdef" for c in h)


class TestGenerateBearerToken:
    def test_tokens_are_unique(self):
        tokens = {generate_bearer_token() for _ in range(100)}
        assert len(tokens) == 100

    def test_token_is_url_safe(self):
        token = generate_bearer_token()
        assert all(c.isalnum() or c in "-_" for c in token)
