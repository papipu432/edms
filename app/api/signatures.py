from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.document import Document
from app.models.signature import DocumentSignature
from app.models.user import User
from app.schemas.signature import (
    SignatureResponse,
    SignDocumentRequest,
    VerifyResponse,
)
from app.services.signature_service import (
    generate_qr_code,
    generate_signature,
    sign_with_certificate,
    STORAGE_DIR,
)

router = APIRouter(tags=["signatures"])


@router.post(
    "/api/documents/{document_id}/sign",
    response_model=SignatureResponse,
    status_code=201,
)
async def sign_document(
    document_id: int,
    data: SignDocumentRequest | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Sign a document - generates hash, QR code, and stores signature."""
    document = await db.get(Document, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    # Read document content from storage path, fallback to path string
    storage_path = Path(document.storage_path)
    if storage_path.exists():
        content_bytes = storage_path.read_bytes()
    else:
        content_bytes = document.storage_path.encode("utf-8")

    timestamp = datetime.now(timezone.utc).isoformat()
    signature_hash = generate_signature(content_bytes, current_user.id, timestamp)

    # Check for duplicate hash
    existing = await db.execute(
        select(DocumentSignature).where(
            DocumentSignature.signature_hash == signature_hash
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Signature already exists")

    verification_url = f"/api/signatures/verify/{signature_hash}"

    # Generate QR code
    qr_output_path = str(STORAGE_DIR / f"{signature_hash}.png")
    try:
        generate_qr_code(verification_url, qr_output_path)
    except Exception:
        qr_output_path = None

    # Optional certificate signing
    certificate_data = None
    if data and data.private_key_pem:
        certificate_data = sign_with_certificate(content_bytes, data.private_key_pem)
        if certificate_data is None:
            raise HTTPException(
                status_code=422, detail="Invalid private key or signing failed"
            )

    signature = DocumentSignature(
        document_id=document_id,
        signer_id=current_user.id,
        signature_hash=signature_hash,
        qr_code_path=qr_output_path,
        signed_at=datetime.fromisoformat(timestamp),
        certificate_data=certificate_data,
        verification_url=verification_url,
        is_valid=True,
    )
    db.add(signature)
    await db.flush()
    await db.refresh(signature)
    return signature


@router.get(
    "/api/signatures/verify/{hash}",
    response_model=VerifyResponse,
)
async def verify_signature(
    hash: str,
    db: AsyncSession = Depends(get_db),
):
    """Public endpoint - verify a signature by hash. No authentication required."""
    result = await db.execute(
        select(DocumentSignature).where(DocumentSignature.signature_hash == hash)
    )
    signature = result.scalar_one_or_none()
    if not signature or not signature.is_valid:
        return VerifyResponse(valid=False)

    # Get signer username
    signer = await db.get(User, signature.signer_id)
    signer_username = signer.username if signer else None

    return VerifyResponse(
        valid=True,
        document_id=signature.document_id,
        signer_username=signer_username,
        signed_at=signature.signed_at,
    )


@router.get(
    "/api/documents/{document_id}/signatures",
    response_model=list[SignatureResponse],
)
async def list_signatures(
    document_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all signatures for a document."""
    document = await db.get(Document, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    result = await db.execute(
        select(DocumentSignature)
        .where(DocumentSignature.document_id == document_id)
        .order_by(DocumentSignature.signed_at.desc())
    )
    return list(result.scalars().all())
