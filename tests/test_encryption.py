"""Tests for envelope encryption and Shamir Secret Sharing."""

from pathlib import Path

import pytest

from app.services.encryption import MAGIC, VERSION, EnvelopeEncryption
from app.services.key_recovery import KeyRecoveryManager, ShamirSecretSharing
from app.services.storage import StorageService


class TestEnvelopeEncryption:
    """Tests for the EnvelopeEncryption class."""

    def test_generate_dek(self):
        """DEK should be 32 bytes of random data."""
        dek = EnvelopeEncryption.generate_dek()
        assert len(dek) == 32
        # Two DEKs should be different (extremely unlikely to be equal)
        dek2 = EnvelopeEncryption.generate_dek()
        assert dek != dek2

    def test_encrypt_decrypt_dek_roundtrip(self):
        """Encrypting and decrypting a DEK should return the original."""
        kek = EnvelopeEncryption.generate_dek()  # 32-byte KEK
        dek = EnvelopeEncryption.generate_dek()

        nonce, tag, ciphertext = EnvelopeEncryption.encrypt_dek(dek, kek)

        assert len(nonce) == 12
        assert len(tag) == 16
        assert len(ciphertext) == 32  # same size as DEK

        recovered_dek = EnvelopeEncryption.decrypt_dek(nonce, tag, ciphertext, kek)
        assert recovered_dek == dek

    def test_encrypt_decrypt_dek_wrong_kek_fails(self):
        """Decrypting DEK with wrong KEK should fail."""
        kek = EnvelopeEncryption.generate_dek()
        wrong_kek = EnvelopeEncryption.generate_dek()
        dek = EnvelopeEncryption.generate_dek()

        nonce, tag, ciphertext = EnvelopeEncryption.encrypt_dek(dek, kek)

        with pytest.raises(Exception):
            EnvelopeEncryption.decrypt_dek(nonce, tag, ciphertext, wrong_kek)

    def test_encrypt_decrypt_file_roundtrip(self, tmp_path: Path):
        """Encrypting and decrypting a file should produce the original content."""
        kek = EnvelopeEncryption.generate_dek()
        plaintext = b"Hello, this is a test document with some content!\n" * 100

        plaintext_path = tmp_path / "test.txt"
        plaintext_path.write_bytes(plaintext)

        encrypted_path = tmp_path / "test.enc"
        decrypted_path = tmp_path / "test.dec"

        EnvelopeEncryption.encrypt_file(plaintext_path, encrypted_path, kek)

        # Encrypted file should be different from plaintext
        assert encrypted_path.read_bytes() != plaintext

        EnvelopeEncryption.decrypt_file(encrypted_path, decrypted_path, kek)
        assert decrypted_path.read_bytes() == plaintext

    def test_encrypt_file_format(self, tmp_path: Path):
        """Encrypted file should have correct header format."""
        kek = EnvelopeEncryption.generate_dek()
        plaintext = b"test content"

        plaintext_path = tmp_path / "test.txt"
        plaintext_path.write_bytes(plaintext)

        encrypted_path = tmp_path / "test.enc"
        EnvelopeEncryption.encrypt_file(plaintext_path, encrypted_path, kek)

        with open(encrypted_path, "rb") as f:
            # Check magic bytes
            magic = f.read(4)
            assert magic == MAGIC

            # Check version
            version_bytes = f.read(4)
            version = int.from_bytes(version_bytes, "big")
            assert version == VERSION

            # DEK nonce (12), tag (16), wrapped DEK (32)
            dek_nonce = f.read(12)
            assert len(dek_nonce) == 12
            dek_tag = f.read(16)
            assert len(dek_tag) == 16
            wrapped_dek = f.read(32)
            assert len(wrapped_dek) == 32

            # Data nonce (12), tag (16)
            data_nonce = f.read(12)
            assert len(data_nonce) == 12
            data_tag = f.read(16)
            assert len(data_tag) == 16

            # Rest is ciphertext
            ciphertext = f.read()
            assert len(ciphertext) == len(plaintext)

    def test_decrypt_file_wrong_kek_fails(self, tmp_path: Path):
        """Decrypting with wrong KEK should fail."""
        kek = EnvelopeEncryption.generate_dek()
        wrong_kek = EnvelopeEncryption.generate_dek()
        plaintext = b"sensitive data"

        plaintext_path = tmp_path / "test.txt"
        plaintext_path.write_bytes(plaintext)

        encrypted_path = tmp_path / "test.enc"
        decrypted_path = tmp_path / "test.dec"

        EnvelopeEncryption.encrypt_file(plaintext_path, encrypted_path, kek)

        with pytest.raises(Exception):
            EnvelopeEncryption.decrypt_file(encrypted_path, decrypted_path, wrong_kek)

    def test_decrypt_file_bad_magic_fails(self, tmp_path: Path):
        """File with bad magic bytes should fail to decrypt."""
        kek = EnvelopeEncryption.generate_dek()

        bad_file = tmp_path / "bad.enc"
        bad_file.write_bytes(b"XXXX" + b"\x00" * 100)

        decrypted_path = tmp_path / "test.dec"

        with pytest.raises(ValueError, match="bad magic bytes"):
            EnvelopeEncryption.decrypt_file(bad_file, decrypted_path, kek)

    def test_dek_zeroize(self):
        """DEK should be zeroed after zeroization."""
        dek = bytearray(b"\xff" * 32)
        EnvelopeEncryption.dek_zeroize(dek)
        assert dek == bytearray(32)  # all zeros

    def test_encrypt_empty_file(self, tmp_path: Path):
        """Empty files should encrypt/decrypt correctly."""
        kek = EnvelopeEncryption.generate_dek()
        plaintext = b""

        plaintext_path = tmp_path / "empty.txt"
        plaintext_path.write_bytes(plaintext)

        encrypted_path = tmp_path / "empty.enc"
        decrypted_path = tmp_path / "empty.dec"

        EnvelopeEncryption.encrypt_file(plaintext_path, encrypted_path, kek)
        EnvelopeEncryption.decrypt_file(encrypted_path, decrypted_path, kek)
        assert decrypted_path.read_bytes() == plaintext

    def test_encrypt_large_file(self, tmp_path: Path):
        """Large files should encrypt/decrypt correctly."""
        kek = EnvelopeEncryption.generate_dek()
        plaintext = b"A" * (1024 * 1024)  # 1MB

        plaintext_path = tmp_path / "large.bin"
        plaintext_path.write_bytes(plaintext)

        encrypted_path = tmp_path / "large.enc"
        decrypted_path = tmp_path / "large.dec"

        EnvelopeEncryption.encrypt_file(plaintext_path, encrypted_path, kek)
        EnvelopeEncryption.decrypt_file(encrypted_path, decrypted_path, kek)
        assert decrypted_path.read_bytes() == plaintext


