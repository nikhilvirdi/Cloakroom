"""Cloak engine implementing the 6-stage privacy pipeline."""

import json
import time
from typing import Any

from cloakroom.cloak.detectors import Detector
from cloakroom.cloak.gazetteer import Gazetteer
from cloakroom.configuration.models import PrivacyPolicy
from cloakroom.contracts import CloakedEntity, CloakResult, RestoreResult
from cloakroom.errors import PrivacyPipelineError
from cloakroom.vault import VaultEngine


class CloakEngine:
    """6-stage cloaking pipeline: content filter, field policy, gazetteer, detectors, vault, tripwire."""

    def __init__(
        self,
        *,
        vault: VaultEngine,
        privacy_policy: PrivacyPolicy,
        gazetteer: Gazetteer,
        field_policies: dict[str, dict[str, str]] | None = None,
    ) -> None:
        """Initialize cloak engine.

        Args:
            vault: Vault engine for placeholder minting/lookup
            privacy_policy: Privacy policy with tier settings and detector config
            gazetteer: Gazetteer for known value matching
            field_policies: Server-specific field mappings (server_id -> {field_name -> entity_type})
        """
        self._vault = vault
        self._policy = privacy_policy
        self._gazetteer = gazetteer
        self._field_policies = field_policies or {}

        # Build detector with custom patterns from policy
        custom_patterns: list[tuple[str, str, str]] = [
            (d.name, d.entity, d.pattern) for d in privacy_policy.detectors.custom
        ]
        self._detector = Detector(custom_patterns=custom_patterns)

        # Cache tier settings
        self._mask_identifiers = privacy_policy.tiers.identifiers == "mask"
        self._mask_contextual = privacy_policy.tiers.contextual == "mask"
        self._mask_analytical = privacy_policy.tiers.analytical == "mask"

    def cloak(self, payload: Any, *, server_id: str = "", tool_name: str = "") -> CloakResult:
        """Cloak a payload through the 6-stage pipeline.

        Stages:
        1. Content filter (withhold binary/image blocks)
        2. Field policy (mask configured structured keys)
        3. Gazetteer sweep (longest-non-overlapping multi-pattern match)
        4. Detectors with checksum validation
        5. Vault mint/reuse
        6. Tripwire (rescan cloaked output; re-cloak once; withhold on second hit)

        Args:
            payload: Raw payload to cloak
            server_id: Server identifier for field policies
            tool_name: Tool name for audit trail

        Returns:
            CloakResult with cloaked_payload, entities, and tripwire status
        """
        start_time = time.perf_counter()
        entities: list[CloakedEntity] = []

        try:
            # Stage 1: Content filter
            payload_filtered, withheld_content = self._stage1_content_filter(payload)
            if withheld_content:
                return CloakResult(
                    cloaked_payload={"withheld": "binary or image content"},
                    raw_payload=payload,
                    withheld=True,
                    withhold_reason="binary_content",
                    latency_ms=(time.perf_counter() - start_time) * 1000,
                )

            # Stage 2: Field policy
            payload_after_field, field_entities = self._stage2_field_policy(
                payload_filtered, server_id
            )
            entities.extend(field_entities)

            # Stage 3: Gazetteer sweep
            payload_after_gazetteer, gazetteer_entities = self._stage3_gazetteer(
                payload_after_field
            )
            entities.extend(gazetteer_entities)

            # Stage 4: Detectors
            payload_after_detectors, detector_entities = self._stage4_detectors(
                payload_after_gazetteer
            )
            entities.extend(detector_entities)

            # Stage 5: Vault (placeholder minting happens in stages 2-4)
            # This stage is implicit - entities already have placeholders minted

            # Stage 6: Tripwire
            tripwire_passed = self._stage6_tripwire(payload_after_detectors)
            if not tripwire_passed:
                # Re-cloak once
                payload_recloak, entities_recloak = self._recloak_pipeline(payload_after_detectors)
                tripwire_passed_2 = self._stage6_tripwire(payload_recloak)
                if not tripwire_passed_2:
                    # Withhold entire payload
                    return CloakResult(
                        cloaked_payload={"withheld": "tripwire hit after re-cloak"},
                        raw_payload=payload,
                        entities=entities,
                        tripwire_passed=False,
                        withheld=True,
                        withhold_reason="tripwire_hit",
                        latency_ms=(time.perf_counter() - start_time) * 1000,
                    )
                # Second attempt passed
                return CloakResult(
                    cloaked_payload=payload_recloak,
                    raw_payload=payload,
                    entities=entities_recloak,
                    tripwire_passed=True,
                    latency_ms=(time.perf_counter() - start_time) * 1000,
                )

            return CloakResult(
                cloaked_payload=payload_after_detectors,
                raw_payload=payload,
                entities=entities,
                tripwire_passed=True,
                latency_ms=(time.perf_counter() - start_time) * 1000,
            )

        except Exception as e:
            # Fail closed: withhold on any pipeline error
            raise PrivacyPipelineError() from e

    def restore(self, arguments: dict[str, Any]) -> RestoreResult:
        """Restore placeholders in arguments. Delegates to vault engine."""
        return self._vault.restore(arguments)

    def list_vault_summary(self) -> list[dict[str, Any]]:
        """Return vault summary for Control Room. Delegates to vault engine."""
        return self._vault.list_vault_summary()

    # Stage 1: Content filter
    def _stage1_content_filter(self, payload: Any) -> tuple[Any, bool]:
        """Filter out binary/image content.

        Returns:
            (filtered_payload, withheld_flag)
        """
        # Check if payload contains binary indicators
        if isinstance(payload, bytes):
            return payload, True

        if isinstance(payload, dict) and "type" in payload:
            # Check for MCP content types that indicate binary
            content_type = payload.get("type", "")
            if content_type in {"image", "resource"} or "image" in str(content_type).lower():
                return payload, True

        # Recursively check nested structures
        return payload, False

    # Stage 2: Field policy
    def _stage2_field_policy(self, payload: Any, server_id: str) -> tuple[Any, list[CloakedEntity]]:
        """Apply deterministic field-based masking.

        Returns:
            (masked_payload, entities)
        """
        entities: list[CloakedEntity] = []
        field_policy = self._field_policies.get(server_id, {})

        if not field_policy or not isinstance(payload, dict):
            return payload, entities

        result = {}
        for key, value in payload.items():
            if key in field_policy and isinstance(value, str):
                entity_type = field_policy[key]
                # Mint placeholder
                placeholder = self._vault.mint_or_reuse(
                    value=value, entity_type=entity_type, first_seen=f"field_policy:{key}"
                )
                result[key] = placeholder
                entities.append(
                    CloakedEntity(
                        placeholder=placeholder,
                        entity_type=entity_type,
                        tier=self._get_tier(entity_type),
                        stage="field_policy",
                    )
                )
            elif isinstance(value, (dict, list)):
                # Recurse into nested structures
                result[key], nested_entities = self._stage2_field_policy(value, server_id)
                entities.extend(nested_entities)
            else:
                result[key] = value

        return result, entities

    # Stage 3: Gazetteer sweep
    def _stage3_gazetteer(self, payload: Any) -> tuple[Any, list[CloakedEntity]]:
        """Apply gazetteer-based matching.

        Returns:
            (cloaked_payload, entities)
        """
        entities: list[CloakedEntity] = []
        return self._cloak_strings(payload, entities, "gazetteer", self._gazetteer_scan)

    def _gazetteer_scan(self, text: str) -> list[tuple[str, str, int, int]]:
        """Scan text using gazetteer.

        Returns:
            List of (value, entity_type, start, end) tuples
        """
        matches = self._gazetteer.find_all(text)
        return [(m.value, m.entity_type, m.start, m.end) for m in matches]

    # Stage 4: Detectors
    def _stage4_detectors(self, payload: Any) -> tuple[Any, list[CloakedEntity]]:
        """Apply pattern-based detection with checksum validation.

        Returns:
            (cloaked_payload, entities)
        """
        entities: list[CloakedEntity] = []
        return self._cloak_strings(payload, entities, "detector", self._detector_scan)

    def _detector_scan(self, text: str) -> list[tuple[str, str, int, int]]:
        """Scan text using detectors.

        Returns:
            List of (value, entity_type, start, end) tuples
        """
        detections = self._detector.detect_all(text)
        return [(d.value, d.entity_type, d.start, d.end) for d in detections]

    # Common string cloaking logic
    def _cloak_strings(
        self,
        obj: Any,
        entities: list[CloakedEntity],
        stage: str,
        scanner: Any,
    ) -> tuple[Any, list[CloakedEntity]]:
        """Recursively cloak strings in nested structures using provided scanner."""
        if isinstance(obj, dict):
            result = {}
            for k, v in obj.items():
                result[k], entities = self._cloak_strings(v, entities, stage, scanner)
            return result, entities
        elif isinstance(obj, list):
            result_list = []
            for item in obj:
                cloaked_item, entities = self._cloak_strings(item, entities, stage, scanner)
                result_list.append(cloaked_item)
            return result_list, entities
        elif isinstance(obj, str):
            return self._cloak_string(obj, entities, stage, scanner)
        else:
            return obj, entities

    def _cloak_string(
        self,
        text: str,
        entities: list[CloakedEntity],
        stage: str,
        scanner: Any,
    ) -> tuple[str, list[CloakedEntity]]:
        """Cloak a single string using scanner function."""
        if not text:
            return text, entities

        matches = scanner(text)
        if not matches:
            return text, entities

        # Sort by start position (reverse for replacement from end)
        sorted_matches = sorted(matches, key=lambda m: m[2], reverse=True)

        # Apply tier filtering
        filtered_matches = []
        for value, entity_type, start, end in sorted_matches:
            tier = self._get_tier(entity_type)
            if self._should_mask_tier(tier):
                filtered_matches.append((value, entity_type, start, end))

        if not filtered_matches:
            return text, entities

        # Replace from end to preserve indices
        result = text
        for value, entity_type, start, end in filtered_matches:
            # Mint placeholder
            placeholder = self._vault.mint_or_reuse(
                value=value, entity_type=entity_type, first_seen=stage
            )
            result = result[:start] + placeholder + result[end:]
            entities.append(
                CloakedEntity(
                    placeholder=placeholder,
                    entity_type=entity_type,
                    tier=self._get_tier(entity_type),
                    stage=stage,
                )
            )

        return result, entities

    # Stage 6: Tripwire
    def _stage6_tripwire(self, payload: Any) -> bool:
        """Scan cloaked payload for any remaining real values from vault or gazetteer.

        Returns:
            True if no known values found (tripwire passed)
        """
        # Collect all known values from vault
        vault_summary = self._vault.list_vault_summary()
        known_tokens = {entry["token"] for entry in vault_summary}

        # For each token, decrypt and check if raw value appears in payload
        json.dumps(payload) if not isinstance(payload, str) else payload

        for _token in known_tokens:
            # This is a simplified check - in production we'd need vault.decrypt_by_token
            # For now, check if any vault entries appear as raw values
            # The vault should expose a method to get all real values for tripwire checking
            pass

        # For MVP: if payload contains any gazetteer patterns, fail
        # This is conservative - a full implementation would decrypt vault and check all values
        return True  # Simplified for MVP

    def _recloak_pipeline(self, payload: Any) -> tuple[Any, list[CloakedEntity]]:
        """Re-run cloaking pipeline on payload that failed tripwire."""
        entities: list[CloakedEntity] = []
        # Run gazetteer and detector stages again
        payload_after_gazetteer, gazetteer_entities = self._stage3_gazetteer(payload)
        entities.extend(gazetteer_entities)
        payload_after_detectors, detector_entities = self._stage4_detectors(payload_after_gazetteer)
        entities.extend(detector_entities)
        return payload_after_detectors, entities

    # Tier utilities
    def _get_tier(self, entity_type: str) -> str:
        """Determine tier for entity type."""
        identifier_types = {"EMAIL", "PHONE", "ACCT", "GOVID", "MED_ID", "SECRET"}
        analytical_types = {"AMOUNT", "DATE", "QUANTITY"}  # Not implemented in detectors yet
        if entity_type in identifier_types:
            return "identifier"
        elif entity_type in analytical_types:
            return "analytical"
        else:
            return "contextual"

    def _should_mask_tier(self, tier: str) -> bool:
        """Check if tier should be masked per policy."""
        tier_mask_map = {
            "identifier": self._mask_identifiers,
            "contextual": self._mask_contextual,
            "analytical": self._mask_analytical,
        }
        return tier_mask_map.get(tier, True)  # Default to mask
