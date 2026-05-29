from fastapi import APIRouter, HTTPException

from app.schemas.scanner import ScannerDevice, ScanRequest, ScanResponse
from app.services.scanner import ScannerService

router = APIRouter(tags=["scanner"])

scanner_service = ScannerService()


@router.get("/api/scanner/devices", response_model=list[ScannerDevice])
async def list_scanner_devices():
    """List available scanner devices."""
    devices = scanner_service.list_devices()
    return [
        ScannerDevice(
            id=d["id"],
            name=d["name"],
            backend=d["backend"],
            capabilities=d.get("capabilities", {}),
        )
        for d in devices
    ]


@router.post("/api/scanner/scan", response_model=ScanResponse)
async def scan_document(request: ScanRequest):
    """Scan a document using the specified device."""
    if scanner_service._backend is None:
        raise HTTPException(
            status_code=503,
            detail="No scanner backend available",
        )

    try:
        file_path = scanner_service.scan(
            device_id=request.device_id,
            dpi=request.dpi,
            color_mode=request.color_mode,
        )
        return ScanResponse(
            file_path=str(file_path),
            status="success",
            message="Document scanned successfully",
        )
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