class TestShamirSecretSharing:
    """Tests for Shamir's Secret Sharing implementation."""

    def test_split_2_of_3_reconstruct_any_2(self):
        """2-of-3 threshold: any 2 shares should reconstruct the secret."""
        secret = b"This is a 32-byte secret key!!\x00\x00"
        shares = ShamirSecretSharing.split_secret(secret, threshold=2, num_shares=3)

        assert len(shares) == 3
        # Each share should have an index and same-length bytes
        for idx, share_bytes in shares:
            assert 1 <= idx <= 3
            assert len(share_bytes) == len(secret)

        # Any 2 shares should work
        from itertools import combinations

        for combo in combinations(shares, 2):
            recovered = ShamirSecretSharing.reconstruct_secret(list(combo))
            assert recovered == secret

    def test_split_2_of_3_single_share_insufficient(self):
        """A single share should not reconstruct the correct secret."""
        secret = b"secret_key_32_bytes_long_value!!"
        shares = ShamirSecretSharing.split_secret(secret, threshold=2, num_shares=3)

        # Using only 1 share and a fake second share should give wrong result
        # (Note: with only 1 share we cannot even call reconstruct since minimum is 2,
        # but the result with 1 real + 1 fake should be wrong)
        single_share = [shares[0]]
        # This should raise since we need at least 2
        with pytest.raises(ValueError, match="at least 2"):
            ShamirSecretSharing.reconstruct_secret(single_share)

    def test_split_3_of_5_reconstruct_any_3(self):
        """3-of-5 threshold: any 3 shares should reconstruct the secret."""
        secret = b"\x01\x02\x03\x04\x05\x06\x07\x08" * 4  # 32 bytes
        shares = ShamirSecretSharing.split_secret(secret, threshold=3, num_shares=5)

        assert len(shares) == 5

        from itertools import combinations

        for combo in combinations(shares, 3):
            recovered = ShamirSecretSharing.reconstruct_secret(list(combo))
            assert recovered == secret

    def test_split_3_of_5_only_2_shares_wrong(self):
        """With 3-of-5 threshold, using only 2 shares gives wrong result."""
        secret = b"x" * 32
        shares = ShamirSecretSharing.split_secret(secret, threshold=3, num_shares=5)

        # Using only 2 shares should reconstruct something different
        partial = [shares[0], shares[1]]
        recovered = ShamirSecretSharing.reconstruct_secret(partial)
        # Very unlikely to accidentally reconstruct correctly with insufficient shares
        assert recovered != secret

    def test_split_preserves_all_byte_values(self):
        """Secrets with all possible byte values should work."""
        secret = bytes(range(256))
        shares = ShamirSecretSharing.split_secret(secret, threshold=2, num_shares=3)

        recovered = ShamirSecretSharing.reconstruct_secret([shares[0], shares[2]])
        assert recovered == secret

    def test_split_threshold_validation(self):
        """Invalid threshold/shares should raise ValueError."""
        secret = b"test"

        with pytest.raises(ValueError, match="Threshold must be at least 2"):
            ShamirSecretSharing.split_secret(secret, threshold=1, num_shares=3)

        with pytest.raises(ValueError, match="Number of shares must be >= threshold"):
            ShamirSecretSharing.split_secret(secret, threshold=3, num_shares=2)

    def test_known_vector_single_byte(self):
        """Test with a single-byte secret for predictable behavior."""
        # Secret is a single byte; split into 2-of-3
        secret = b"\x42"
        shares = ShamirSecretSharing.split_secret(secret, threshold=2, num_shares=3)

        # Any 2 shares should recover the original byte
        from itertools import combinations

        for combo in combinations(shares, 2):
            recovered = ShamirSecretSharing.reconstruct_secret(list(combo))
            assert recovered == secret

    def test_split_all_zeros(self):
        """Secret of all zeros should work correctly."""
        secret = b"\x00" * 32
        shares = ShamirSecretSharing.split_secret(secret, threshold=2, num_shares=3)
        recovered = ShamirSecretSharing.reconstruct_secret([shares[0], shares[1]])
        assert recovered == secret

    def test_reconstruct_duplicate_indices_fails(self):
        """Duplicate share indices should raise an error."""
        # Manually create shares with duplicate indices
        shares = [(1, b"\x01\x02"), (1, b"\x03\x04")]
        with pytest.raises(ValueError, match="Duplicate share indices"):
            ShamirSecretSharing.reconstruct_secret(shares)


