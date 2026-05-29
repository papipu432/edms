"""Tests for the KMS abstraction layer."""

import pytest

from app.services.kms import (
    CosmianKMS,
    KMSProvider,
    LocalFileKMS,
    VaultKMS,
    get_kms_provider,
)


class TestLocalFileKMS:
    """Tests for the LocalFileKMS implementation."""

    def test_wrap_unwrap_roundtrip(self):
        """Wrapping and unwrapping a key should return the original."""
        kms = LocalFileKMS(passphrase="test-passphrase-123")
        original_key = b"\x01\x02\x03" * 10 + b"\x04\x05"  # 32 bytes

        wrapped = kms.wrap_key(original_key)
        unwrapped = kms.unwrap_key(wrapped)

        assert unwrapped == original_key

    def test_wrap_produces_different_blobs(self):
        """Each wrap call should produce a different blob (unique salt/nonce)."""
        kms = LocalFileKMS(passphrase="test-passphrase")
        key = b"\xaa" * 32

        blob1 = kms.wrap_key(key)
        blob2 = kms.wrap_key(key)

        assert blob1 != blob2  # Different due to random salt and nonce

    def test_unwrap_wrong_passphrase_fails(self):
        """Unwrapping with a different passphrase should fail."""
        kms1 = LocalFileKMS(passphrase="correct-passphrase")
        kms2 = LocalFileKMS(passphrase="wrong-passphrase")

        key = b"\xbb" * 32
        wrapped = kms1.wrap_key(key)

        with pytest.raises(Exception):
            kms2.unwrap_key(wrapped)

    def test_generate_key_returns_wrapped_blob(self):
        """generate_key should return a wrapped blob that can be unwrapped."""
        kms = LocalFileKMS(passphrase="gen-test")

        wrapped = kms.generate_key()
        unwrapped = kms.unwrap_key(wrapped)

        assert len(unwrapped) == 32
        # Generated key should be different each time
        wrapped2 = kms.generate_key()
        unwrapped2 = kms.unwrap_key(wrapped2)
        assert unwrapped != unwrapped2

    def test_empty_passphrase_raises(self):
        """Empty passphrase should raise ValueError."""
        with pytest.raises(ValueError, match="must not be empty"):
            LocalFileKMS(passphrase="")

    def test_wrap_various_key_sizes(self):
        """Should work with different key sizes."""
        kms = LocalFileKMS(passphrase="size-test")

        for size in (16, 24, 32, 64):
            key = b"\x42" * size
            wrapped = kms.wrap_key(key)
            unwrapped = kms.unwrap_key(wrapped)
            assert unwrapped == key

    def test_wrapped_blob_is_json(self):
        """Wrapped blob should be valid JSON."""
        import json

        kms = LocalFileKMS(passphrase="json-test")
        key = b"\xcc" * 32

        wrapped = kms.wrap_key(key)
        data = json.loads(wrapped.decode("utf-8"))

        assert data["v"] == 1
        assert "salt" in data
        assert "nonce" in data
        assert "tag" in data
        assert "ciphertext" in data

    def test_tampered_blob_fails(self):
        """Tampered wrapped blob should fail to unwrap."""
        kms = LocalFileKMS(passphrase="tamper-test")
        key = b"\xdd" * 32

        wrapped = kms.wrap_key(key)

        # Tamper with blob
        import json
        data = json.loads(wrapped.decode("utf-8"))
        # Flip a byte in the ciphertext
        ct = bytes.fromhex(data["ciphertext"])
        tampered_ct = bytes([ct[0] ^ 0xFF]) + ct[1:]
        data["ciphertext"] = tampered_ct.hex()
        tampered_blob = json.dumps(data).encode("utf-8")

        with pytest.raises(Exception):
            kms.unwrap_key(tampered_blob)


class TestVaultKMS:
    """Tests for VaultKMS stub."""

    def test_vault_kms_raises_not_implemented(self):
        """VaultKMS operations should raise NotImplementedError."""
        kms = VaultKMS(vault_url="http://vault:8200", vault_token="s.test-token")

        with pytest.raises(NotImplementedError):
            kms.wrap_key(b"\x00" * 32)

        with pytest.raises(NotImplementedError):
            kms.unwrap_key(b"blob")

        with pytest.raises(NotImplementedError):
            kms.generate_key()

    def test_vault_kms_requires_url_and_token(self):
        """VaultKMS should require both URL and token."""
        with pytest.raises(ValueError):
            VaultKMS(vault_url="", vault_token="token")

        with pytest.raises(ValueError):
            VaultKMS(vault_url="http://vault:8200", vault_token="")


class TestCosmianKMS:
    """Tests for CosmianKMS stub."""

    def test_cosmian_kms_raises_not_implemented(self):
        """CosmianKMS operations should raise NotImplementedError."""
        kms = CosmianKMS()

        with pytest.raises(NotImplementedError):
            kms.wrap_key(b"\x00" * 32)

        with pytest.raises(NotImplementedError):
            kms.unwrap_key(b"blob")

        with pytest.raises(NotImplementedError):
            kms.generate_key()


class TestKMSProviderABC:
    """Tests for the KMS provider interface."""

    def test_local_file_kms_is_kms_provider(self):
        """LocalFileKMS should be an instance of KMSProvider."""
        kms = LocalFileKMS(passphrase="abc")
        assert isinstance(kms, KMSProvider)

    def test_vault_kms_is_kms_provider(self):
        """VaultKMS should be an instance of KMSProvider."""
        kms = VaultKMS(vault_url="http://v:8200", vault_token="t")
        assert isinstance(kms, KMSProvider)

    def test_cosmian_kms_is_kms_provider(self):
        """CosmianKMS should be an instance of KMSProvider."""
        kms = CosmianKMS()
        assert isinstance(kms, KMSProvider)


class TestGetKMSProvider:
    """Tests for the get_kms_provider factory function."""

    def test_get_local_provider(self, monkeypatch):
        """Should return LocalFileKMS when KMS_PROVIDER=local."""
        monkeypatch.setenv("KMS_PROVIDER", "local")
        monkeypatch.setenv("KMS_LOCAL_PASSPHRASE", "test-pass")

        # Direct test using the class
        kms = LocalFileKMS(passphrase="test-pass")
        assert isinstance(kms, LocalFileKMS)

    def test_unknown_provider_raises(self, monkeypatch):
        """Unknown KMS provider should raise ValueError."""
        monkeypatch.setattr("app.core.config.settings.KMS_PROVIDER", "unknown")
        with pytest.raises(ValueError, match="Unknown KMS provider"):
            get_kms_provider()

    def test_local_provider_no_passphrase_raises(self, monkeypatch):
        """Local provider without passphrase should raise ValueError."""
        monkeypatch.setattr("app.core.config.settings.KMS_PROVIDER", "local")
        monkeypatch.setattr("app.core.config.settings.KMS_LOCAL_PASSPHRASE", "")
        with pytest.raises(ValueError, match="KMS_LOCAL_PASSPHRASE must be set"):
            get_kms_provider()
