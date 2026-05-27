"""Encryption settings API router."""

import hashlib
import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.security import require_role
from app.models.encryption import EncryptionKey, KeyShare
from app.services.key_recovery import KeyRecoveryManager, ShamirSecretSharing

router = APIRouter()
logger = logging.getLogger(__name__)


def _get_key_manager() -> KeyRecoveryManager:
    key_store = Path(settings.STORAGE_PATH) / ".keys" / "kek.enc"
    return KeyRecoveryManager(key_store_path=key_store)


@router.get("/settings/encryption", response_class=HTMLResponse)
async def encryption_settings_page(
    request: Request,
    _user=Depends(require_role("admin")),
):
    """Render the encryption settings HTML page."""
    from app.main import templates

    return templates.TemplateResponse(
        "settings_encryption.html", {"request": request}
    )


@router.get("/api/settings/encryption/status")
async def encryption_status(
    _user=Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    """Get current encryption key status."""
    result = await db.execute(
        select(EncryptionKey).where(
            EncryptionKey.key_type == "kek",
            EncryptionKey.is_active == True,  # noqa: E712
        )
    )
    active_key = result.scalar_one_or_none()

    if not active_key:
        return {
            "initialized": False,
            "key_id": None,
            "created_at": None,
            "shares_total": 0,
            "shares_distributed": 0,
        }

    # Get share info
    shares_result = await db.execute(
        select(KeyShare).where(KeyShare.key_id == active_key.id)
    )
    shares = shares_result.scalars().all()
    distributed = sum(1 for s in shares if s.is_distributed)

    return {
        "initialized": True,
        "key_id": active_key.key_id_hex,
        "created_at": active_key.created_at.isoformat() if active_key.created_at else None,
        "shares_total": len(shares),
        "shares_distributed": distributed,
    }


@router.post("/api/settings/encryption/init")
async def initialize_encryption(
    request: Request,
    _user=Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    """Initialize encryption by generating KEK and splitting into shares."""
    body = await request.json()
    threshold = body.get("threshold", 2)
    num_shares = body.get("num_shares", 3)
    passphrase = body.get("passphrase", "")
    share_holders = body.get("share_holders", [])

    if threshold < 2:
        raise HTTPException(status_code=400, detail="Threshold must be at least 2")
    if num_shares < threshold:
        raise HTTPException(
            status_code=400, detail="Number of shares must be >= threshold"
        )
    if not passphrase:
        raise HTTPException(status_code=400, detail="Passphrase is required")

    # Check if KEK already exists
    existing = await db.execute(
        select(EncryptionKey).where(
            EncryptionKey.key_type == "kek",
            EncryptionKey.is_active == True,  # noqa: E712
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=409, detail="Encryption already initialized. Deactivate existing key first."
        )

    # Generate and split KEK
    manager = _get_key_manager()
    kek = manager.generate_kek()
    shares = manager.split_kek(kek, threshold=threshold, num_shares=num_shares)

    # Save KEK encrypted with passphrase
    manager.save_kek_encrypted(kek, passphrase)

    # Also wrap with KMS for operational use
    try:
        manager.save_kek_kms_wrapped(kek)
        logger.info("KEK wrapped with KMS provider for operational use")
    except Exception:
        # KMS wrapping is optional - passphrase-based storage is the fallback
        logger.info("KMS wrapping skipped (provider may not be configured)")

    # Create DB record for the key
    key_id_hex = hashlib.sha256(kek).hexdigest()[:16]
    logger.info("Encryption initialized with key_id=%s", key_id_hex)
    enc_key = EncryptionKey(
        id=str(uuid.uuid4()),
        key_type="kek",
        key_id_hex=key_id_hex,
        is_active=True,
        metadata_json={"threshold": threshold, "num_shares": num_shares},
    )
    db.add(enc_key)

    # Create share records
    share_data = []
    for idx, (share_index, share_bytes) in enumerate(shares):
        holder = share_holders[idx] if idx < len(share_holders) else f"holder_{share_index}"
        key_share = KeyShare(
            id=str(uuid.uuid4()),
            key_id=enc_key.id,
            share_index=share_index,
            share_holder=holder,
            is_distributed=False,
        )
        db.add(key_share)
        share_data.append({
            "index": share_index,
            "holder": holder,
            "share_hex": share_bytes.hex(),
        })

    await db.commit()

    return {
        "status": "initialized",
        "key_id": key_id_hex,
        "threshold": threshold,
        "shares": share_data,
        "message": "Store each share securely with the designated holder. "
        "Shares are shown only once.",
    }


@router.post("/api/settings/encryption/recover")
async def recover_encryption(
    request: Request,
    _user=Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    """Reconstruct KEK from provided shares."""
    body = await request.json()
    shares_input = body.get("shares", [])

    if len(shares_input) < 2:
        raise HTTPException(
            status_code=400, detail="At least 2 shares are required"
        )

    # Parse shares
    try:
        shares = [
            (int(s["index"]), bytes.fromhex(s["share_hex"]))
            for s in shares_input
        ]
    except (KeyError, ValueError) as e:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid share format: {e}",
        )

    # Reconstruct
    try:
        kek = ShamirSecretSharing.reconstruct_secret(shares)
    except Exception as e:
        logger.warning("KEK recovery failed: invalid shares provided")
        raise HTTPException(
            status_code=400,
            detail=f"Failed to reconstruct key: {e}",
        )

    # Verify against stored key ID
    key_id_hex = hashlib.sha256(kek).hexdigest()[:16]
    result = await db.execute(
        select(EncryptionKey).where(
            EncryptionKey.key_id_hex == key_id_hex,
            EncryptionKey.is_active == True,  # noqa: E712
        )
    )
    stored_key = result.scalar_one_or_none()

    if not stored_key:
        logger.warning("KEK recovery verification failed: key_id=%s not found", key_id_hex)
        raise HTTPException(
            status_code=400,
            detail="Reconstructed key does not match any active key. "
            "Shares may be incorrect or corrupted.",
        )

    logger.info("KEK successfully recovered and verified: key_id=%s", key_id_hex)
    return {
        "status": "recovered",
        "key_id": key_id_hex,
        "message": "KEK successfully reconstructed and verified.",
    }
