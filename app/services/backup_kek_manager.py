"""Backup KEK Manager - manages a separate KEK hierarchy for backup encryption.

The backup KEK is distinct from the production KEK to ensure isolation between
production encryption and backup encryption. The backup KEK is wrapped by the
KMS provider and stored in the backup_encryption_keys table.
"""

import logging

from Crypto.Cipher import AES
from Crypto.Random import get_random_bytes

from app.services.kms import KMSProvider, get_kms_provider

logger = logging.getLogger(__name__)

NONCE_SIZE = 12
TAG_SIZE = 16
KEY_SIZE = 32


class BackupKEKManager:
    """Manages a separate KEK hierarchy for backup encryption.

    Uses the KMS provider to wrap/unwrap the backup KEK, which is stored
    separately from the production KEK.
    """

    def __init__(self, kms: KMSProvider | None = None) -> None:
        self._kms = kms
        self._cached_kek: bytes | None = None

    @property
    def kms(self) -> KMSProvider:
        """Get the KMS provider, creating one if needed."""
        if self._kms is None:
            self._kms = get_kms_provider()
        return self._kms

    def generate_backup_kek(self) -> tuple[bytes, bytes]:
        """Generate a new backup KEK and return (raw_kek, wrapped_blob).

        The raw KEK is returned only for initial Shamir splitting if needed.
        The wrapped blob is what gets stored in the database.
        """
        raw_kek = get_random_bytes(KEY_SIZE)
        wrapped_blob = self.kms.wrap_key(raw_kek)
        logger.info("Generated new backup KEK")
        return raw_kek, wrapped_blob

    def unwrap_backup_kek(self, wrapped_blob: bytes) -> bytes:
        """Unwrap a stored backup KEK using the KMS provider."""
        return self.kms.unwrap_key(wrapped_blob)

    def encrypt_for_backup(self, data: bytes, kek: bytes) -> bytes:
        """Encrypt data using the backup KEK with AES-256-GCM envelope encryption.

        Format: NONCE(12) | TAG(16) | DEK_NONCE(12) | DEK_TAG(16) | WRAPPED_DEK(32) | CIPHERTEXT

        Uses a per-operation DEK wrapped by the backup KEK.
        """
        # Generate a per-operation DEK
        dek = bytearray(get_random_bytes(KEY_SIZE))
        try:
            # Wrap DEK with backup KEK
            dek_cipher = AES.new(kek, AES.MODE_GCM, nonce=get_random_bytes(NONCE_SIZE))
            wrapped_dek, dek_tag = dek_cipher.encrypt_and_digest(bytes(dek))

            # Encrypt data with DEK
            data_cipher = AES.new(bytes(dek), AES.MODE_GCM, nonce=get_random_bytes(NONCE_SIZE))
            ciphertext, data_tag = data_cipher.encrypt_and_digest(data)

            # Assemble output: data_nonce | data_tag | dek_nonce | dek_tag | wrapped_dek | ciphertext
            return (
                data_cipher.nonce
                + data_tag
                + dek_cipher.nonce
                + dek_tag
                + wrapped_dek
                + ciphertext
            )
        finally:
            # Zeroize DEK
            for i in range(len(dek)):
                dek[i] = 0

    def decrypt_from_backup(self, encrypted_data: bytes, kek: bytes) -> bytes:
        """Decrypt data that was encrypted with encrypt_for_backup.

        Parses the envelope format and uses the backup KEK to unwrap the DEK.
        """
        offset = 0
        data_nonce = encrypted_data[offset:offset + NONCE_SIZE]
        offset += NONCE_SIZE
        data_tag = encrypted_data[offset:offset + TAG_SIZE]
        offset += TAG_SIZE
        dek_nonce = encrypted_data[offset:offset + NONCE_SIZE]
        offset += NONCE_SIZE
        dek_tag = encrypted_data[offset:offset + TAG_SIZE]
        offset += TAG_SIZE
        wrapped_dek = encrypted_data[offset:offset + KEY_SIZE]
        offset += KEY_SIZE
        ciphertext = encrypted_data[offset:]

        # Unwrap DEK
        dek_cipher = AES.new(kek, AES.MODE_GCM, nonce=dek_nonce)
        dek = bytearray(dek_cipher.decrypt_and_verify(wrapped_dek, dek_tag))

        try:
            # Decrypt data
            data_cipher = AES.new(bytes(dek), AES.MODE_GCM, nonce=data_nonce)
            return data_cipher.decrypt_and_verify(ciphertext, data_tag)
        finally:
            # Zeroize DEK
            for i in range(len(dek)):
                dek[i] = 0

    def get_backup_key_id(self, wrapped_blob: bytes) -> str:
        """Generate a deterministic key ID from the wrapped blob for DB storage."""
        import hashlib
        return hashlib.sha256(wrapped_blob).hexdigest()[:16]
