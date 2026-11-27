"""Encrypted SQLite storage for the vault.

Implements AES-256-GCM encryption with keyed HMAC-SHA256 for lookups.
Key is auto-generated locally with 0600 permissions (no OS keychain GUI blocking).
"""

import hashlib
import hmac
import secrets
import sqlite3
from pathlib import Path
from typing import Final

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from cloakroom.errors import VaultError

_SCHEMA: Final = """
CREATE TABLE IF NOT EXISTS entities (
    token       TEXT PRIMARY KEY,
    entity_type TEXT NOT NULL,
    keyed_hash  BLOB NOT NULL UNIQUE,
    ciphertext  BLOB NOT NULL,
    nonce       BLOB NOT NULL,
    first_seen  TEXT NOT NULL,
    hits        INTEGER NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_keyed_hash ON entities(keyed_hash);
"""

_KEY_SIZE: Final = 32  # AES-256
_NONCE_SIZE: Final = 12  # Recommended for AES-GCM
_HMAC_KEY_SIZE: Final = 32


class VaultStorage:
    """Encrypted persistent storage for placeholder mappings."""

    def __init__(self, *, vault_path: Path, key_path: Path) -> None:
        """Initialize storage with vault and key file paths.

        Args:
            vault_path: SQLite database file path
            key_path: Encryption key file path (created with 0600 if missing)
        """
        self._vault_path = vault_path
        self._key_path = key_path
        self._encryption_key = self._load_or_create_key()
        self._hmac_key = self._derive_hmac_key()
        self._cipher = AESGCM(self._encryption_key)
        self._init_database()

    def _load_or_create_key(self) -> bytes:
        """Load existing key or create new one with 0600 permissions."""
        if self._key_path.exists():
            try:
                return self._key_path.read_bytes()
            except (OSError, ValueError) as e:
                raise VaultError() from e

        # Generate new key
        key = secrets.token_bytes(_KEY_SIZE)
        try:
            # Create parent directory if needed
            self._key_path.parent.mkdir(parents=True, exist_ok=True)
            # Write with restricted permissions (owner read/write only)
            self._key_path.touch(mode=0o600, exist_ok=False)
            self._key_path.write_bytes(key)
            # Verify permissions were set correctly
            self._key_path.chmod(0o600)
        except (OSError, ValueError) as e:
            raise VaultError() from e

        return key

    def _derive_hmac_key(self) -> bytes:
        """Derive HMAC key from encryption key using HKDF-like approach."""
        # Simple KDF: HMAC-SHA256(encryption_key, "hmac_key")
        return hmac.new(self._encryption_key, b"cloakroom_hmac_key_v1", hashlib.sha256).digest()

    def _compute_keyed_hash(self, canonical_value: str) -> bytes:
        """Compute keyed HMAC-SHA256 for lookup."""
        return hmac.new(self._hmac_key, canonical_value.encode("utf-8"), hashlib.sha256).digest()

    def _init_database(self) -> None:
        """Initialize SQLite schema."""
        try:
            self._vault_path.parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(str(self._vault_path)) as conn:
                conn.executescript(_SCHEMA)
                conn.commit()
        except (sqlite3.Error, OSError) as e:
            raise VaultError() from e

    def lookup_by_canonical(self, canonical_value: str) -> str | None:
        """Look up existing placeholder by canonical value.

        Args:
            canonical_value: Canonicalized value to look up

        Returns:
            Placeholder token (e.g. "[PERSON_1]") or None if not found
        """
        keyed_hash = self._compute_keyed_hash(canonical_value)
        try:
            with sqlite3.connect(str(self._vault_path)) as conn:
                cursor = conn.execute(
                    "SELECT token, hits FROM entities WHERE keyed_hash = ?", (keyed_hash,)
                )
                row = cursor.fetchone()
                if row:
                    token: str = row[0]
                    hits: int = row[1]
                    # Increment hit counter
                    conn.execute("UPDATE entities SET hits = ? WHERE token = ?", (hits + 1, token))
                    conn.commit()
                    return token
        except sqlite3.Error as e:
            raise VaultError() from e

        return None

    def store_entity(
        self,
        *,
        token: str,
        entity_type: str,
        canonical_value: str,
        original_value: str,
        first_seen: str,
    ) -> None:
        """Store new entity in vault.

        Args:
            token: Placeholder token (e.g. "[PERSON_1]")
            entity_type: Entity type (e.g. "PERSON")
            canonical_value: Canonicalized value for lookup
            original_value: Original value to encrypt and store
            first_seen: Tool identifier that first produced this value
        """
        keyed_hash = self._compute_keyed_hash(canonical_value)
        nonce = secrets.token_bytes(_NONCE_SIZE)
        try:
            ciphertext = self._cipher.encrypt(nonce, original_value.encode("utf-8"), None)
        except Exception as e:
            raise VaultError() from e

        try:
            with sqlite3.connect(str(self._vault_path)) as conn:
                conn.execute(
                    """
                    INSERT INTO entities (token, entity_type, keyed_hash, ciphertext, nonce, first_seen, hits)
                    VALUES (?, ?, ?, ?, ?, ?, 1)
                    """,
                    (token, entity_type, keyed_hash, ciphertext, nonce, first_seen),
                )
                conn.commit()
        except sqlite3.IntegrityError:
            # Token or keyed_hash already exists — this is a vault consistency issue
            raise VaultError() from None
        except sqlite3.Error as e:
            raise VaultError() from e

    def decrypt_by_token(self, token: str) -> str | None:
        """Decrypt and return original value for a given token.

        Args:
            token: Placeholder token (e.g. "[PERSON_1]")

        Returns:
            Original decrypted value or None if token not found
        """
        try:
            with sqlite3.connect(str(self._vault_path)) as conn:
                cursor = conn.execute(
                    "SELECT ciphertext, nonce FROM entities WHERE token = ?", (token,)
                )
                row = cursor.fetchone()
                if not row:
                    return None

                ciphertext, nonce = row
                plaintext_bytes = self._cipher.decrypt(nonce, ciphertext, None)
                return plaintext_bytes.decode("utf-8")
        except Exception as e:
            raise VaultError() from e

    def list_all_tokens(self) -> list[str]:
        """List all placeholder tokens in vault."""
        try:
            with sqlite3.connect(str(self._vault_path)) as conn:
                cursor = conn.execute("SELECT token FROM entities ORDER BY token")
                return [row[0] for row in cursor.fetchall()]
        except sqlite3.Error as e:
            raise VaultError() from e

    def list_summary(self) -> list[dict[str, str | int]]:
        """List vault summary (token, entity_type, first_seen, hits) without values."""
        try:
            with sqlite3.connect(str(self._vault_path)) as conn:
                cursor = conn.execute(
                    """
                    SELECT token, entity_type, first_seen, hits
                    FROM entities
                    ORDER BY entity_type, token
                    """
                )
                return [
                    {
                        "token": row[0],
                        "entity_type": row[1],
                        "first_seen": row[2],
                        "hits": row[3],
                    }
                    for row in cursor.fetchall()
                ]
        except sqlite3.Error as e:
            raise VaultError() from e

    def wipe(self) -> None:
        """Delete all vault entries."""
        try:
            with sqlite3.connect(str(self._vault_path)) as conn:
                conn.execute("DELETE FROM entities")
                conn.commit()
        except sqlite3.Error as e:
            raise VaultError() from e

    def get_next_counter(self, entity_type: str) -> int:
        """Get next available counter for an entity type.

        Args:
            entity_type: Entity type (e.g. "PERSON")

        Returns:
            Next counter value (1-indexed)
        """
        try:
            with sqlite3.connect(str(self._vault_path)) as conn:
                cursor = conn.execute(
                    """
                    SELECT token FROM entities
                    WHERE entity_type = ?
                    ORDER BY token DESC
                    LIMIT 1
                    """,
                    (entity_type,),
                )
                row = cursor.fetchone()
                if not row:
                    return 1

                # Extract counter from token like "[PERSON_42]"
                token = row[0]
                # Format: [TYPE_N]
                if "_" in token:
                    counter_str = token.rsplit("_", 1)[-1].rstrip("]")
                    try:
                        return int(counter_str) + 1
                    except ValueError:
                        return 1
                return 1
        except sqlite3.Error as e:
            raise VaultError() from e

    def close(self) -> None:
        """Close storage connections (SQLite connections are created per-operation)."""
        pass  # No persistent connection to close
