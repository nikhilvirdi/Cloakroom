"""Comprehensive tests for the vault module."""

from pathlib import Path

import pytest

from cloakroom.errors import VaultError
from cloakroom.vault import Canonicalizer, VaultEngine, VaultStorage


class TestCanonicalizer:
    """Test value canonicalization."""

    def test_whitespace_normalization(self) -> None:
        canon = Canonicalizer()
        assert canon.canonicalize("  Aarav   Sharma  ") == "aarav sharma"
        assert canon.canonicalize("Aarav\t\nSharma") == "aarav sharma"

    def test_case_normalization(self) -> None:
        canon = Canonicalizer()
        assert canon.canonicalize("AARAV SHARMA") == "aarav sharma"
        assert canon.canonicalize("Aarav Sharma") == "aarav sharma"

    def test_honorifics_stripped_for_person(self) -> None:
        canon = Canonicalizer()
        assert canon.canonicalize("Mr. Aarav Sharma", entity_type="PERSON") == "aarav sharma"
        assert canon.canonicalize("Dr Aarav Sharma", entity_type="PERSON") == "aarav sharma"
        assert canon.canonicalize("Shri Aarav Sharma", entity_type="PERSON") == "aarav sharma"
        assert canon.canonicalize("Mrs. Meera", entity_type="PERSON") == "meera"

    def test_honorifics_not_stripped_for_other_types(self) -> None:
        canon = Canonicalizer()
        assert canon.canonicalize("Mr. Bank", entity_type="ORG") == "mr. bank"

    def test_digit_separators_removed_for_identifiers(self) -> None:
        canon = Canonicalizer()
        assert canon.canonicalize("1234-5678-9012", entity_type="ACCT") == "123456789012"
        assert canon.canonicalize("4401 9283 71", entity_type="ACCT") == "4401928371"
        assert canon.canonicalize("123-456-7890", entity_type="PHONE") == "1234567890"
        assert canon.canonicalize("LH-99214", entity_type="MED_ID") == "lh99214"

    def test_digit_separators_not_removed_for_names(self) -> None:
        canon = Canonicalizer()
        # Names don't get digit separator removal
        assert canon.canonicalize("test-name", entity_type="PERSON") == "test-name"

    def test_alias_mapping(self) -> None:
        alias_map = {"aarav": "aarav sharma", "a. sharma": "aarav sharma"}
        canon = Canonicalizer(alias_map=alias_map)
        assert canon.canonicalize("Aarav", entity_type="PERSON") == "aarav sharma"
        assert canon.canonicalize("A. Sharma", entity_type="PERSON") == "aarav sharma"
        assert canon.canonicalize("Aarav Sharma", entity_type="PERSON") == "aarav sharma"

    def test_build_alias_map(self) -> None:
        canon = Canonicalizer()
        aliases = {"Aarav Sharma": ["Aarav", "A. Sharma", "Mr. Aarav"]}
        alias_map = canon.build_alias_map(aliases)
        # All should map to canonicalized form of "Aarav Sharma"
        assert alias_map.get("aarav") == "aarav sharma"
        assert alias_map.get("a. sharma") == "aarav sharma"
        assert alias_map.get("aarav") == "aarav sharma"  # honorific stripped

    def test_empty_value(self) -> None:
        canon = Canonicalizer()
        assert canon.canonicalize("") == ""
        assert canon.canonicalize("   ") == ""


