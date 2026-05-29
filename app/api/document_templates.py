"""
Document Templates API
Endpoints for generating and downloading standardized document templates.
"""

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from typing import Dict, Any, Optional, List
import io

from app.services.document_templates import (
    DocumentTemplateService,
    TemplateType,
    TEMPLATE_CATEGORIES
)
from app.schemas.document_templates import (
    TemplateGenerateRequest,
    TemplateListResponse,
    TemplateCategoryResponse
)

router = APIRouter(prefix="/api/templates", tags=["Document Templates"])
template_service = DocumentTemplateService()


@router.get("/categories", response_model=List[TemplateCategoryResponse])
async def list_template_categories():
    """List all available template categories and their templates."""
    categories = []
    for category_name, template_types in TEMPLATE_CATEGORIES.items():
        templates = []
        for t_type in template_types:
            templates.append({
                "type": t_type,
                "name": t_type.replace("_", " ").title(),
                "formats": ["docx", "pdf"]
            })
        categories.append({
            "category": category_name,
            "templates": templates
        })
    return categories


@router.get("/list", response_model=TemplateListResponse)
async def list_templates(
    category: Optional[str] = Query(None, description="Filter by category")
):
    """List all available templates with optional category filter."""
    templates = []
    
    for cat_name, template_types in TEMPLATE_CATEGORIES.items():
        if category and cat_name != category:
            continue
            
        for t_type in template_types:
            templates.append({
                "type": t_type,
                "name": t_type.replace("_", " ").title(),
                "category": cat_name,
                "formats": ["docx", "pdf"],
                "description": get_template_description(t_type)
            })
    
    return {"templates": templates}


@router.post("/generate/{template_type}")
async def generate_document(
    template_type: str,
    request: TemplateGenerateRequest,
    format: str = Query("docx", description="Output format: docx or pdf")
):
    """Generate a document from template with provided data."""
    
    # Validate template type
    valid_types = [t for cats in TEMPLATE_CATEGORIES.values() for t in cats]
    if template_type not in valid_types and template_type != TemplateType.CUSTOM:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid template type. Valid types: {', '.join(valid_types)}"
        )
    
    # Validate format
    if format not in ["docx", "pdf"]:
        raise HTTPException(
            status_code=400,
            detail="Invalid format. Must be 'docx' or 'pdf'"
        )
    
    try:
        # Generate document
        if format == "docx":
            content = template_service.generate_docx(template_type, request.data)
            media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            extension = "docx"
        else:
            content = template_service.generate_pdf(template_type, request.data)
            media_type = "application/pdf"
            extension = "pdf"
        
        # Create filename
        filename = f"{template_type}.{extension}"
        if hasattr(request, 'filename_prefix') and request.filename_prefix:
            filename = f"{request.filename_prefix}.{extension}"
        
        # Return as downloadable file
        return StreamingResponse(
            io.BytesIO(content),
            media_type=media_type,
            headers={
                "Content-Disposition": f"attachment; filename={filename}"
            }
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error generating document: {str(e)}"
        )


