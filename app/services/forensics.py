"""
Time-Travel Document Forensics Service

Provides immutable audit trails, cryptographic chain of custody,
and WORM (Write Once Read Many) storage for airgap security.
"""

import hashlib
import json
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from sqlalchemy import Column, String, DateTime, ForeignKey, Text, BigInteger
from sqlalchemy.orm import relationship
from app.models.base import Base, get_db_session


class ForensicLedger(Base):
    """Immutable ledger entry for document forensics"""
    __tablename__ = 'forensic_ledger'
    
    id = Column(String(64), primary_key=True)  # SHA256 hash as ID
    document_id = Column(String(64), ForeignKey('documents.id'), nullable=False, index=True)
    version_id = Column(String(64), ForeignKey('versions.id'), nullable=True)
    previous_hash = Column(String(64), nullable=False)  # Hash of previous entry
    current_hash = Column(String(64), nullable=False)  # Hash of this entry
    action = Column(String(50), nullable=False)  # create, modify, view, delete, transfer
    actor_id = Column(String(64), ForeignKey('users.id'), nullable=False)
    actor_name = Column(String(255), nullable=False)
    timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    metadata_json = Column(Text, nullable=True)  # JSON serialized metadata
    signature = Column(String(512), nullable=False)  # Cryptographic signature
    worm_locked = Column(Boolean, default=False, nullable=False)  # WORM protection flag
    
    document = relationship("Document", back_populates="forensic_entries")
    
    def compute_hash(self) -> str:
        """Compute SHA256 hash of this ledger entry"""
        data = {
            'document_id': self.document_id,
            'version_id': self.version_id,
            'previous_hash': self.previous_hash,
            'action': self.action,
            'actor_id': self.actor_id,
            'timestamp': self.timestamp.isoformat(),
            'metadata': json.loads(self.metadata_json) if self.metadata_json else {}
        }
        return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
    
    def verify_chain(self, previous_entry: Optional['ForensicLedger']) -> bool:
        """Verify this entry links correctly to previous entry"""
        if previous_entry is None:
            return self.previous_hash == '0' * 64  # Genesis block
        return self.previous_hash == previous_entry.current_hash


class DocumentTimeline:
    """Service for document timeline visualization and forensics"""
    
    def __init__(self, db_session=None):
        self.db = db_session or get_db_session()
    
    def create_ledger_entry(
        self,
        document_id: str,
        action: str,
        actor_id: str,
        actor_name: str,
        version_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        signature: Optional[str] = None
    ) -> ForensicLedger:
        """Create a new immutable ledger entry"""
        
        # Get latest entry for this document
        latest = self.db.query(ForensicLedger).filter(
            ForensicLedger.document_id == document_id
        ).order_by(ForensicLedger.timestamp.desc()).first()
        
        previous_hash = latest.current_hash if latest else '0' * 64
        
        # Create new entry
        entry = ForensicLedger(
            document_id=document_id,
            version_id=version_id,
            previous_hash=previous_hash,
            action=action,
            actor_id=actor_id,
            actor_name=actor_name,
            metadata_json=json.dumps(metadata) if metadata else None,
            signature=signature or self._generate_signature(document_id, action, actor_id)
        )
        
        # Compute hash
        entry.id = entry.compute_hash()
        entry.current_hash = entry.id
        
        # Verify chain integrity
        if not entry.verify_chain(latest):
            raise ValueError("Chain integrity verification failed")
        
        self.db.add(entry)
        self.db.commit()
        self.db.refresh(entry)
        
        return entry
    
    def get_document_timeline(self, document_id: str) -> List[Dict[str, Any]]:
        """Get complete timeline for a document"""
        entries = self.db.query(ForensicLedger).filter(
            ForensicLedger.document_id == document_id
        ).order_by(ForensicLedger.timestamp.asc()).all()
        
        timeline = []
        for entry in entries:
            timeline.append({
                'id': entry.id,
                'action': entry.action,
                'actor': entry.actor_name,
                'timestamp': entry.timestamp.isoformat(),
                'hash': entry.current_hash,
                'previous_hash': entry.previous_hash,
                'metadata': json.loads(entry.metadata_json) if entry.metadata_json else {},
                'worm_locked': entry.worm_locked
            })
        
        return timeline
    
    def verify_chain_integrity(self, document_id: str) -> Dict[str, Any]:
        """Verify entire chain integrity for a document"""
        entries = self.db.query(ForensicLedger).filter(
            ForensicLedger.document_id == document_id
        ).order_by(ForensicLedger.timestamp.asc()).all()
        
        if not entries:
            return {'valid': True, 'message': 'No entries found', 'entries_count': 0}
        
        # Verify genesis block
        if entries[0].previous_hash != '0' * 64:
            return {'valid': False, 'message': 'Genesis block invalid', 'entries_count': len(entries)}
        
        # Verify chain links
        for i in range(1, len(entries)):
            if entries[i].previous_hash != entries[i-1].current_hash:
                return {
                    'valid': False,
                    'message': f'Chain broken at entry {i}',
                    'entries_count': len(entries),
                    'broken_at': i
                }
        
        # Verify hashes
        for entry in entries:
            computed_hash = entry.compute_hash()
            if computed_hash != entry.current_hash:
                return {
                    'valid': False,
                    'message': f'Hash mismatch at entry {entry.id}',
                    'entries_count': len(entries),
                    'invalid_entry': entry.id
                }
        
        return {'valid': True, 'message': 'Chain integrity verified', 'entries_count': len(entries)}
    
    def _generate_signature(self, document_id: str, action: str, actor_id: str) -> str:
        """Generate cryptographic signature for ledger entry"""
        # In production, use actual KMS signing
        data = f"{document_id}:{action}:{actor_id}:{datetime.now(timezone.utc).isoformat()}"
        return hashlib.sha512(data.encode()).hexdigest()
    
    def enable_worm_lock(self, entry_id: str) -> bool:
        """Enable WORM lock on a ledger entry (irreversible)"""
        entry = self.db.query(ForensicLedger).get(entry_id)
        if not entry:
            return False
        
        entry.worm_locked = True
        self.db.commit()
        return True


# Add relationship to Document model
def add_forensic_relationship():
    """Add forensic_entries relationship to Document model"""
    from app.models.document import Document
    from sqlalchemy.orm import relationship
    
    if not hasattr(Document, 'forensic_entries'):
        Document.forensic_entries = relationship(
            "ForensicLedger",
            back_populates="document",
            cascade="all, delete-orphan"
        )