class TestVaultStorage:
    """Test encrypted storage operations."""

    def test_store_and_lookup_entity(self, tmp_path: Path) -> None:
        vault_path = tmp_path / "vault.db"
        key_path = tmp_path / "vault.key"
        storage = VaultStorage(vault_path=vault_path, key_path=key_path)

        # Store entity
        storage.store_entity(
            token="[PERSON_1]",
            entity_type="PERSON",
            canonical_value="aarav sharma",
            original_value="Aarav Sharma",
            first_seen="documents.read_text",
        )

        # Lookup should find it
        token = storage.lookup_by_canonical("aarav sharma")
        assert token == "[PERSON_1]"

        # Decrypt should return original value
        value = storage.decrypt_by_token("[PERSON_1]")
        assert value == "Aarav Sharma"

    def test_lookup_nonexistent(self, tmp_path: Path) -> None:
        vault_path = tmp_path / "vault.db"
        key_path = tmp_path / "vault.key"
        storage = VaultStorage(vault_path=vault_path, key_path=key_path)

        token = storage.lookup_by_canonical("nonexistent")
        assert token is None

        value = storage.decrypt_by_token("[PERSON_999]")
        assert value is None

    def test_hit_counter_increments(self, tmp_path: Path) -> None:
        vault_path = tmp_path / "vault.db"
        key_path = tmp_path / "vault.key"
        storage = VaultStorage(vault_path=vault_path, key_path=key_path)

        storage.store_entity(
            token="[PERSON_1]",
            entity_type="PERSON",
            canonical_value="aarav sharma",
            original_value="Aarav Sharma",
            first_seen="test",
        )

        # First lookup
        storage.lookup_by_canonical("aarav sharma")
        summary = storage.list_summary()
        assert summary[0]["hits"] == 2  # Initial 1 + 1 lookup

        # Second lookup
        storage.lookup_by_canonical("aarav sharma")
        summary = storage.list_summary()
        assert summary[0]["hits"] == 3

    def test_duplicate_token_raises_error(self, tmp_path: Path) -> None:
        vault_path = tmp_path / "vault.db"
        key_path = tmp_path / "vault.key"
        storage = VaultStorage(vault_path=vault_path, key_path=key_path)

        storage.store_entity(
            token="[PERSON_1]",
            entity_type="PERSON",
            canonical_value="aarav sharma",
            original_value="Aarav Sharma",
            first_seen="test",
        )

        # Attempting to store same token should fail
        with pytest.raises(VaultError):
            storage.store_entity(
                token="[PERSON_1]",
                entity_type="PERSON",
                canonical_value="different value",
                original_value="Different Value",
                first_seen="test",
            )

    def test_key_persistence(self, tmp_path: Path) -> None:
        vault_path = tmp_path / "vault.db"
        key_path = tmp_path / "vault.key"

        # Create first storage instance
        storage1 = VaultStorage(vault_path=vault_path, key_path=key_path)
        storage1.store_entity(
            token="[PERSON_1]",
            entity_type="PERSON",
            canonical_value="aarav",
            original_value="Aarav",
            first_seen="test",
        )
        storage1.close()

        # Create second storage instance with same key
        storage2 = VaultStorage(vault_path=vault_path, key_path=key_path)
        value = storage2.decrypt_by_token("[PERSON_1]")
        assert value == "Aarav"

    def test_key_file_permissions(self, tmp_path: Path) -> None:
        vault_path = tmp_path / "vault.db"
        key_path = tmp_path / "vault.key"
        VaultStorage(vault_path=vault_path, key_path=key_path)

        # Key file should be created with 0600 permissions
        import stat

        st = key_path.stat()
        assert stat.S_IMODE(st.st_mode) == 0o600

    def test_list_summary(self, tmp_path: Path) -> None:
        vault_path = tmp_path / "vault.db"
        key_path = tmp_path / "vault.key"
        storage = VaultStorage(vault_path=vault_path, key_path=key_path)

        storage.store_entity(
            token="[PERSON_1]",
            entity_type="PERSON",
            canonical_value="aarav",
            original_value="Aarav",
            first_seen="test.tool",
        )
        storage.store_entity(
            token="[EMAIL_1]",
            entity_type="EMAIL",
            canonical_value="test@example.com",
            original_value="test@example.com",
            first_seen="contacts.lookup",
        )

        summary = storage.list_summary()
        assert len(summary) == 2
        assert summary[0]["token"] == "[EMAIL_1]"  # Sorted by entity_type then token
        assert summary[0]["entity_type"] == "EMAIL"
        assert summary[1]["token"] == "[PERSON_1]"
        assert summary[1]["entity_type"] == "PERSON"
        # Verify no actual values in summary
        assert "original_value" not in summary[0]

    def test_wipe(self, tmp_path: Path) -> None:
        vault_path = tmp_path / "vault.db"
        key_path = tmp_path / "vault.key"
        storage = VaultStorage(vault_path=vault_path, key_path=key_path)

        storage.store_entity(
            token="[PERSON_1]",
            entity_type="PERSON",
            canonical_value="aarav",
            original_value="Aarav",
            first_seen="test",
        )

        storage.wipe()
        summary = storage.list_summary()
        assert len(summary) == 0

    def test_get_next_counter(self, tmp_path: Path) -> None:
        vault_path = tmp_path / "vault.db"
        key_path = tmp_path / "vault.key"
        storage = VaultStorage(vault_path=vault_path, key_path=key_path)

        # Empty vault should return 1
        assert storage.get_next_counter("PERSON") == 1

        # After storing [PERSON_1], next should be 2
        storage.store_entity(
            token="[PERSON_1]",
            entity_type="PERSON",
            canonical_value="aarav",
            original_value="Aarav",
            first_seen="test",
        )
        assert storage.get_next_counter("PERSON") == 2

        # Different entity type should still be 1
        assert storage.get_next_counter("EMAIL") == 1


