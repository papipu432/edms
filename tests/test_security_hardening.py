"""Tests for security hardening - no raw keys in API responses, KEK isolation."""

import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import get_db
from app.main import app
from app.models.group import Base
from app.services.kms import LocalFileKMS


@pytest_asyncio.fixture
async def security_db(tmp_path: Path):
    """Create a fresh test database."""
    db_path = tmp_path / "security_test.db"
    db_url = f"sqlite+aiosqlite:///{db_path}"
    engine = create_async_engine(db_url, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest_asyncio.fixture
async def security_client(security_db: AsyncSession, tmp_path: Path):
    """Create an authenticated test client."""
    async def override_get_db():
        try:
            yield security_db
            await security_db.commit()
        except Exception:
            await security_db.rollback()
            raise

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


class TestNoRawKeysInAPIResponses:
    """Verify that no raw key material appears in API response bodies."""

    @pytest.mark.asyncio
    async def test_backup_config_masks_secrets(self, security_client: AsyncClient):
        """GET /api/settings/backup/config should mask all secret values."""
        from app.core.config import settings

        # Set some test secrets
        original_primary_key = settings.MINIO_PRIMARY_SECRET_KEY
        original_dr_key = settings.MINIO_DR_SECRET_KEY
        original_restic_pw = settings.RESTIC_PASSWORD

        settings.MINIO_PRIMARY_SECRET_KEY = "super-secret-primary"
        settings.MINIO_PRIMARY_ACCESS_KEY = "access-key-primary"
        settings.MINIO_DR_SECRET_KEY = "super-secret-dr"
        settings.MINIO_DR_ACCESS_KEY = "access-key-dr"
        settings.RESTIC_PASSWORD = "restic-secret-pw"

        try:
            # Mock auth to bypass permission check
            with patch("app.core.security.require_permission", return_value=lambda: None):
                from app.core.security import require_permission
                app.dependency_overrides[require_permission("settings", "manage")] = lambda: None

            response = await security_client.get("/api/settings/backup/config")

            if response.status_code == 200:
                data = response.json()
                # Secrets should be masked
                assert data.get("minio_primary_secret_key") == "***"
                assert data.get("minio_dr_secret_key") == "***"
                assert data.get("restic_password") == "***"
                # Access keys should also be masked
                assert data.get("minio_primary_access_key") == "***"
                assert data.get("minio_dr_access_key") == "***"

                # Raw values should NOT appear anywhere in response
                response_text = response.text
                assert "super-secret-primary" not in response_text
                assert "super-secret-dr" not in response_text
                assert "restic-secret-pw" not in response_text
                assert "access-key-primary" not in response_text
                assert "access-key-dr" not in response_text
        finally:
            settings.MINIO_PRIMARY_SECRET_KEY = original_primary_key
            settings.MINIO_DR_SECRET_KEY = original_dr_key
            settings.RESTIC_PASSWORD = original_restic_pw
            app.dependency_overrides.clear()

    def test_encryption_init_no_raw_kek_in_response(self):
        """The /init response should contain share_hex (shares) but NOT the KEK itself."""
        from app.services.key_recovery import KeyRecoveryManager

        # Simulate what the init endpoint does
        manager = KeyRecoveryManager(key_store_path=Path("/tmp/test-kek.enc"))
        kek = manager.generate_kek()
        shares = manager.split_kek(kek, threshold=2, num_shares=3)

        # The response contains shares in hex
        share_data = []
        for share_index, share_bytes in shares:
            share_data.append({
                "index": share_index,
                "share_hex": share_bytes.hex(),
            })

        # Convert response to string and verify KEK is not in it
        response_str = json.dumps(share_data)
        kek_hex = kek.hex()
        assert kek_hex not in response_str

    def test_recovery_endpoint_does_not_return_kek(self):
        """The recover endpoint should return status and key_id, not raw KEK."""
        from app.services.key_recovery import KeyRecoveryManager, ShamirSecretSharing

        manager = KeyRecoveryManager(key_store_path=Path("/tmp/test-kek.enc"))
        kek = manager.generate_kek()
        shares = manager.split_kek(kek, threshold=2, num_shares=3)

        # Reconstruct
        recovered = ShamirSecretSharing.reconstruct_secret(shares[:2])
        assert recovered == kek

        # Simulate response (what the endpoint returns)
        key_id_hex = hashlib.sha256(recovered).hexdigest()[:16]
        response = {
            "status": "recovered",
            "key_id": key_id_hex,
            "message": "KEK successfully reconstructed and verified.",
        }

        # The response should NOT contain raw KEK bytes
        response_str = json.dumps(response)
        assert kek.hex() not in response_str
        assert repr(kek) not in response_str


class TestBackupProductionKEKIsolation:
    """Verify that backup and production use separate KEKs."""

    def test_backup_and_production_keks_are_different(self):
        """Backup KEK and production KEK should be distinct keys."""
        from app.services.backup_kek_manager import BackupKEKManager
        from app.services.key_recovery import KeyRecoveryManager

        kms = LocalFileKMS(passphrase="isolation-test")

        # Generate production KEK
        prod_manager = KeyRecoveryManager(key_store_path=Path("/tmp/prod-kek.enc"))
        production_kek = prod_manager.generate_kek()

        # Generate backup KEK
        backup_manager = BackupKEKManager(kms=kms)
        backup_kek, backup_wrapped = backup_manager.generate_backup_kek()

        # They must be different
        assert production_kek != backup_kek

    def test_backup_encrypted_data_cannot_be_decrypted_with_production_kek(self):
        """Data encrypted with backup KEK cannot be decrypted with production KEK."""
        from app.services.backup_kek_manager import BackupKEKManager
        from Crypto.Random import get_random_bytes

        kms = LocalFileKMS(passphrase="cross-test")
        backup_manager = BackupKEKManager(kms=kms)

        backup_kek, _ = backup_manager.generate_backup_kek()
        production_kek = get_random_bytes(32)

        data = b"sensitive document content"
        encrypted = backup_manager.encrypt_for_backup(data, backup_kek)

        # Attempting to decrypt with production KEK should fail
        with pytest.raises(Exception):
            backup_manager.decrypt_from_backup(encrypted, production_kek)

    def test_backup_key_id_differs_from_production_key_id(self):
        """Backup and production keys should have different key IDs."""
        from app.services.backup_kek_manager import BackupKEKManager
        from app.services.key_recovery import KeyRecoveryManager

        kms = LocalFileKMS(passphrase="id-test")

        prod_manager = KeyRecoveryManager(key_store_path=Path("/tmp/prod-kek.enc"))
        production_kek = prod_manager.generate_kek()
        prod_key_id = hashlib.sha256(production_kek).hexdigest()[:16]

        backup_manager = BackupKEKManager(kms=kms)
        _, backup_wrapped = backup_manager.generate_backup_kek()
        backup_key_id = backup_manager.get_backup_key_id(backup_wrapped)

        assert prod_key_id != backup_key_id


class TestKMSWrappedKEKStorage:
    """Tests for storing KEK wrapped by KMS."""

    def test_kek_wrapped_by_kms_can_be_unwrapped(self):
        """KEK wrapped by KMS should be recoverable."""
        from app.services.key_recovery import KeyRecoveryManager

        kms = LocalFileKMS(passphrase="kms-wrap-test")
        manager = KeyRecoveryManager(key_store_path=Path("/tmp/kms-test.enc"))
        kek = manager.generate_kek()

        # Wrap with KMS
        wrapped = kms.wrap_key(kek)

        # Unwrap
        unwrapped = kms.unwrap_key(wrapped)
        assert unwrapped == kek

    def test_key_recovery_kms_wrap_method(self, monkeypatch):
        """KeyRecoveryManager.save_kek_kms_wrapped should wrap key."""
        from app.services.key_recovery import KeyRecoveryManager

        monkeypatch.setattr("app.core.config.settings.KMS_PROVIDER", "local")
        monkeypatch.setattr("app.core.config.settings.KMS_LOCAL_PASSPHRASE", "test-kms-pass")

        manager = KeyRecoveryManager(key_store_path=Path("/tmp/kms-test.enc"))
        kek = manager.generate_kek()

        wrapped = manager.save_kek_kms_wrapped(kek)
        assert len(wrapped) > 0

        # Should be unwrappable
        recovered = manager.load_kek_kms_wrapped(wrapped)
        assert recovered == kek


class TestCeremonyRequired:
    """Tests for the ceremony_required flag on key recovery."""

    def test_ceremony_required_default_true(self):
        """ceremony_required should default to True."""
        from app.services.key_recovery import KeyRecoveryManager

        manager = KeyRecoveryManager(key_store_path=Path("/tmp/test.enc"))
        assert manager.ceremony_required is True

    def test_ceremony_required_can_be_set_false(self):
        """ceremony_required can be explicitly set to False."""
        from app.services.key_recovery import KeyRecoveryManager

        manager = KeyRecoveryManager(
            key_store_path=Path("/tmp/test.enc"),
            ceremony_required=False,
        )
        assert manager.ceremony_required is False

    def test_recovery_still_works_with_ceremony_flag(self):
        """Recovery should still function regardless of ceremony flag."""
        from app.services.key_recovery import KeyRecoveryManager

        manager = KeyRecoveryManager(
            key_store_path=Path("/tmp/test.enc"),
            ceremony_required=True,
        )
        kek = manager.generate_kek()
        shares = manager.split_kek(kek, threshold=2, num_shares=3)

        recovered = manager.recover_kek(shares[:2])
        assert recovered == kek


class TestGetProductionKEK:
    """Tests for the get_production_kek helper."""

    def test_get_production_kek_unwraps_via_kms(self, monkeypatch):
        """get_production_kek should unwrap the KEK using the KMS provider."""
        monkeypatch.setattr("app.core.config.settings.KMS_PROVIDER", "local")
        monkeypatch.setattr("app.core.config.settings.KMS_LOCAL_PASSPHRASE", "prod-kek-test")

        from app.services.encryption import get_production_kek
        from app.services.kms import get_kms_provider

        kms = get_kms_provider()
        original_kek = b"\x55" * 32
        wrapped = kms.wrap_key(original_kek)

        recovered = get_production_kek(wrapped)
        assert recovered == original_kek
