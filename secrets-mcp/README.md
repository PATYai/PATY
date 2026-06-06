This is the secrets server. 

Server Master Key (SMK)  ← from env var, derived via PBKDF2
    └── encrypts → Key Encryption Key (KEK)  ← per-bearer, stored in DB
            └── encrypts → Data Encryption Key (DEK)  ← per-secret, stored alongside ciphertext
                    └── encrypts → Secret Value (plaintext)

SQLite for zero infra. 
Storage: SQLite (zero infrastructure), AES-256-GCM (authenticated encryption)

MCP Tools: store_secret, get_secret, list_secrets, delete_secret, create_bearer, revoke_bearer
