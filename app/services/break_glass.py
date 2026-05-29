"""
Break-Glass Emergency Access Service

M-of-N approval protocol for emergency admin access with time-limited credentials
and comprehensive logging.
"""

import hashlib
import secrets
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict, Any, Tuple
from sqlalchemy import Column, String, DateTime, ForeignKey, Boolean, Integer, Text
from sqlalchemy.orm import relationship
from app.models.base import Base, get_db_session


class BreakGlassRequest(Base):
    """Emergency access request requiring M-of-N approval"""
    __tablename__ = 'break_glass_requests'
    
    id = Column(String(64), primary_key=True)
    requester_id = Column(String(64), ForeignKey('users.id'), nullable=False)
    requester_name = Column(String(255), nullable=False)
    reason = Column(Text, nullable=False)
    requested_role = Column(String(100), nullable=False)  # e.g., "admin"
    required_approvals = Column(Integer, default=3, nullable=False)  # M value
    current_approvals = Column(Integer, default=0, nullable=False)
    approvers = Column(Text, nullable=True)  # JSON list of approver IDs
    status = Column(String(50), default='pending', nullable=False)  # pending, approved, denied, expired, used
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    expires_at = Column(DateTime(timezone=True), nullable=False)
    granted_at = Column(DateTime(timezone=True), nullable=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    temporary_token = Column(String(512), nullable=True)
    token_expires_at = Column(DateTime(timezone=True), nullable=True)
    usage_log = Column(Text, nullable=True)  # JSON log of actions taken
    
    def is_expired(self) -> bool:
        return datetime.now(timezone.utc) > self.expires_at
    
    def is_token_valid(self) -> bool:
        if not self.token_expires_at:
            return False
        return datetime.now(timezone.utc) < self.token_expires_at and self.status == 'active'


class BreakGlassApproval(Base):
    """Individual approval for break-glass request"""
    __tablename__ = 'break_glass_approvals'
    
    id = Column(String(64), primary_key=True)
    request_id = Column(String(64), ForeignKey('break_glass_requests.id'), nullable=False)
    approver_id = Column(String(64), ForeignKey('users.id'), nullable=False)
    approver_name = Column(String(255), nullable=False)
    approved = Column(Boolean, nullable=False)
    comment = Column(Text, nullable=True)
    approved_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class BreakGlassService:
    """Service for managing emergency access requests"""
    
    def __init__(self, db_session=None):
        self.db = db_session or get_db_session()
    
    def create_request(
        self,
        requester_id: str,
        requester_name: str,
        reason: str,
        requested_role: str,
        required_approvals: int = 3,
        approvers: List[str] = None,
        duration_hours: int = 4
    ) -> BreakGlassRequest:
        """Create a new break-glass request"""
        import uuid
        
        request = BreakGlassRequest(
            id=str(uuid.uuid4()),
            requester_id=requester_id,
            requester_name=requester_name,
            reason=reason,
            requested_role=requested_role,
            required_approvals=required_approvals,
            approvers=str(approvers) if approvers else None,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=24),  # Request expires in 24h
            status='pending'
        )
        
        self.db.add(request)
        self.db.commit()
        self.db.refresh(request)
        
        # Send notifications to approvers
        self._notify_approvers(request, approvers or [])
        
        return request
    
    def approve_request(
        self,
        request_id: str,
        approver_id: str,
        approver_name: str,
        approved: bool,
        comment: Optional[str] = None
    ) -> Tuple[bool, str]:
        """Approve or deny a break-glass request"""
        import uuid
        
        request = self.db.query(BreakGlassRequest).get(request_id)
        if not request:
            return False, "Request not found"
        
        if request.status != 'pending':
            return False, f"Request is {request.status}"
        
        if request.is_expired():
            request.status = 'expired'
            self.db.commit()
            return False, "Request has expired"
        
        # Check if already approved by this user
        existing = self.db.query(BreakGlassApproval).filter(
            BreakGlassApproval.request_id == request_id,
            BreakGlassApproval.approver_id == approver_id
        ).first()
        
        if existing:
            return False, "Already voted on this request"
        
        # Record approval
        approval = BreakGlassApproval(
            id=str(uuid.uuid4()),
            request_id=request_id,
            approver_id=approver_id,
            approver_name=approver_name,
            approved=approved,
            comment=comment
        )
        self.db.add(approval)
        
        if approved:
            request.current_approvals += 1
            
            # Check if M-of-N threshold reached
            if request.current_approvals >= request.required_approvals:
                # Grant emergency access
                token = self._generate_emergency_token()
                request.status = 'active'
                request.temporary_token = hashlib.sha512(token.encode()).hexdigest()
                request.granted_at = datetime.now(timezone.utc)
                request.token_expires_at = datetime.now(timezone.utc) + timedelta(hours=4)
                
                self.db.commit()
                return True, f"Emergency access granted. Token valid for 4 hours."
        
        self.db.commit()
        
        if not approved:
            return True, "Request denied"
        return True, f"Approval recorded. {request.required_approvals - request.current_approvals} more needed."
    
    def validate_emergency_token(self, token: str) -> Optional[BreakGlassRequest]:
        """Validate emergency access token"""
        token_hash = hashlib.sha512(token.encode()).hexdigest()
        
        request = self.db.query(BreakGlassRequest).filter(
            BreakGlassRequest.temporary_token == token_hash,
            BreakGlassRequest.status == 'active'
        ).first()
        
        if request and request.is_token_valid():
            return request
        return None
    
    def revoke_emergency_access(self, request_id: str) -> bool:
        """Revoke emergency access"""
        request = self.db.query(BreakGlassRequest).get(request_id)
        if not request:
            return False
        
        request.status = 'revoked'
        request.revoked_at = datetime.now(timezone.utc)
        self.db.commit()
        return True
    
    def log_action(self, request_id: str, action: str, details: Dict[str, Any]) -> bool:
        """Log action taken with emergency access"""
        request = self.db.query(BreakGlassRequest).get(request_id)
        if not request:
            return False
        
        import json
        
        usage_log = json.loads(request.usage_log) if request.usage_log else []
        usage_log.append({
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'action': action,
            'details': details
        })
        request.usage_log = json.dumps(usage_log)
        self.db.commit()
        return True
    
    def get_request_status(self, request_id: str) -> Optional[Dict[str, Any]]:
        """Get detailed status of a break-glass request"""
        request = self.db.query(BreakGlassRequest).get(request_id)
        if not request:
            return None
        
        approvals = self.db.query(BreakGlassApproval).filter(
            BreakGlassApproval.request_id == request_id
        ).all()
        
        return {
            'id': request.id,
            'requester': request.requester_name,
            'reason': request.reason,
            'role': request.requested_role,
            'status': request.status,
            'required_approvals': request.required_approvals,
            'current_approvals': request.current_approvals,
            'created_at': request.created_at.isoformat(),
            'expires_at': request.expires_at.isoformat(),
            'granted_at': request.granted_at.isoformat() if request.granted_at else None,
            'approvals': [
                {
                    'approver': a.approver_name,
                    'approved': a.approved,
                    'comment': a.comment,
                    'timestamp': a.approved_at.isoformat()
                }
                for a in approvals
            ]
        }
    
    def _generate_emergency_token(self) -> str:
        """Generate secure emergency access token"""
        return secrets.token_urlsafe(64)
    
    def _notify_approvers(self, request: BreakGlassRequest, approver_ids: List[str]):
        """Send notifications to approvers (placeholder)"""
        # In production, integrate with notification service
        pass


def get_break_glass_service():
    """Get break-glass service instance"""
    return BreakGlassService()
