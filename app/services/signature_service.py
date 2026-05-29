import hashlib
import logging
import os
from pathlib import Path

import qrcode
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

logger = logging.getLogger(__name__)

STORAGE_DIR = Path("storage/qrcodes")


def generate_signature(content_bytes: bytes, user_id: str, timestamp: str) -> str:
    """Generate SHA-256 hash of content + user_id + timestamp."""
    data = content_bytes + user_id.encode("utf-8") + timestamp.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def generate_qr_code(verification_url: str, output_path: str) -> str:
    """Generate a QR code image for the verification URL."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    img = qrcode.make(verification_url)
    img.save(output_path)
    return output_path


def sign_with_certificate(content_bytes: bytes, private_key_pem: str) -> str | None:
    """Sign content with a PEM-encoded private key. Returns hex-encoded signature.

    Used in server-side signing ceremony: the private key signs the content to
    produce a verifiable cryptographic signature. The key material is used only
    within this operation and is not stored or forwarded.
    """
    try:
        private_key = serialization.load_pem_private_key(
            private_key_pem.encode("utf-8"), password=None
        )
        signature = private_key.sign(  # type: ignore[union-attr]
            content_bytes,
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
        return signature.hex()
    except Exception as exc:
        logger.error("Failed to sign content with provided private key: %s", exc)
        return None
