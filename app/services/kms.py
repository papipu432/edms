"""Key Management Service abstraction layer.

Provides a pluggable KMS interface with implementations for:
- LocalFileKMS: File-based key wrapping using scrypt-derived root key + AES-GCM
- VaultKMS: HashiCorp Vault transit engine (stub)
- CosmianKMS: Cosmian KMS (stub)
"""

import json
import logging
from abc import ABC, abstractmethod

from Crypto.Cipher import AES
from Crypto.Protocol.KDF import scrypt
from Crypto.Random import get_random_bytes

logger = logging.getLogger(__name__)

# Constants
NONCE_SIZE = 12
TAG_SIZE = 16
SALT_SIZE = 32
SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1
KEY_SIZE = 32


class KMSProvider(ABC):
    """Abstract base class for Key Management Service providers."""

    @abstractmethod
    def wrap_key(self, plaintext_key: bytes) -> bytes:
        """Wrap (encrypt) a plaintext key.

        Args:
            plaintext_key: The raw key material to wrap.

        Returns:
            An opaque wrapped blob that can be stored safely.
        """
        ...

    @abstractmethod
    def unwrap_key(self, wrapped_blob: bytes) -> bytes:
        """Unwrap (decrypt) a previously wrapped key.

        Args:
            wrapped_blob: The wrapped key blob from wrap_key().

        Returns:
            The original plaintext key material.
        """
        ...

    @abstractmethod
    def generate_key(self) -> bytes:
        """Generate a new random key and return it wrapped.

        Returns:
            A wrapped blob containing a newly generated key.
        """
        ...


class LocalFileKMS(KMSProvider):
    """Local file-based KMS using scrypt-derived root key and AES-256-GCM.

    The root key is derived from a passphrase using scrypt. Keys are wrapped
    using AES-256-GCM with the derived root key.

    Wrapped blob format (JSON):
        {
            "v": 1,
            "salt": hex,
            "nonce": hex,
            "tag": hex,
            "ciphertext": hex
        }
    """

    def __init__(self, passphrase: str) -> None:
        if not passphrase:
            raise ValueError("KMS passphrase must not be empty")
        self._passphrase = passphrase

    def _derive_root_key(self, salt: bytes) -> bytes:
        """Derive the root wrapping key from passphrase and salt."""
        return scrypt(
            self._passphrase.encode(),
            salt,
            KEY_SIZE,
            N=SCRYPT_N,
            r=SCRYPT_R,
            p=SCRYPT_P,
        )

    def wrap_key(self, plaintext_key: bytes) -> bytes:
        """Wrap a key using AES-256-GCM with scrypt-derived root key."""
        salt = get_random_bytes(SALT_SIZE)
        root_key = self._derive_root_key(salt)
        nonce = get_random_bytes(NONCE_SIZE)
        cipher = AES.new(root_key, AES.MODE_GCM, nonce=nonce)
        ciphertext, tag = cipher.encrypt_and_digest(plaintext_key)

        blob = json.dumps({
            "v": 1,
            "salt": salt.hex(),
            "nonce": nonce.hex(),
            "tag": tag.hex(),
            "ciphertext": ciphertext.hex(),
        })
        return blob.encode("utf-8")

    def unwrap_key(self, wrapped_blob: bytes) -> bytes:
        """Unwrap a key from the wrapped blob."""
        data = json.loads(wrapped_blob.decode("utf-8"))

        if data.get("v") != 1:
            raise ValueError("Unsupported KMS blob version")

        salt = bytes.fromhex(data["salt"])
        nonce = bytes.fromhex(data["nonce"])
        tag = bytes.fromhex(data["tag"])
        ciphertext = bytes.fromhex(data["ciphertext"])

        root_key = self._derive_root_key(salt)
        cipher = AES.new(root_key, AES.MODE_GCM, nonce=nonce)
        return cipher.decrypt_and_verify(ciphertext, tag)

    def generate_key(self) -> bytes:
        """Generate a new 32-byte key and return it wrapped."""
        plaintext_key = get_random_bytes(KEY_SIZE)
        return self.wrap_key(plaintext_key)