class TestKeyRecoveryManager:
    """Tests for the KeyRecoveryManager class."""

    def test_generate_kek(self, tmp_path: Path):
        """Generated KEK should be 32 bytes."""
        manager = KeyRecoveryManager(key_store_path=tmp_path / "kek.enc")
        kek = manager.generate_kek()
        assert len(kek) == 32

    def test_split_and_recover(self, tmp_path: Path):
        """Split KEK into shares and recover it."""
        manager = KeyRecoveryManager(key_store_path=tmp_path / "kek.enc")
        kek = manager.generate_kek()

        shares = manager.split_kek(kek, threshold=2, num_shares=3)
        assert len(shares) == 3

        # Recover with first 2 shares
        recovered = manager.recover_kek(shares[:2])
        assert recovered == kek

        # Recover with last 2 shares
        recovered2 = manager.recover_kek(shares[1:])
        assert recovered2 == kek

    def test_save_and_load_encrypted(self, tmp_path: Path):
        """KEK should be saved and loaded correctly with passphrase."""
        key_path = tmp_path / "keys" / "kek.enc"
        manager = KeyRecoveryManager(key_store_path=key_path)
        kek = manager.generate_kek()

        passphrase = "my-strong-passphrase-123!"
        manager.save_kek_encrypted(kek, passphrase)

        assert key_path.exists()

        loaded_kek = manager.load_kek_encrypted(passphrase)
        assert loaded_kek == kek

    def test_load_wrong_passphrase_fails(self, tmp_path: Path):
        """Loading KEK with wrong passphrase should fail."""
        key_path = tmp_path / "kek.enc"
        manager = KeyRecoveryManager(key_store_path=key_path)
        kek = manager.generate_kek()

        manager.save_kek_encrypted(kek, "correct-passphrase")

        with pytest.raises(Exception):
            manager.load_kek_encrypted("wrong-passphrase")


