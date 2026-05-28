from datetime import datetime

from pydantic import BaseModel


class SignDocumentRequest(BaseModel):
    certificate_pem: str | None = None


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
