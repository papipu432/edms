"""Envelope encryption service using AES-256-GCM.

File format:
    MAGIC(4) | VERSION(4) | DEK_NONCE(12) | DEK_TAG(16) | WRAPPED_DEK(32) |
    DATA_NONCE(12) | DATA_TAG(16) | CIPHERTEXT(...)
"""

from pathlib import Path

from Crypto.Cipher import AES
from Crypto.Random import get_random_bytes

MAGIC = b"EDMS"
VERSION = 1

# Header sizes
MAGIC_SIZE = 4
VERSION_SIZE = 4
NONCE_SIZE = 12
TAG_SIZE = 16
DEK_SIZE = 32


class EnvelopeEncryption:
    """Envelope encryption with unique DEKs per file, wrapped by a KEK."""

    MAGIC = MAGIC
    VERSION = VERSION

    @staticmethod
    def generate_dek() -> bytes:
        """Generate a 32-byte random Data Encryption Key."""
        return get_random_bytes(DEK_SIZE)

    @staticmethod
    def encrypt_dek(dek: bytes, kek: bytes) -> tuple[bytes, bytes, bytes]:
        """Wrap DEK with KEK using AES-256-GCM.

        Returns:
            (nonce, tag, ciphertext) where ciphertext is the wrapped DEK.
        """
        cipher = AES.new(kek, AES.MODE_GCM, nonce=get_random_bytes(NONCE_SIZE))
        ciphertext, tag = cipher.encrypt_and_digest(dek)
        return cipher.nonce, tag, ciphertext

    @staticmethod
    def decrypt_dek(nonce: bytes, tag: bytes, ciphertext: bytes, kek: bytes) -> bytes:
        """Unwrap DEK from KEK."""
        cipher = AES.new(kek, AES.MODE_GCM, nonce=nonce)
        return cipher.decrypt_and_verify(ciphertext, tag)

    @staticmethod
    def encrypt_file(plaintext_path: Path, output_path: Path, kek: bytes) -> None:
        """Encrypt file with unique DEK, store wrapped DEK in file header.

        Format:
            MAGIC(4) | VERSION(4) | DEK_NONCE(12) | DEK_TAG(16) | WRAPPED_DEK(32) |
            DATA_NONCE(12) | DATA_TAG(16) | CIPHERTEXT(...)
        """
        dek = bytearray(EnvelopeEncryption.generate_dek())
        try:
            # Wrap DEK with KEK
            dek_nonce, dek_tag, wrapped_dek = EnvelopeEncryption.encrypt_dek(
                bytes(dek), kek
            )

            # Read plaintext
            plaintext = plaintext_path.read_bytes()

            # Encrypt data with DEK
            data_cipher = AES.new(bytes(dek), AES.MODE_GCM, nonce=get_random_bytes(NONCE_SIZE))
            ciphertext, data_tag = data_cipher.encrypt_and_digest(plaintext)

            # Write output
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "wb") as f:
                f.write(MAGIC)
                f.write(VERSION.to_bytes(4, "big"))
                f.write(dek_nonce)  # 12 bytes
                f.write(dek_tag)  # 16 bytes
                f.write(wrapped_dek)  # 32 bytes
                f.write(data_cipher.nonce)  # 12 bytes
                f.write(data_tag)  # 16 bytes
                f.write(ciphertext)
        finally:
            EnvelopeEncryption.dek_zeroize(dek)

    @staticmethod
    def decrypt_file(encrypted_path: Path, output_path: Path, kek: bytes) -> None:
        """Decrypt file by reading header, unwrapping DEK, decrypting content."""
        with open(encrypted_path, "rb") as f:
            # Read and verify magic
            magic = f.read(MAGIC_SIZE)
            if magic != MAGIC:
                raise ValueError("Invalid file format: bad magic bytes")

            # Read and verify version
            version_bytes = f.read(VERSION_SIZE)
            version = int.from_bytes(version_bytes, "big")
            if version != VERSION:
                raise ValueError(f"Unsupported version: {version}")

            # Read wrapped DEK components
            dek_nonce = f.read(NONCE_SIZE)
            dek_tag = f.read(TAG_SIZE)
            wrapped_dek = f.read(DEK_SIZE)

            # Read data encryption components
            data_nonce = f.read(NONCE_SIZE)
            data_tag = f.read(TAG_SIZE)
            ciphertext = f.read()

        # Unwrap DEK
        dek = bytearray(
            EnvelopeEncryption.decrypt_dek(dek_nonce, dek_tag, wrapped_dek, kek)
        )
        try:
            # Decrypt data
            data_cipher = AES.new(bytes(dek), AES.MODE_GCM, nonce=data_nonce)
            plaintext = data_cipher.decrypt_and_verify(ciphertext, data_tag)

            # Write output
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(plaintext)
        finally:
            EnvelopeEncryption.dek_zeroize(dek)

    @staticmethod
    def dek_zeroize(dek: bytearray) -> None:
        """Overwrite DEK memory with zeros."""
        for i in range(len(dek)):
            dek[i] = 0
