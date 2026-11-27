"""Pattern-based detectors with checksum validation for identifiers.

Implements detection for:
- Aadhaar (Verhoeff checksum)
- Card numbers (Luhn checksum)
- PAN, IFSC
- Email, phone
- API keys (high-entropy strings)
- Custom patterns from configuration
"""

import re
from typing import Final, NamedTuple

# Verhoeff checksum table for Aadhaar validation
_VERHOEFF_D: Final = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
    [1, 2, 3, 4, 0, 6, 7, 8, 9, 5],
    [2, 3, 4, 0, 1, 7, 8, 9, 5, 6],
    [3, 4, 0, 1, 2, 8, 9, 5, 6, 7],
    [4, 0, 1, 2, 3, 9, 5, 6, 7, 8],
    [5, 9, 8, 7, 6, 0, 4, 3, 2, 1],
    [6, 5, 9, 8, 7, 1, 0, 4, 3, 2],
    [7, 6, 5, 9, 8, 2, 1, 0, 4, 3],
    [8, 7, 6, 5, 9, 3, 2, 1, 0, 4],
    [9, 8, 7, 6, 5, 4, 3, 2, 1, 0],
]

_VERHOEFF_P: Final = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
    [1, 5, 7, 6, 2, 8, 3, 0, 9, 4],
    [5, 8, 0, 3, 7, 9, 6, 1, 4, 2],
    [8, 9, 1, 6, 0, 4, 3, 5, 2, 7],
    [9, 4, 5, 3, 1, 2, 6, 8, 7, 0],
    [4, 2, 8, 6, 5, 7, 3, 9, 0, 1],
    [2, 7, 9, 3, 8, 0, 6, 4, 1, 5],
    [7, 0, 4, 6, 9, 1, 3, 2, 5, 8],
]

_VERHOEFF_INV: Final = [0, 4, 3, 2, 1, 5, 6, 7, 8, 9]


class Detection(NamedTuple):
    """A detected entity match."""

    value: str
    entity_type: str
    start: int
    end: int


def _validate_verhoeff(digits: str) -> bool:
    """Validate Aadhaar checksum using Verhoeff algorithm."""
    if len(digits) != 12 or not digits.isdigit():
        return False

    c = 0
    for i, digit in enumerate(reversed(digits)):
        c = _VERHOEFF_D[c][_VERHOEFF_P[(i + 1) % 8][int(digit)]]
    return c == 0


def _validate_luhn(digits: str) -> bool:
    """Validate card number using Luhn algorithm."""
    if len(digits) < 13 or not digits.isdigit():
        return False

    total = 0
    for i, digit in enumerate(reversed(digits)):
        d = int(digit)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


class Detector:
    """Pattern-based detector with checksum validation."""

    # PAN format: 5 letters, 4 digits, 1 letter
    _PAN_PATTERN: Final = re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b")

    # IFSC format: 4 letters, zero, 6 alphanumerics
    _IFSC_PATTERN: Final = re.compile(r"\b[A-Z]{4}0[A-Z0-9]{6}\b")

    # Email pattern (basic)
    _EMAIL_PATTERN: Final = re.compile(r"\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b")

    # Phone pattern (Indian-style with optional +91 prefix)
    _PHONE_PATTERN: Final = re.compile(r"\b(?:\+91[\s-]?)?[6-9]\d{9}\b")

    # Aadhaar: 12 digits (possibly with spaces/dashes)
    _AADHAAR_PATTERN: Final = re.compile(r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}\b")

    # Card number: 13-19 digits (possibly with spaces/dashes every 4 digits)
    _CARD_PATTERN: Final = re.compile(r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{1,7}\b")

    # API keys: known prefixes with high-entropy strings
    _API_KEY_PATTERN: Final = re.compile(
        r"(?:sk|pk|api|token|key)[-_]\w*[-_]?[a-zA-Z0-9]{24,}", re.IGNORECASE
    )

    def __init__(self, *, custom_patterns: list[tuple[str, str, str]] | None = None) -> None:
        """Initialize detector with optional custom patterns.

        Args:
            custom_patterns: List of (name, entity_type, pattern) tuples
        """
        self._custom_patterns: list[tuple[str, str, re.Pattern[str]]] = []
        if custom_patterns:
            for name, entity_type, pattern_str in custom_patterns:
                try:
                    compiled = re.compile(pattern_str)
                    self._custom_patterns.append((name, entity_type, compiled))
                except re.error:
                    # Skip invalid patterns
                    pass

    def detect_all(self, text: str) -> list[Detection]:
        """Detect all entities in text with checksum validation where applicable.

        Args:
            text: Text to scan

        Returns:
            List of detections (may overlap; caller must deduplicate)
        """
        detections: list[Detection] = []

        # Custom patterns first
        for _name, entity_type, pattern in self._custom_patterns:
            for match in pattern.finditer(text):
                detections.append(
                    Detection(
                        value=match.group(),
                        entity_type=entity_type,
                        start=match.start(),
                        end=match.end(),
                    )
                )

        # Aadhaar with Verhoeff validation
        for match in self._AADHAAR_PATTERN.finditer(text):
            digits = re.sub(r"[\s-]", "", match.group())
            if _validate_verhoeff(digits):
                detections.append(
                    Detection(
                        value=match.group(),
                        entity_type="GOVID",
                        start=match.start(),
                        end=match.end(),
                    )
                )

        # Card number with Luhn validation
        for match in self._CARD_PATTERN.finditer(text):
            digits = re.sub(r"[\s-]", "", match.group())
            if _validate_luhn(digits):
                detections.append(
                    Detection(
                        value=match.group(),
                        entity_type="ACCT",
                        start=match.start(),
                        end=match.end(),
                    )
                )

        # PAN
        for match in self._PAN_PATTERN.finditer(text):
            detections.append(
                Detection(
                    value=match.group(),
                    entity_type="GOVID",
                    start=match.start(),
                    end=match.end(),
                )
            )

        # IFSC
        for match in self._IFSC_PATTERN.finditer(text):
            detections.append(
                Detection(
                    value=match.group(),
                    entity_type="ACCT",
                    start=match.start(),
                    end=match.end(),
                )
            )

        # Email
        for match in self._EMAIL_PATTERN.finditer(text):
            detections.append(
                Detection(
                    value=match.group(),
                    entity_type="EMAIL",
                    start=match.start(),
                    end=match.end(),
                )
            )

        # Phone
        for match in self._PHONE_PATTERN.finditer(text):
            # Normalize phone number
            re.sub(r"[\s-]", "", match.group())
            detections.append(
                Detection(
                    value=match.group(),
                    entity_type="PHONE",
                    start=match.start(),
                    end=match.end(),
                )
            )

        # API keys
        for match in self._API_KEY_PATTERN.finditer(text):
            detections.append(
                Detection(
                    value=match.group(),
                    entity_type="SECRET",
                    start=match.start(),
                    end=match.end(),
                )
            )

        return detections
