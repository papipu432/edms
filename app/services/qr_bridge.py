"""
QR Code Physical-to-Digital Bridge Service

Generates unique QR codes for documents/folders to link physical locations
(file cabinets, meeting rooms, assets) to digital content.
"""

import io
import base64
import qrcode
from typing import Optional, Dict, Any, List
from sqlalchemy import Column, String, DateTime, ForeignKey, Boolean, Text
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from app.models.base import Base, get_db_session


class QRCodeLink(Base):
    """QR code linking physical items to digital content"""
    __tablename__ = 'qr_code_links'
    
    id = Column(String(64), primary_key=True)
    document_id = Column(String(64), ForeignKey('documents.id'), nullable=True)
    folder_id = Column(String(64), ForeignKey('groups.id'), nullable=True)
    location_name = Column(String(255), nullable=False)  # e.g., "File Cabinet A-12"
    location_type = Column(String(50), nullable=False)  # cabinet, room, asset, shelf
    qr_data = Column(Text, nullable=False)  # Encoded URL/data
    qr_image_base64 = Column(Text, nullable=True)  # Cached QR image
    scan_count = Column(Integer, default=0, nullable=False)
    last_scanned_at = Column(DateTime(timezone=True), nullable=True)
    last_scanned_by = Column(String(64), ForeignKey('users.id'), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    created_by = Column(String(64), ForeignKey('users.id'), nullable=False)
    active = Column(Boolean, default=True, nullable=False)
    
    def generate_qr_data(self, base_url: str) -> str:
        """Generate QR code data (URL)"""
        return f"{base_url}/scan/qr/{self.id}"
    
    def generate_qr_image(self, data: str, size: int = 300) -> str:
        """Generate QR code image as base64"""
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(data)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        img = img.resize((size, size))
        
        buffered = io.BytesIO()
        img.save(buffered, format="PNG")
        return base64.b64encode(buffered.getvalue()).decode()


class QRCodeService:
    """Service for managing QR code links"""
    
    def __init__(self, db_session=None):
        self.db = db_session or get_db_session()
    
    def create_qr_link(
        self,
        location_name: str,
        location_type: str,
        created_by: str,
        document_id: Optional[str] = None,
        folder_id: Optional[str] = None,
        base_url: str = "https://edms.local"
    ) -> QRCodeLink:
        """Create a new QR code link"""
        import uuid
        
        qr_link = QRCodeLink(
            id=str(uuid.uuid4()),
            document_id=document_id,
            folder_id=folder_id,
            location_name=location_name,
            location_type=location_type,
            created_by=created_by
        )
        
        # Generate QR data and image
        qr_data = qr_link.generate_qr_data(base_url)
        qr_link.qr_data = qr_data
        qr_link.qr_image_base64 = qr_link.generate_qr_image(qr_data)
        
        self.db.add(qr_link)
        self.db.commit()
        self.db.refresh(qr_link)
        
        return qr_link
    
    def scan_qr(self, qr_id: str, user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Process QR code scan"""
        qr_link = self.db.query(QRCodeLink).get(qr_id)
        if not qr_link or not qr_link.active:
            return None
        
        # Update scan statistics
        qr_link.scan_count += 1
        qr_link.last_scanned_at = datetime.now(timezone.utc)
        qr_link.last_scanned_by = user_id
        self.db.commit()
        
        # Return linked content
        result = {
            'id': qr_link.id,
            'location': qr_link.location_name,
            'type': qr_link.location_type,
            'document_id': qr_link.document_id,
            'folder_id': qr_link.folder_id
        }
        
        return result
    
    def get_qr_links_for_location(self, location_type: Optional[str] = None) -> List[QRCodeLink]:
        """Get all QR links, optionally filtered by type"""
        query = self.db.query(QRCodeLink).filter(QRCodeLink.active == True)
        if location_type:
            query = query.filter(QRCodeLink.location_type == location_type)
        return query.all()
    
    def deactivate_qr_link(self, qr_id: str) -> bool:
        """Deactivate a QR code link"""
        qr_link = self.db.query(QRCodeLink).get(qr_id)
        if not qr_link:
            return False
        
        qr_link.active = False
        self.db.commit()
        return True
    
    def export_qr_labels(self, qr_ids: List[str]) -> Dict[str, str]:
        """Export QR code images for printing labels"""
        labels = {}
        for qr_id in qr_ids:
            qr_link = self.db.query(QRCodeLink).get(qr_id)
            if qr_link and qr_link.qr_image_base64:
                labels[qr_link.location_name] = qr_link.qr_image_base64
        return labels


def get_qr_service():
    """Get QR code service instance"""
    return QRCodeService()