class TestStorageServiceEncryption:
    """Tests for encrypted storage service operations."""

    def test_save_and_read_unencrypted(self, tmp_path: Path):
        """Without KEK, files should be stored as plaintext."""
        storage = StorageService(base_path=str(tmp_path / "storage"))
        content = b"Hello, world!"

        path = storage.save_to_data(1, "md", "test.md", content)
        assert path.exists()
        # Should be raw content (no encryption)
        assert path.read_bytes() == content

        read_content = storage.read_from_data(1, "md", "test.md")
        assert read_content == content

    def test_save_and_read_encrypted(self, tmp_path: Path):
        """With KEK, files should be encrypted at rest."""
        from app.services.encryption import EnvelopeEncryption

        kek = EnvelopeEncryption.generate_dek()
        storage = StorageService(base_path=str(tmp_path / "storage"), kek=kek)
        content = b"Sensitive document content here"

        path = storage.save_to_data(1, "raw", "doc.pdf", content)
        assert path.exists()
        # On-disk content should NOT be plaintext
        assert path.read_bytes() != content

        # Reading should decrypt
        read_content = storage.read_from_data(1, "raw", "doc.pdf")
        assert read_content == content

    def test_save_encrypted_read_with_kek_param(self, tmp_path: Path):
        """KEK passed as parameter should override instance KEK."""
        from app.services.encryption import EnvelopeEncryption

        kek = EnvelopeEncryption.generate_dek()
        storage = StorageService(base_path=str(tmp_path / "storage"))
        content = b"Test content with explicit kek"

        path = storage.save_to_data(1, "csv", "table.csv", content, kek=kek)
        assert path.exists()
        assert path.read_bytes() != content

        read_content = storage.read_from_data(1, "csv", "table.csv", kek=kek)
        assert read_content == content

    def test_vectors_not_encrypted(self, tmp_path: Path):
        """Vectors category should not be encrypted even with KEK."""
        from app.services.encryption import EnvelopeEncryption

        kek = EnvelopeEncryption.generate_dek()
        storage = StorageService(base_path=str(tmp_path / "storage"), kek=kek)
        content = b"vector data"

        path = storage.save_to_data(1, "vectors", "embedding.bin", content)
        assert path.exists()
        # Vectors should be stored as-is
        assert path.read_bytes() == content

        read_content = storage.read_from_data(1, "vectors", "embedding.bin")
        assert read_content == content

    def test_save_to_uploads_never_encrypted(self, tmp_path: Path):
        """Uploads directory should never be encrypted."""
        from app.services.encryption import EnvelopeEncryption

        kek = EnvelopeEncryption.generate_dek()
        storage = StorageService(base_path=str(tmp_path / "storage"), kek=kek)
        content = b"uploaded file content"

        path = storage.save_to_uploads(1, "upload.pdf", content)
        assert path.exists()
        assert path.read_bytes() == content

    def test_invalid_category_raises(self, tmp_path: Path):
        """Invalid category should raise ValueError."""
        storage = StorageService(base_path=str(tmp_path / "storage"))

        with pytest.raises(ValueError, match="Invalid category"):
            storage.save_to_data(1, "invalid", "test.txt", b"data")

        with pytest.raises(ValueError, match="Invalid category"):
            storage.read_from_data(1, "invalid", "test.txt")

    def test_read_nonexistent_file_raises(self, tmp_path: Path):
        """Reading a nonexistent file should raise FileNotFoundError."""
        storage = StorageService(base_path=str(tmp_path / "storage"))

        with pytest.raises(FileNotFoundError):
            storage.read_from_data(1, "md", "nonexistent.md")

    def test_backward_compat_old_methods(self, tmp_path: Path):
        """Old methods (save_upload, encrypt_pdf, etc.) should still work."""
        storage = StorageService(base_path=str(tmp_path / "storage"))

        # _ensure_dirs still creates old layout
        dirs = storage._ensure_dirs(1)
        assert dirs["originals"].exists()
        assert dirs["encrypted"].exists()
        assert dirs["markdown"].exists()
        assert dirs["images"].exists()

    def test_all_data_categories(self, tmp_path: Path):
        """All valid categories should work."""
        from app.services.encryption import EnvelopeEncryption

        kek = EnvelopeEncryption.generate_dek()
        storage = StorageService(base_path=str(tmp_path / "storage"), kek=kek)

        for category in ("raw", "md", "csv", "images"):
            content = f"content for {category}".encode()
            storage.save_to_data(1, category, f"test.{category}", content)
            read = storage.read_from_data(1, category, f"test.{category}")
            assert read == content