class VaultKMS(KMSProvider):
    """HashiCorp Vault transit engine KMS provider (stub).

    Requires Vault URL and token for authentication.
    Uses the transit/keys endpoint for key wrapping operations.
    """

    def __init__(self, vault_url: str, vault_token: str) -> None:
        self._vault_url = vault_url.rstrip("/")
        self._vault_token = vault_token
        if not vault_url or not vault_token:
            raise ValueError("Vault URL and token are required")

    def wrap_key(self, plaintext_key: bytes) -> bytes:
        """Wrap key using Vault transit engine."""
        raise NotImplementedError(
            "VaultKMS is not yet implemented. Configure KMS_PROVIDER=local for now."
        )

    def unwrap_key(self, wrapped_blob: bytes) -> bytes:
        """Unwrap key using Vault transit engine."""
        raise NotImplementedError(
            "VaultKMS is not yet implemented. Configure KMS_PROVIDER=local for now."
        )

    def generate_key(self) -> bytes:
        """Generate key via Vault transit engine."""
        raise NotImplementedError(
            "VaultKMS is not yet implemented. Configure KMS_PROVIDER=local for now."
        )


class CosmianKMS(KMSProvider):
    """Cosmian KMS provider (stub).

    Provides integration with Cosmian's key management system.
    """

    def __init__(self, endpoint: str = "", api_key: str = "") -> None:
        self._endpoint = endpoint
        self._api_key = api_key

    def wrap_key(self, plaintext_key: bytes) -> bytes:
        """Wrap key using Cosmian KMS."""
        raise NotImplementedError(
            "CosmianKMS is not yet implemented. Configure KMS_PROVIDER=local for now."
        )

    def unwrap_key(self, wrapped_blob: bytes) -> bytes:
        """Unwrap key using Cosmian KMS."""
        raise NotImplementedError(
            "CosmianKMS is not yet implemented. Configure KMS_PROVIDER=local for now."
        )

    def generate_key(self) -> bytes:
        """Generate key via Cosmian KMS."""
        raise NotImplementedError(
            "CosmianKMS is not yet implemented. Configure KMS_PROVIDER=local for now."
        )


def get_kms_provider() -> KMSProvider:
    """Factory function to get the configured KMS provider.

    Returns the appropriate KMS provider based on KMS_PROVIDER setting.
    """
    from app.core.config import settings

    provider = settings.KMS_PROVIDER.lower()

    if provider == "local":
        passphrase = settings.KMS_LOCAL_PASSPHRASE
        if not passphrase:
            raise ValueError(
                "KMS_LOCAL_PASSPHRASE must be set when using local KMS provider"
            )
        return LocalFileKMS(passphrase=passphrase)
    elif provider == "vault":
        return VaultKMS(
            vault_url=settings.KMS_VAULT_URL,
            vault_token=settings.KMS_VAULT_TOKEN,
        )
    elif provider == "cosmian":
        return CosmianKMS()
    else:
        raise ValueError(f"Unknown KMS provider: {provider}")


def rate_limited_unwrap(wrapped_blob: bytes, client_ip: str = "unknown") -> bytes:
    """Unwrap a key with rate limiting per client IP.

    Checks the KMS rate limiter before performing the unwrap operation.
    If the rate limit is exceeded, logs a warning and raises KMSError.

    Args:
        wrapped_blob: The wrapped key blob to unwrap.
        client_ip: The client IP address for rate limiting.

    Returns:
        The unwrapped key bytes.

    Raises:
        KMSError: If the rate limit is exceeded.
    """
    from app.services.error_handling import KMSError
    from app.services.security_monitoring import get_kms_rate_limiter

    rate_limiter = get_kms_rate_limiter()

    if not rate_limiter.check_rate_limit(client_ip):
        logger.warning(
            "KMS rate limit exceeded for IP %s. Blocking unwrap operation.",
            client_ip,
        )
        raise KMSError("Rate limit exceeded")

    rate_limiter.record_call(client_ip)
    provider = get_kms_provider()
    return provider.unwrap_key(wrapped_blob)