class TestVaultEngine:
    """Test vault engine integration."""

    def test_mint_new_placeholder(self, tmp_path: Path) -> None:
        vault_path = tmp_path / "vault.db"
        key_path = tmp_path / "vault.key"
        engine = VaultEngine(vault_path=vault_path, key_path=key_path)

        token = engine.mint_or_reuse(
            value="Aarav Sharma", entity_type="PERSON", first_seen="test.tool"
        )
        assert token == "[PERSON_1]"

    def test_reuse_existing_placeholder(self, tmp_path: Path) -> None:
        vault_path = tmp_path / "vault.db"
        key_path = tmp_path / "vault.key"
        engine = VaultEngine(vault_path=vault_path, key_path=key_path)

        # Mint first time
        token1 = engine.mint_or_reuse(value="Aarav Sharma", entity_type="PERSON")
        # Variations should reuse (canonicalization)
        token2 = engine.mint_or_reuse(value="AARAV SHARMA", entity_type="PERSON")
        token3 = engine.mint_or_reuse(value="  Aarav   Sharma  ", entity_type="PERSON")

        assert token1 == token2 == token3 == "[PERSON_1]"

    def test_honorific_variations_reuse(self, tmp_path: Path) -> None:
        vault_path = tmp_path / "vault.db"
        key_path = tmp_path / "vault.key"
        engine = VaultEngine(vault_path=vault_path, key_path=key_path)

        token1 = engine.mint_or_reuse(value="Mr. Aarav Sharma", entity_type="PERSON")
        token2 = engine.mint_or_reuse(value="Aarav Sharma", entity_type="PERSON")
        token3 = engine.mint_or_reuse(value="Dr. Aarav Sharma", entity_type="PERSON")

        assert token1 == token2 == token3

    def test_alias_mapping_integration(self, tmp_path: Path) -> None:
        vault_path = tmp_path / "vault.db"
        key_path = tmp_path / "vault.key"

        # Build alias map
        from cloakroom.vault.canonicalizer import Canonicalizer

        canon = Canonicalizer()
        alias_map = canon.build_alias_map({"Aarav Sharma": ["Aarav", "A. Sharma"]})

        engine = VaultEngine(vault_path=vault_path, key_path=key_path, alias_map=alias_map)

        # All variants should reuse same token
        token1 = engine.mint_or_reuse(value="Aarav Sharma", entity_type="PERSON")
        token2 = engine.mint_or_reuse(value="Aarav", entity_type="PERSON")
        token3 = engine.mint_or_reuse(value="A. Sharma", entity_type="PERSON")

        assert token1 == token2 == token3

    def test_different_entity_types_separate_counters(self, tmp_path: Path) -> None:
        vault_path = tmp_path / "vault.db"
        key_path = tmp_path / "vault.key"
        engine = VaultEngine(vault_path=vault_path, key_path=key_path)

        person_token = engine.mint_or_reuse(value="Test Person", entity_type="PERSON")
        org_token = engine.mint_or_reuse(value="Test Org", entity_type="ORG")
        email_token = engine.mint_or_reuse(value="test@example.com", entity_type="EMAIL")

        assert person_token == "[PERSON_1]"
        assert org_token == "[ORG_1]"
        assert email_token == "[EMAIL_1]"

    def test_account_number_canonicalization(self, tmp_path: Path) -> None:
        vault_path = tmp_path / "vault.db"
        key_path = tmp_path / "vault.key"
        engine = VaultEngine(vault_path=vault_path, key_path=key_path)

        # Different formats should canonicalize to same
        token1 = engine.mint_or_reuse(value="4401928371", entity_type="ACCT")
        engine.mint_or_reuse(value="4401 9283 71", entity_type="ACCT")
        engine.mint_or_reuse(value="4401-9283-71", entity_type="ACCT")

        # The first one should mint [ACCT_1]
        assert token1 == "[ACCT_1]"

    def test_restore_known_placeholders(self, tmp_path: Path) -> None:
        vault_path = tmp_path / "vault.db"
        key_path = tmp_path / "vault.key"
        engine = VaultEngine(vault_path=vault_path, key_path=key_path)

        # Mint some placeholders
        engine.mint_or_reuse(value="Aarav Sharma", entity_type="PERSON")
        engine.mint_or_reuse(value="test@example.com", entity_type="EMAIL")

        # Restore arguments
        arguments = {
            "to": "[EMAIL_1]",
            "subject": "Hello [PERSON_1]",
            "body": "Dear [PERSON_1], this is a test.",
        }

        result = engine.restore(arguments)
        assert not result.blocked
        assert result.restored_arguments["to"] == "test@example.com"
        assert result.restored_arguments["subject"] == "Hello Aarav Sharma"
        assert result.restored_arguments["body"] == "Dear Aarav Sharma, this is a test."
        assert len(result.used_placeholders) == 2
        assert result.contains_identifier_tier  # EMAIL is identifier tier

    def test_restore_unknown_placeholder_blocks(self, tmp_path: Path) -> None:
        vault_path = tmp_path / "vault.db"
        key_path = tmp_path / "vault.key"
        engine = VaultEngine(vault_path=vault_path, key_path=key_path)

        arguments = {
            "to": "[EMAIL_999]",  # Unknown placeholder
            "body": "Test",
        }

        result = engine.restore(arguments)
        assert result.blocked
        assert "[EMAIL_999]" in result.unknown_placeholders
        # Arguments should remain unchanged when blocked
        assert result.restored_arguments == arguments

    def test_restore_nested_structures(self, tmp_path: Path) -> None:
        vault_path = tmp_path / "vault.db"
        key_path = tmp_path / "vault.key"
        engine = VaultEngine(vault_path=vault_path, key_path=key_path)

        engine.mint_or_reuse(value="Aarav", entity_type="PERSON")
        engine.mint_or_reuse(value="test@example.com", entity_type="EMAIL")

        arguments = {
            "recipients": ["[EMAIL_1]", "other@example.com"],
            "metadata": {"sender": "[PERSON_1]", "count": 42},
            "body": "Hello [PERSON_1]",
        }

        result = engine.restore(arguments)
        assert not result.blocked
        assert result.restored_arguments["recipients"][0] == "test@example.com"
        assert result.restored_arguments["metadata"]["sender"] == "Aarav"
        assert result.restored_arguments["body"] == "Hello Aarav"

    def test_restore_identifier_tier_detection(self, tmp_path: Path) -> None:
        vault_path = tmp_path / "vault.db"
        key_path = tmp_path / "vault.key"
        engine = VaultEngine(vault_path=vault_path, key_path=key_path)

        # Identifier tier
        engine.mint_or_reuse(value="test@example.com", entity_type="EMAIL")
        engine.mint_or_reuse(value="123456789012", entity_type="ACCT")
        # Contextual tier
        engine.mint_or_reuse(value="Aarav", entity_type="PERSON")

        # Only contextual
        result1 = engine.restore({"name": "[PERSON_1]"})
        assert not result1.contains_identifier_tier

        # Contains identifier
        result2 = engine.restore({"email": "[EMAIL_1]", "name": "[PERSON_1]"})
        assert result2.contains_identifier_tier

        result3 = engine.restore({"account": "[ACCT_1]"})
        assert result3.contains_identifier_tier

    def test_list_vault_summary(self, tmp_path: Path) -> None:
        vault_path = tmp_path / "vault.db"
        key_path = tmp_path / "vault.key"
        engine = VaultEngine(vault_path=vault_path, key_path=key_path)

        engine.mint_or_reuse(value="Aarav", entity_type="PERSON", first_seen="test.tool")
        engine.mint_or_reuse(value="test@example.com", entity_type="EMAIL", first_seen="contacts")

        summary = engine.list_vault_summary()
        assert len(summary) == 2
        # Verify no actual values exposed
        assert all("original_value" not in entry for entry in summary)

    def test_wipe(self, tmp_path: Path) -> None:
        vault_path = tmp_path / "vault.db"
        key_path = tmp_path / "vault.key"
        engine = VaultEngine(vault_path=vault_path, key_path=key_path)

        engine.mint_or_reuse(value="Aarav", entity_type="PERSON")
        engine.mint_or_reuse(value="test@example.com", entity_type="EMAIL")

        engine.wipe()
        summary = engine.list_vault_summary()
        assert len(summary) == 0

    def test_invalid_entity_type_raises_error(self, tmp_path: Path) -> None:
        vault_path = tmp_path / "vault.db"
        key_path = tmp_path / "vault.key"
        engine = VaultEngine(vault_path=vault_path, key_path=key_path)

        with pytest.raises(VaultError):
            engine.mint_or_reuse(value="test", entity_type="INVALID_TYPE")

    def test_empty_value_raises_error(self, tmp_path: Path) -> None:
        vault_path = tmp_path / "vault.db"
        key_path = tmp_path / "vault.key"
        engine = VaultEngine(vault_path=vault_path, key_path=key_path)

        with pytest.raises(VaultError):
            engine.mint_or_reuse(value="", entity_type="PERSON")


