"""Gazetteer-based entity matching using Aho-Corasick for efficient multi-pattern search."""

from typing import NamedTuple

import ahocorasick_rs


class GazetteerMatch(NamedTuple):
    """A gazetteer match result."""

    value: str
    entity_type: str
    start: int
    end: int


class Gazetteer:
    """Multi-pattern matcher for known personal values using Aho-Corasick."""

    def __init__(self) -> None:
        """Initialize empty gazetteer."""
        self._automaton = ahocorasick_rs.AhoCorasick([])
        self._value_to_entity: dict[str, str] = {}

    def build(self, entries: list[tuple[str, str]]) -> None:
        """Build automaton from list of (value, entity_type) tuples.

        Args:
            entries: List of (canonicalized_value, entity_type) pairs
        """
        if not entries:
            self._automaton = ahocorasick_rs.AhoCorasick([])
            self._value_to_entity = {}
            return

        # Build value -> entity_type mapping
        self._value_to_entity = {value.lower(): entity_type for value, entity_type in entries}

        # Build automaton with case-insensitive patterns
        patterns = [value.lower() for value, _ in entries]
        self._automaton = ahocorasick_rs.AhoCorasick(patterns)

    def find_all(self, text: str) -> list[GazetteerMatch]:
        """Find all gazetteer matches in text.

        Uses longest-non-overlapping matching strategy. If multiple patterns
        match at the same position, keeps the longest. Protects already-minted
        placeholders by checking for bracket patterns.

        Args:
            text: Text to search

        Returns:
            List of non-overlapping matches, sorted by start position
        """
        if not text or not self._value_to_entity:
            return []

        # Case-insensitive search
        text_lower = text.lower()

        # Get all raw matches
        raw_matches = self._automaton.find_matches_as_indexes(text_lower)

        # Convert to GazetteerMatch objects
        all_matches: list[GazetteerMatch] = []
        for match_tuple in raw_matches:
            # Unpack the match tuple (may vary by ahocorasick_rs version)
            if len(match_tuple) == 3:
                pattern_idx, start_idx, end_idx = match_tuple
            else:
                # Fallback if format is different
                continue

            # Get the pattern that matched
            patterns = list(self._value_to_entity.keys())
            if pattern_idx >= len(patterns):
                continue

            pattern = patterns[pattern_idx]

            # Verify this isn't inside a placeholder like [PERSON_1]
            if self._is_inside_placeholder(text, start_idx, end_idx):
                continue

            # Extract original-case value from text
            original_value = text[start_idx:end_idx]
            entity_type = self._value_to_entity[pattern]

            all_matches.append(
                GazetteerMatch(
                    value=original_value,
                    entity_type=entity_type,
                    start=start_idx,
                    end=end_idx,
                )
            )

        # Apply longest-non-overlapping strategy
        return self._select_longest_non_overlapping(all_matches)

    def _is_inside_placeholder(self, text: str, start: int, end: int) -> bool:
        """Check if position range is inside a placeholder like [PERSON_1]."""
        # Look backwards for opening bracket
        bracket_start = text.rfind("[", max(0, start - 20), start)
        if bracket_start != -1:
            bracket_end = text.find("]", bracket_start, min(len(text), end + 20))
            if bracket_end != -1 and bracket_start < start < bracket_end:
                # Check if it looks like a placeholder
                placeholder_text = text[bracket_start : bracket_end + 1]
                if "_" in placeholder_text and placeholder_text[1:-1].replace("_", "").isalnum():
                    return True
        return False

    def _select_longest_non_overlapping(
        self, matches: list[GazetteerMatch]
    ) -> list[GazetteerMatch]:
        """Select longest non-overlapping matches using greedy algorithm.

        Args:
            matches: All potential matches

        Returns:
            Non-overlapping matches, longest first at each position
        """
        if not matches:
            return []

        # Sort by start position, then by length (longest first at same position)
        sorted_matches = sorted(matches, key=lambda m: (m.start, -(m.end - m.start)))

        selected: list[GazetteerMatch] = []
        covered_ranges: set[tuple[int, int]] = set()

        for match in sorted_matches:
            # Check if this match overlaps with any selected match
            overlaps = False
            for start, end in covered_ranges:
                if not (match.end <= start or match.start >= end):
                    overlaps = True
                    break

            if not overlaps:
                selected.append(match)
                covered_ranges.add((match.start, match.end))

        # Sort by start position for final output
        return sorted(selected, key=lambda m: m.start)