@router.get("/preview/{template_type}")
async def preview_template(template_type: str):
    """Get a preview/description of what the template contains."""
    if template_type == TemplateType.ISO27001_POLICY:
        return {
            "template_type": template_type,
            "name": "ISO 27001 Information Security Policy",
            "description": "Comprehensive ISO/IEC 27001:2022 compliant information security policy template",
            "sections": [
                "Document Control",
                "Purpose",
                "Scope",
                "Policy Statements",
                "Roles and Responsibilities",
                "Compliance and Enforcement",
                "Review and Approval"
            ],
            "required_fields": ["organization_name", "policy_name", "version", "owner"],
            "optional_fields": ["effective_date", "prepared_by", "reviewed_by", "approved_by", "next_review"]
        }
    elif template_type == TemplateType.ISO27001_SOP:
        return {
            "template_type": template_type,
            "name": "ISO 27001 Standard Operating Procedure",
            "description": "Standard operating procedure template aligned with ISO 27001 requirements",
            "sections": [
                "Purpose",
                "Scope",
                "Definitions",
                "Responsibilities",
                "Procedure Steps",
                "Related Documents",
                "Records",
                "Revision History"
            ],
            "required_fields": ["title", "sop_id", "department"],
            "optional_fields": []
        }
    elif template_type == TemplateType.OWASP_CHECKLIST:
        return {
            "template_type": template_type,
            "name": "OWASP Security Checklist",
            "description": "Security assessment checklist based on OWASP Top 10",
            "sections": [
                "A01: Broken Access Control",
                "A02: Cryptographic Failures",
                "A03: Injection",
                "A04: Insecure Design",
                "A05: Security Misconfiguration",
                "A06: Vulnerable and Outdated Components",
                "A07: Identification and Authentication Failures",
                "A08: Software and Data Integrity Failures",
                "A09: Security Logging and Monitoring Failures",
                "A10: Server-Side Request Forgery (SSRF)"
            ],
            "required_fields": ["project_name"],
            "optional_fields": ["application_type"]
        }
    elif template_type == TemplateType.SBOM:
        return {
            "template_type": template_type,
            "name": "Software Bill of Materials (SBOM)",
            "description": "SPDX/CycloneDX compatible software bill of materials template",
            "sections": [
                "Product Information",
                "Component Inventory",
                "Known Vulnerabilities",
                "Dependency Relationships"
            ],
            "required_fields": ["product_name", "version", "supplier"],
            "optional_fields": ["sbom_version", "components"]
        }
    elif template_type == TemplateType.HR_ONBOARDING:
        return {
            "template_type": template_type,
            "name": "Employee Onboarding Checklist",
            "description": "Comprehensive new employee onboarding checklist",
            "sections": [
                "Employee Information",
                "Pre-Arrival Tasks",
                "First Day Checklist",
                "First Week Goals",
                "Acknowledgments"
            ],
            "required_fields": ["employee_name", "position", "department", "start_date", "manager"],
            "optional_fields": ["location"]
        }
    elif template_type == TemplateType.HR_OFFBOARDING:
        return {
            "template_type": template_type,
            "name": "Employee Offboarding Checklist",
            "description": "Employee departure and knowledge transfer checklist",
            "sections": [
                "Departure Information",
                "Asset Return Checklist",
                "Access Revocation",
                "Knowledge Transfer",
                "Exit Interview",
                "Final Approvals"
            ],
            "required_fields": ["employee_name", "position", "last_day"],
            "optional_fields": ["reason", "rehire_eligible"]
        }
    elif template_type == TemplateType.INCIDENT_REPORT:
        return {
            "template_type": template_type,
            "name": "Security Incident Report",
            "description": "Detailed security incident documentation and analysis template",
            "sections": [
                "Incident Details",
                "Incident Description",
                "Impact Assessment",
                "Incident Timeline",
                "Root Cause Analysis",
                "Remediation Actions",
                "Lessons Learned",
                "Report Approval"
            ],
            "required_fields": ["incident_id", "severity"],
            "optional_fields": ["detected_at", "status", "incident_type", "reporter", "description", 
                              "systems_affected", "data_compromised", "users_affected", "business_impact",
                              "root_cause", "actions"]
        }
    elif template_type == TemplateType.CHANGE_REQUEST:
        return {
            "template_type": template_type,
            "name": "Change Request Form",
            "description": "IT change management request and approval form",
            "sections": [
                "Change Information",
                "Justification",
                "Risk Assessment",
                "Implementation Plan",
                "Rollback Plan",
                "Approval"
            ],
            "required_fields": [],
            "optional_fields": ["id", "title", "requester", "change_type", "priority"]
        }
    elif template_type == TemplateType.RISK_ASSESSMENT:
        return {
            "template_type": template_type,
            "name": "Risk Assessment Report",
            "description": "Comprehensive risk assessment and treatment planning template",
            "sections": [
                "Executive Summary",
                "Scope and Methodology",
                "Asset Inventory",
                "Threat Identification",
                "Risk Analysis",
                "Risk Treatment Plan",
                "Recommendations"
            ],
            "required_fields": [],
            "optional_fields": ["title", "assessor", "assessment_date"]
        }
    elif template_type == TemplateType.MEETING_MINUTES:
        return {
            "template_type": template_type,
            "name": "Meeting Minutes",
            "description": "Professional meeting minutes template with action items tracking",
            "sections": [
                "Meeting Details",
                "Attendees",
                "Agenda Items",
                "Discussion Points",
                "Action Items",
                "Next Meeting"
            ],
            "required_fields": [],
            "optional_fields": ["meeting_title", "date", "location", "attendees"]
        }
    elif template_type == TemplateType.PROJECT_CHARTER:
        return {
            "template_type": template_type,
            "name": "Project Charter",
            "description": "Project initiation charter with objectives and stakeholder alignment",
            "sections": [
                "Project Overview",
                "Business Case",
                "Objectives and Success Criteria",
                "Scope",
                "Stakeholders",
                "Timeline and Milestones",
                "Budget and Resources",
                "Risks and Assumptions",
                "Approval"
            ],
            "required_fields": [],
            "optional_fields": ["project_name", "sponsor", "manager"]
        }
    elif template_type == TemplateType.NDA:
        return {
            "template_type": template_type,
            "name": "Non-Disclosure Agreement",
            "description": "Mutual non-disclosure agreement template",
            "sections": [
                "Parties",
                "Definition of Confidential Information",
                "Obligations",
                "Exclusions",
                "Term",
                "Return of Information",
                "Remedies",
                "General Provisions",
                "Signatures"
            ],
            "required_fields": [],
            "optional_fields": ["party1", "party2", "effective_date", "term_years"]
        }
    else:
        raise HTTPException(status_code=404, detail="Template type not found")


def get_template_description(template_type: str) -> str:
    """Get human-readable description for template type."""
    descriptions = {
        TemplateType.ISO27001_POLICY: "ISO 27001 Information Security Policy",
        TemplateType.ISO27001_SOP: "ISO 27001 Standard Operating Procedure",
        TemplateType.OWASP_CHECKLIST: "OWASP Top 10 Security Checklist",
        TemplateType.SBOM: "Software Bill of Materials (SBOM)",
        TemplateType.HR_ONBOARDING: "Employee Onboarding Checklist",
        TemplateType.HR_OFFBOARDING: "Employee Offboarding Checklist",
        TemplateType.INCIDENT_REPORT: "Security Incident Report",
        TemplateType.CHANGE_REQUEST: "Change Request Form",
        TemplateType.RISK_ASSESSMENT: "Risk Assessment Report",
        TemplateType.MEETING_MINUTES: "Meeting Minutes",
        TemplateType.PROJECT_CHARTER: "Project Charter",
        TemplateType.NDA: "Non-Disclosure Agreement",
        TemplateType.CUSTOM: "Custom Document Template"
    }
    return descriptions.get(template_type, template_type)
