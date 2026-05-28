from datetime import datetime

from pydantic import BaseModel


class SignDocumentRequest(BaseModel):
    """Request to sign a document.

    The optional private_key_pem field is used for server-side signing ceremony:
    the key signs the document content to produce a cryptographic signature that
    is stored alongside the hash-based signature. The private key is used only
    within the signing operation and is not persisted or transmitted further.
    """

    private_key_pem: str | None = None


class SignatureResponse(BaseModel):
    id: int
    document_id: int
    signer_id: str
    signature_hash: str
    qr_code_path: str | None = None
    signed_at: datetime
    certificate_data: str | None = None
    verification_url: str | None = None
    is_valid: bool

    model_config = {"from_attributes": True}


class VerifyResponse(BaseModel):
    valid: bool
    document_id: int | None = None
    signer_username: str | None = None
    signed_at: datetime | None = None