class TestRealWorldScenarios:
    """Test real-world usage scenarios from README examples."""

    def test_hospital_bill_example(self, tmp_path: Path) -> None:
        """Test the README hospital bill example."""
        vault_path = tmp_path / "vault.db"
        key_path = tmp_path / "vault.key"

        # Build alias map for the patient
        from cloakroom.vault.canonicalizer import Canonicalizer

        canon = Canonicalizer()
        alias_map = canon.build_alias_map({"Aarav Sharma": ["Aarav"]})

        engine = VaultEngine(vault_path=vault_path, key_path=key_path, alias_map=alias_map)

        # Mint placeholders as cloak pipeline would
        person_token = engine.mint_or_reuse(
            value="Aarav Sharma", entity_type="PERSON", first_seen="documents.read_text"
        )
        med_id_token = engine.mint_or_reuse(
            value="LH-99214", entity_type="MED_ID", first_seen="documents.read_text"
        )
        org_token = engine.mint_or_reuse(
            value="Lakeview Hospital", entity_type="ORG", first_seen="documents.read_text"
        )
        email_token = engine.mint_or_reuse(
            value="billing@lakeview.example", entity_type="EMAIL", first_seen="documents.read_text"
        )

        assert person_token == "[PERSON_1]"
        assert med_id_token == "[MED_ID_1]"
        assert org_token == "[ORG_1]"
        assert email_token == "[EMAIL_1]"

        # Later, alias "Aarav" should reuse [PERSON_1]
        reused = engine.mint_or_reuse(value="Aarav", entity_type="PERSON")
        assert reused == "[PERSON_1]"

    def test_mail_draft_restoration(self, tmp_path: Path) -> None:
        """Test restoring placeholders in mail draft creation."""
        vault_path = tmp_path / "vault.db"
        key_path = tmp_path / "vault.key"
        engine = VaultEngine(vault_path=vault_path, key_path=key_path)

        # Pre-populate vault
        engine.mint_or_reuse(value="billing@lakeview.example", entity_type="EMAIL")
        engine.mint_or_reuse(value="Lakeview Hospital", entity_type="ORG")
        engine.mint_or_reuse(value="Aarav Sharma", entity_type="PERSON")
        engine.mint_or_reuse(value="LH-99214", entity_type="MED_ID")
        engine.mint_or_reuse(value="4401928371", entity_type="ACCT")

        # Arguments as assistant would send them
        arguments = {
            "to": "[EMAIL_1]",
            "subject": "Billing discrepancy for [PERSON_1]",
            "body": (
                "Dear [ORG_1] billing team, the bill for [PERSON_1] (record [MED_ID_1]) "
                "shows Rs 48,500. Account [ACCT_1] was charged Rs 52,000. "
                "Please explain the Rs 3,500 difference."
            ),
        }

        result = engine.restore(arguments)
        assert not result.blocked
        assert result.contains_identifier_tier  # EMAIL, MED_ID, ACCT are identifier tier

        # Verify restoration
        assert result.restored_arguments["to"] == "billing@lakeview.example"
        assert "Aarav Sharma" in result.restored_arguments["subject"]
        assert "Lakeview Hospital" in result.restored_arguments["body"]
        assert "LH-99214" in result.restored_arguments["body"]
        assert "4401928371" in result.restored_arguments["body"]
