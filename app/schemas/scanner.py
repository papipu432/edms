from pydantic import BaseModel


class ScannerDevice(BaseModel):
    id: str
    name: str
    backend: str
    capabilities: dict = {}


class ScanRequest(BaseModel):
    device_id: str
    dpi: int = 300
    color_mode: str = "color"  # color, grayscale, bw


class ScanResponse(BaseModel):
    file_path: str
    status: str
    message: str = ""
