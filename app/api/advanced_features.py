"""
API endpoints for advanced production features:
- Document forensics and timeline
- Local AI assistant
- QR code bridge
- Break-glass emergency access
"""

from fastapi import APIRouter, Depends, HTTPException, status, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
import json

from app.core.security import get_current_user
from app.models.user import User
from app.services.forensics import DocumentTimeline, add_forensic_relationship
from app.services.local_ai import get_local_ai
from app.services.qr_bridge import get_qr_service
from app.services.break_glass import get_break_glass_service
from app.core.database import get_db

router = APIRouter()


# ==================== Document Forensics ====================

@router.get("/api/forensics/document/{document_id}/timeline")
async def get_document_timeline(
    document_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get complete forensic timeline for a document"""
    try:
        timeline_service = DocumentTimeline(db)
        timeline = timeline_service.get_document_timeline(document_id)
        
        return {
            "document_id": document_id,
            "timeline": timeline,
            "entries_count": len(timeline)
        }
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/api/forensics/document/{document_id}/verify")
async def verify_chain_integrity(
    document_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Verify cryptographic chain integrity for a document"""
    try:
        timeline_service = DocumentTimeline(db)
        result = timeline_service.verify_chain_integrity(document_id)
        
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/forensics/document/{document_id}/worm-lock")
async def enable_worm_lock(
    document_id: str,
    entry_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Enable WORM (Write Once Read Many) lock on a ledger entry"""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        timeline_service = DocumentTimeline(db)
        success = timeline_service.enable_worm_lock(entry_id)
        
        if success:
            return {"message": "WORM lock enabled", "entry_id": entry_id}
        else:
            raise HTTPException(status_code=404, detail="Entry not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==================== Local AI Assistant ====================

@router.post("/api/local-ai/summarize")
async def summarize_document(
    text: str,
    max_length: int = 500,
    current_user: User = Depends(get_current_user)
):
    """Summarize document text using local AI"""
    try:
        ai = get_local_ai()
        summary = ai.summarize(text, max_length)
        
        return {
            "summary": summary,
            "original_length": len(text),
            "summary_length": len(summary)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/local-ai/extract-entities")
async def extract_entities(
    text: str,
    current_user: User = Depends(get_current_user)
):
    """Extract entities from text using local AI"""
    try:
        ai = get_local_ai()
        entities = ai.extract_entities(text)
        
        return {"entities": entities}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/local-ai/compare")
async def compare_documents(
    text1: str,
    text2: str,
    current_user: User = Depends(get_current_user)
):
    """Compare two documents using local AI"""
    try:
        ai = get_local_ai()
        comparison = ai.compare_documents(text1, text2)
        
        return comparison
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/local-ai/answer")
async def answer_question(
    context: str,
    question: str,
    current_user: User = Depends(get_current_user)
):
    """Answer question based on document context"""
    try:
        ai = get_local_ai()
        answer = ai.answer_question(context, question)
        
        return {"answer": answer}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/local-ai/status")
async def get_local_ai_status(current_user: User = Depends(get_current_user)):
    """Get local AI model status"""
    try:
        ai = get_local_ai()
        info = ai.get_model_info()
        
        return info
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==================== QR Code Bridge ====================

@router.post("/api/qr/create")
async def create_qr_link(
    location_name: str,
    location_type: str,
    document_id: Optional[str] = None,
    folder_id: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new QR code link for physical-to-digital bridge"""
    try:
        qr_service = get_qr_service()
        base_url = request.base_url
        
        qr_link = qr_service.create_qr_link(
            location_name=location_name,
            location_type=location_type,
            document_id=document_id,
            folder_id=folder_id,
            created_by=current_user.id,
            base_url=str(base_url).rstrip('/')
        )
        
        return {
            "id": qr_link.id,
            "location": qr_link.location_name,
            "type": qr_link.location_type,
            "qr_data": qr_link.qr_data,
            "qr_image": f"data:image/png;base64,{qr_link.qr_image_base64}"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/qr/{qr_id}/scan")
async def scan_qr_code(
    qr_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user)
):
    """Process QR code scan"""
    try:
        qr_service = get_qr_service()
        user_id = current_user.id if current_user else None
        
        result = qr_service.scan_qr(qr_id, user_id)
        
        if not result:
            raise HTTPException(status_code=404, detail="Invalid or inactive QR code")
        
        # Redirect to linked content
        if result['document_id']:
            return {"redirect": f"/documents/{result['document_id']}", "content": result}
        elif result['folder_id']:
            return {"redirect": f"/groups/{result['folder_id']}", "content": result}
        else:
            return {"content": result}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/qr/list")
async def list_qr_links(
    location_type: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List all QR code links"""
    try:
        qr_service = get_qr_service()
        links = qr_service.get_qr_links_for_location(location_type)
        
        return {
            "links": [
                {
                    "id": link.id,
                    "location": link.location_name,
                    "type": link.location_type,
                    "scan_count": link.scan_count,
                    "active": link.active
                }
                for link in links
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/qr/{qr_id}/deactivate")
async def deactivate_qr_link(
    qr_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Deactivate a QR code link"""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        qr_service = get_qr_service()
        success = qr_service.deactivate_qr_link(qr_id)
        
        if success:
            return {"message": "QR link deactivated"}
        else:
            raise HTTPException(status_code=404, detail="QR link not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/qr/export-labels")
async def export_qr_labels(
    qr_ids: List[str],
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Export QR code images for label printing"""
    try:
        qr_service = get_qr_service()
        labels = qr_service.export_qr_labels(qr_ids)
        
        return {
            "labels": labels,
            "count": len(labels)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==================== Break-Glass Emergency Access ====================

@router.post("/api/break-glass/request")
async def create_break_glass_request(
    reason: str,
    requested_role: str = "admin",
    required_approvals: int = 3,
    approvers: Optional[List[str]] = None,
    duration_hours: int = 4,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create emergency access request"""
    try:
        bg_service = get_break_glass_service()
        
        request = bg_service.create_request(
            requester_id=current_user.id,
            requester_name=current_user.full_name,
            reason=reason,
            requested_role=requested_role,
            required_approvals=required_approvals,
            approvers=approvers,
            duration_hours=duration_hours
        )
        
        return {
            "request_id": request.id,
            "status": "pending",
            "required_approvals": required_approvals,
            "expires_at": request.expires_at.isoformat(),
            "message": f"Emergency access request created. Requires {required_approvals} approvals."
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/break-glass/request/{request_id}/approve")
async def approve_break_glass_request(
    request_id: str,
    approved: bool,
    comment: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Approve or deny emergency access request"""
    try:
        bg_service = get_break_glass_service()
        
        success, message = bg_service.approve_request(
            request_id=request_id,
            approver_id=current_user.id,
            approver_name=current_user.full_name,
            approved=approved,
            comment=comment
        )
        
        if success:
            return {"success": True, "message": message}
        else:
            raise HTTPException(status_code=400, detail=message)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/break-glass/request/{request_id}/status")
async def get_break_glass_status(
    request_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get status of emergency access request"""
    try:
        bg_service = get_break_glass_service()
        status_data = bg_service.get_request_status(request_id)
        
        if status_data:
            return status_data
        else:
            raise HTTPException(status_code=404, detail="Request not found")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/break-glass/emergency-login")
async def emergency_login(
    token: str,
    db: Session = Depends(get_db)
):
    """Login with emergency access token"""
    try:
        bg_service = get_break_glass_service()
        request = bg_service.validate_emergency_token(token)
        
        if not request:
            raise HTTPException(status_code=401, detail="Invalid or expired emergency token")
        
        # Log the emergency access
        bg_service.log_action(request.id, "emergency_login", {
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        
        # Return temporary session
        return {
            "access_granted": True,
            "role": request.requested_role,
            "expires_at": request.token_expires_at.isoformat(),
            "warning": "This is emergency access. All actions are logged."
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/break-glass/request/{request_id}/revoke")
async def revoke_break_glass_access(
    request_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Revoke emergency access"""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        bg_service = get_break_glass_service()
        success = bg_service.revoke_emergency_access(request_id)
        
        if success:
            return {"message": "Emergency access revoked"}
        else:
            raise HTTPException(status_code=404, detail="Request not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
