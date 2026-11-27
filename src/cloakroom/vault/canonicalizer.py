"""Canonicalization of values for stable vault lookups.

Normalizes whitespace, case, honorifics, digit separators, and applies gazetteer
alias mappings. No fuzzy merging — only explicit transformations.
"""

import re
from typing import Final

# Common honorifics to strip for name canonicalization
_HONORIFICS: Final = frozenset(
    {
        "mr",
        "mrs",
        "ms",
        "miss",
        "dr",
        "prof",
        "sir",
        "madam",
        "master",
        "mx",
        "shri",
        "smt",
        "kumari",
    }
)

# Pattern for digit separators in account numbers, card numbers, etc.
_DIGIT_SEPARATOR_PATTERN: Final = re.compile(r"[\s\-_]+")


class Canonicalizer:
    """Canonicalizes values for deterministic vault lookups."""

    def __init__(self, *, alias_map: dict[str, str] | None = None) -> None:
        """Initialize canonicalizer with optional gazetteer alias mappings.

        Args:
            alias_map: Maps variant spellings/aliases to canonical forms.
                      Keys and values should both be pre-canonicalized.
        """
        self._alias_map = alias_map or {}

    def canonicalize(self, value: str, *, entity_type: str = "") -> str:
        """Canonicalize a value for stable lookup.

        Args:
            value: Raw value to canonicalize
            entity_type: Entity type hint (e.g. "PERSON", "ACCT")

        Returns:
            Canonicalized value suitable for keyed hashing
        """
        if not value:
            return ""

        # Step 1: Normalize whitespace
        canonical = " ".join(value.split())

        # Step 2: Lowercase for case-insensitive matching
        canonical = canonical.lower()

        # Step 3: Strip honorifics for person names
        if entity_type == "PERSON":
            canonical = self._strip_honorifics(canonical)

        # Step 4: Remove digit separators for numeric identifiers
        if entity_type in {"ACCT", "GOVID", "MED_ID", "PHONE"}:
            canonical = self._remove_digit_separators(canonical)

        # Step 5: Apply gazetteer alias mappings
        canonical = self._alias_map.get(canonical, canonical)

        return canonical

    def _strip_honorifics(self, name: str) -> str:
        """Remove common honorifics from names."""
        parts = name.split()
        filtered = [p for p in parts if p.rstrip(".") not in _HONORIFICS]
        return " ".join(filtered) if filtered else name

    def _remove_digit_separators(self, value: str) -> str:
        """Remove spaces, hyphens, underscores from digit strings."""
        return _DIGIT_SEPARATOR_PATTERN.sub("", value)

    def build_alias_map(self, aliases: dict[str, list[str]]) -> dict[str, str]:
        """Build canonicalized alias-to-canonical map from raw aliases.

        Args:
            aliases: Maps canonical forms to lists of aliases.
                    Example: {"aarav sharma": ["aarav", "a. sharma"]}

        Returns:
            Flattened alias map with all keys and values canonicalized.
        """
        alias_map: dict[str, str] = {}
        for canonical_raw, variant_list in aliases.items():
            canonical = self.canonicalize(canonical_raw, entity_type="PERSON")
            for variant in variant_list:
                canonical_variant = self.canonicalize(variant, entity_type="PERSON")
                if canonical_variant and canonical_variant != canonical:
                    alias_map[canonical_variant] = canonical
        return alias_map
