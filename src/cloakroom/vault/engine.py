"""Vault engine coordinating canonicalization, storage, and placeholder management."""

from pathlib import Path
from typing import Any

from cloakroom.contracts import RestoreResult
from cloakroom.errors import VaultError
from cloakroom.vault.canonicalizer import Canonicalizer
from cloakroom.vault.storage import VaultStorage

# Valid entity types from contracts.py
_VALID_ENTITY_TYPES = frozenset(
    {"PERSON", "ORG", "EMAIL", "PHONE", "ACCT", "GOVID", "MED_ID", "ADDR", "SECRET"}
)

# Identifier tier types (always sensitive)
_IDENTIFIER_TIER = frozenset({"EMAIL", "PHONE", "ACCT", "GOVID", "MED_ID", "SECRET"})


class VaultEngine:
    """Central vault engine for placeholder minting and restoration."""

    def __init__(
        self,
        *,
        vault_path: Path,
        key_path: Path,
        alias_map: dict[str, str] | None = None,
    ) -> None:
        """Initialize vault engine.

        Args:
            vault_path: SQLite database file path
            key_path: Encryption key file path
            alias_map: Pre-canonicalized alias mappings from gazetteer
        """
        self._canonicalizer = Canonicalizer(alias_map=alias_map)
        self._storage = VaultStorage(vault_path=vault_path, key_path=key_path)

    def mint_or_reuse(self, *, value: str, entity_type: str, first_seen: str = "unknown") -> str:
        """Mint new placeholder or reuse existing one for a canonical value.

        Args:
            value: Original value to store
            entity_type: Entity type (must be in VALID_ENTITY_TYPES)
            first_seen: Tool identifier that first produced this value

        Returns:
            Placeholder token (e.g. "[PERSON_1]")

        Raises:
            VaultError: If entity_type is invalid or storage fails
        """
        if entity_type not in _VALID_ENTITY_TYPES:
            raise VaultError()

        # Canonicalize for lookup
        canonical = self._canonicalizer.canonicalize(value, entity_type=entity_type)
        if not canonical:
            raise VaultError()

        # Check for existing placeholder
        existing = self._storage.lookup_by_canonical(canonical)
        if existing:
            return existing

        # Mint new placeholder
        counter = self._storage.get_next_counter(entity_type)
        token = f"[{entity_type}_{counter}]"

        self._storage.store_entity(
            token=token,
            entity_type=entity_type,
            canonical_value=canonical,
            original_value=value,
            first_seen=first_seen,
        )

        return token

    def restore(self, arguments: dict[str, Any]) -> RestoreResult:
        """Restore placeholders in arguments to real values.

        Per contracts.py: for invented/unknown placeholders set blocked=True +
        unknown_placeholders (token strings only — never values) and leave them
        unrestored; restore known placeholders locally; compute contains_identifier_tier.

        Args:
            arguments: Tool arguments that may contain placeholders

        Returns:
            RestoreResult with restored_arguments, used_placeholders,
            contains_identifier_tier, blocked status, and unknown_placeholders
        """
        from cloakroom.contracts import CloakedEntity

        restored_arguments = self._restore_nested(arguments)
        unknown_tokens: list[str] = []
        used_placeholders: list[CloakedEntity] = []
        contains_identifier = False

        # Scan for placeholders
        for token in self._extract_placeholders(arguments):
            original_value = self._storage.decrypt_by_token(token)
            if original_value is None:
                # Unknown/invented placeholder
                unknown_tokens.append(token)
            else:
                # Known placeholder
                entity_type = self._extract_entity_type(token)
                tier = "identifier" if entity_type in _IDENTIFIER_TIER else "contextual"
                used_placeholders.append(
                    CloakedEntity(
                        placeholder=token,
                        entity_type=entity_type,
                        tier=tier,
                        stage="vault_restore",
                    )
                )
                if tier == "identifier":
                    contains_identifier = True

        blocked = len(unknown_tokens) > 0

        return RestoreResult(
            restored_arguments=restored_arguments if not blocked else arguments,
            used_placeholders=used_placeholders,
            contains_identifier_tier=contains_identifier,
            blocked=blocked,
            unknown_placeholders=unknown_tokens,
        )

    def _restore_nested(self, obj: Any) -> Any:
        """Recursively restore placeholders in nested structures."""
        if isinstance(obj, dict):
            return {k: self._restore_nested(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._restore_nested(item) for item in obj]
        elif isinstance(obj, str):
            return self._restore_string(obj)
        else:
            return obj

    def _restore_string(self, text: str) -> str:
        """Restore all placeholders in a string."""
        import re

        # Match placeholders: [TYPE_N]
        pattern = r"\[([A-Z_]+)_(\d+)\]"

        def replace_match(match: re.Match[str]) -> str:
            token = match.group(0)
            value = self._storage.decrypt_by_token(token)
            return value if value is not None else token

        return re.sub(pattern, replace_match, text)

    def _extract_placeholders(self, obj: Any) -> set[str]:
        """Extract all placeholder tokens from nested structure."""
        import re

        placeholders: set[tuple[str, str]] = set()
        pattern = re.compile(r"\[([A-Z_]+)_(\d+)\]")

        def scan(o: Any) -> None:
            if isinstance(o, dict):
                for v in o.values():
                    scan(v)
            elif isinstance(o, list):
                for item in o:
                    scan(item)
            elif isinstance(o, str):
                matches = pattern.findall(o)
                for match in matches:
                    placeholders.add(match)

        scan(obj)
        # Convert tuples back to full tokens
        return {f"[{entity_type}_{counter}]" for entity_type, counter in placeholders}

    def _extract_entity_type(self, token: str) -> str:
        """Extract entity type from placeholder token."""
        # Token format: [TYPE_N]
        if token.startswith("[") and token.endswith("]") and "_" in token:
            return token[1:].split("_")[0]
        return "SECRET"  # Fallback

    def list_vault_summary(self) -> list[dict[str, Any]]:
        """Return vault summary for Control Room display."""
        return self._storage.list_summary()

    def wipe(self) -> None:
        """Delete all vault entries."""
        self._storage.wipe()

    def close(self) -> None:
        """Close vault storage."""
        self._storage.close()
