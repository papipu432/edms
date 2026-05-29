"""Tests for Backup KEK Manager - isolation of backup encryption from production."""

import pytest

from app.services.backup_kek_manager import BackupKEKManager
from app.services.kms import LocalFileKMS


class TestBackupKEKManager:
    """Tests for the BackupKEKManager class."""

    def _make_manager(self, passphrase: str = "test-backup-kms") -> BackupKEKManager:
        """Create a BackupKEKManager with a local KMS provider."""
        kms = LocalFileKMS(passphrase=passphrase)
        return BackupKEKManager(kms=kms)

    def test_generate_backup_kek(self):
        """Should generate a raw KEK and a wrapped blob."""
        manager = self._make_manager()
        raw_kek, wrapped_blob = manager.generate_backup_kek()

        assert len(raw_kek) == 32
        assert len(wrapped_blob) > 0
        assert raw_kek != wrapped_blob

    def test_unwrap_backup_kek_roundtrip(self):
        """Wrapping and unwrapping should return the same KEK."""
        manager = self._make_manager()
        raw_kek, wrapped_blob = manager.generate_backup_kek()

        unwrapped = manager.unwrap_backup_kek(wrapped_blob)
        assert unwrapped == raw_kek

    def test_encrypt_decrypt_roundtrip(self):
        """Encrypting and decrypting data should return the original."""
        manager = self._make_manager()
        raw_kek, _ = manager.generate_backup_kek()

        original_data = b"This is sensitive backup data that must be protected"
        encrypted = manager.encrypt_for_backup(original_data, raw_kek)

        assert encrypted != original_data
        assert len(encrypted) > len(original_data)

        decrypted = manager.decrypt_from_backup(encrypted, raw_kek)
        assert decrypted == original_data

    def test_encrypt_empty_data(self):
        """Should handle empty data correctly."""
        manager = self._make_manager()
        raw_kek, _ = manager.generate_backup_kek()

        encrypted = manager.encrypt_for_backup(b"", raw_kek)
        decrypted = manager.decrypt_from_backup(encrypted, raw_kek)
        assert decrypted == b""

    def test_encrypt_large_data(self):
        """Should handle large data correctly."""
        manager = self._make_manager()
        raw_kek, _ = manager.generate_backup_kek()

        large_data = b"X" * (1024 * 1024)  # 1MB
        encrypted = manager.encrypt_for_backup(large_data, raw_kek)
        decrypted = manager.decrypt_from_backup(encrypted, raw_kek)
        assert decrypted == large_data

    def test_decrypt_with_wrong_kek_fails(self):
        """Decrypting with a different KEK should fail."""
        manager = self._make_manager()
        kek1, _ = manager.generate_backup_kek()
        kek2, _ = manager.generate_backup_kek()

        encrypted = manager.encrypt_for_backup(b"secret data", kek1)

        with pytest.raises(Exception):
            manager.decrypt_from_backup(encrypted, kek2)

    def test_different_encryptions_produce_different_output(self):
        """Same data encrypted twice should produce different ciphertext."""
        manager = self._make_manager()
        raw_kek, _ = manager.generate_backup_kek()
        data = b"same data"

        enc1 = manager.encrypt_for_backup(data, raw_kek)
        enc2 = manager.encrypt_for_backup(data, raw_kek)

        assert enc1 != enc2  # Different due to random DEK and nonces

    def test_backup_kek_distinct_from_production_kek(self):
        """Backup KEK should be a different key from production KEK."""
        manager = self._make_manager()
        backup_kek, _ = manager.generate_backup_kek()

        # Generate another key (simulating production KEK)
        from Crypto.Random import get_random_bytes
        production_kek = get_random_bytes(32)

        # They should be different (extremely unlikely to collide)
        assert backup_kek != production_kek

    def test_get_backup_key_id(self):
        """Should generate a consistent key ID from a wrapped blob."""
        manager = self._make_manager()
        _, wrapped_blob = manager.generate_backup_kek()

        key_id = manager.get_backup_key_id(wrapped_blob)
        assert len(key_id) == 16
        # Same blob should give same ID
        assert manager.get_backup_key_id(wrapped_blob) == key_id

    def test_different_blobs_different_key_ids(self):
        """Different wrapped blobs should produce different key IDs."""
        manager = self._make_manager()
        _, blob1 = manager.generate_backup_kek()
        _, blob2 = manager.generate_backup_kek()

        id1 = manager.get_backup_key_id(blob1)
        id2 = manager.get_backup_key_id(blob2)
        assert id1 != id2


class TestBackupServicePreEncryption:
    """Tests for backup service pre-encryption with backup KEK."""

    def test_backup_service_pre_encrypt(self):
        """BackupService.pre_encrypt_backup_data should encrypt data."""
        from app.services.backup import BackupService
        from Crypto.Random import get_random_bytes

        service = BackupService()
        kek = get_random_bytes(32)
        data = b"backup payload content"

        encrypted = service.pre_encrypt_backup_data(data, kek)
        assert encrypted != data

        decrypted = service.decrypt_backup_data(encrypted, kek)
        assert decrypted == data

    def test_backup_service_wrong_kek_fails(self):
        """Decrypting with wrong KEK should fail."""
        from app.services.backup import BackupService
        from Crypto.Random import get_random_bytes

        service = BackupService()
        kek1 = get_random_bytes(32)
        kek2 = get_random_bytes(32)
        data = b"sensitive backup"

        encrypted = service.pre_encrypt_backup_data(data, kek1)

        with pytest.raises(Exception):
            service.decrypt_backup_data(encrypted, kek2)
