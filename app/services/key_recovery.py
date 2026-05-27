"""Key recovery using Shamir's Secret Sharing over GF(256).

Implements polynomial interpolation over the Galois Field GF(2^8) using
the irreducible polynomial x^8 + x^4 + x^3 + x + 1 (0x11B).
"""

import json
from pathlib import Path

from Crypto.Cipher import AES
from Crypto.Protocol.KDF import scrypt
from Crypto.Random import get_random_bytes

# GF(256) with irreducible polynomial x^8 + x^4 + x^3 + x + 1
_GF256_MOD = 0x11B

# Precomputed exp and log tables for GF(256)
_EXP_TABLE = [0] * 256
_LOG_TABLE = [0] * 256


def _init_tables():
    """Initialize GF(256) exp and log lookup tables using generator 3."""
    x = 1
    for i in range(255):
        _EXP_TABLE[i] = x
        _LOG_TABLE[x] = i
        x = (x << 1) ^ x  # multiply by 3 (generator)
        if x & 0x100:
            x ^= _GF256_MOD
    # _EXP_TABLE[255] wraps around for convenience
    _EXP_TABLE[255] = _EXP_TABLE[0]


_init_tables()


def _gf256_add(a: int, b: int) -> int:
    """Addition in GF(256) is XOR."""
    return a ^ b


def _gf256_mul(a: int, b: int) -> int:
    """Multiplication in GF(256) using log/exp tables."""
    if a == 0 or b == 0:
        return 0
    return _EXP_TABLE[(_LOG_TABLE[a] + _LOG_TABLE[b]) % 255]


def _gf256_inv(a: int) -> int:
    """Multiplicative inverse in GF(256)."""
    if a == 0:
        raise ValueError("Zero has no inverse in GF(256)")
    return _EXP_TABLE[255 - _LOG_TABLE[a]]


class ShamirSecretSharing:
    """Shamir's Secret Sharing over GF(256)."""

    @staticmethod
    def split_secret(
        secret: bytes, threshold: int, num_shares: int
    ) -> list[tuple[int, bytes]]:
        """Split secret into num_shares shares, requiring threshold to reconstruct.

        Each share is (index, share_bytes) where index is 1..num_shares.
        Each byte of the secret is independently shared using a random polynomial
        of degree (threshold - 1) over GF(256).
        """
        if threshold < 2:
            raise ValueError("Threshold must be at least 2")
        if num_shares < threshold:
            raise ValueError("Number of shares must be >= threshold")
        if num_shares > 255:
            raise ValueError("Maximum 255 shares supported")

        shares = [(i, bytearray(len(secret))) for i in range(1, num_shares + 1)]

        for byte_idx, secret_byte in enumerate(secret):
            # Generate random polynomial coefficients (degree threshold-1)
            # coefficients[0] = secret_byte, coefficients[1..threshold-1] = random
            coefficients = [secret_byte] + [
                get_random_bytes(1)[0] for _ in range(threshold - 1)
            ]

            # Evaluate polynomial at each share point
            for share_idx, (x, share_bytes) in enumerate(shares):
                # Evaluate P(x) = c0 + c1*x + c2*x^2 + ... using Horner's method
                value = 0
                for coeff in reversed(coefficients):
                    value = _gf256_add(_gf256_mul(value, x), coeff)
                share_bytes[byte_idx] = value

        return [(idx, bytes(data)) for idx, data in shares]

    @staticmethod
    def reconstruct_secret(shares: list[tuple[int, bytes]]) -> bytes:
        """Reconstruct secret from threshold or more shares.

        Uses Lagrange interpolation over GF(256) to recover the secret
        (the constant term of the polynomial).
        """
        if len(shares) < 2:
            raise ValueError("Need at least 2 shares to reconstruct")

        # All shares must be same length
        share_len = len(shares[0][1])
        if not all(len(s[1]) == share_len for s in shares):
            raise ValueError("All shares must be the same length")

        secret = bytearray(share_len)
        x_coords = [s[0] for s in shares]

        for byte_idx in range(share_len):
            # Lagrange interpolation to find P(0)
            result = 0
            for i, (xi, share_i) in enumerate(shares):
                yi = share_i[byte_idx]
                if yi == 0:
                    continue

                # Compute Lagrange basis polynomial at x=0: product of xj/(xj-xi) for j!=i
                lagrange = 1
                for j, xj in enumerate(x_coords):
                    if i == j:
                        continue
                    # At x=0: numerator = 0 - xj = xj (since -xj = xj in GF(256))
                    # denominator = xi - xj = xi XOR xj
                    numerator = xj
                    denominator = _gf256_add(xi, xj)
                    if denominator == 0:
                        raise ValueError("Duplicate share indices detected")
                    lagrange = _gf256_mul(
                        lagrange, _gf256_mul(numerator, _gf256_inv(denominator))
                    )

                result = _gf256_add(result, _gf256_mul(yi, lagrange))

            secret[byte_idx] = result

        return bytes(secret)


class KeyRecoveryManager:
    """Manages KEK generation, splitting, and recovery."""

    def __init__(self, key_store_path: Path):
        self.key_store_path = key_store_path

    def generate_kek(self) -> bytes:
        """Generate a new 32-byte KEK."""
        return get_random_bytes(32)

    def split_kek(
        self, kek: bytes, threshold: int = 2, num_shares: int = 3
    ) -> list[tuple[int, bytes]]:
        """Split KEK into shares using Shamir."""
        return ShamirSecretSharing.split_secret(kek, threshold, num_shares)

    def recover_kek(self, shares: list[tuple[int, bytes]]) -> bytes:
        """Reconstruct KEK from shares."""
        return ShamirSecretSharing.reconstruct_secret(shares)

    def save_kek_encrypted(self, kek: bytes, passphrase: str) -> None:
        """Save KEK encrypted with a passphrase to key_store_path.

        Uses scrypt for key derivation and AES-256-GCM for encryption.
        """
        salt = get_random_bytes(16)
        derived_key = scrypt(passphrase.encode(), salt, 32, N=2**14, r=8, p=1)
        cipher = AES.new(derived_key, AES.MODE_GCM, nonce=get_random_bytes(12))
        ciphertext, tag = cipher.encrypt_and_digest(kek)

        data = {
            "salt": salt.hex(),
            "nonce": cipher.nonce.hex(),
            "tag": tag.hex(),
            "ciphertext": ciphertext.hex(),
        }

        self.key_store_path.parent.mkdir(parents=True, exist_ok=True)
        self.key_store_path.write_text(json.dumps(data), encoding="utf-8")

    def load_kek_encrypted(self, passphrase: str) -> bytes:
        """Load and decrypt KEK from key_store_path."""
        data = json.loads(self.key_store_path.read_text(encoding="utf-8"))

        salt = bytes.fromhex(data["salt"])
        nonce = bytes.fromhex(data["nonce"])
        tag = bytes.fromhex(data["tag"])
        ciphertext = bytes.fromhex(data["ciphertext"])

        derived_key = scrypt(passphrase.encode(), salt, 32, N=2**14, r=8, p=1)
        cipher = AES.new(derived_key, AES.MODE_GCM, nonce=nonce)
        return cipher.decrypt_and_verify(ciphertext, tag)
