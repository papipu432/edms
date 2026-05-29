"""
Document Template Service
Generates Word (.docx) and PDF documents from templates with pre-filled content.
Supports ISO 27001, OWASP, BOM, HR Onboarding, and custom templates.
"""

import io
import os
from datetime import datetime
from typing import Dict, Any, Optional, List
from pathlib import Path

from docx import Document
from docx.shared import Inches, Pt, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.style import WD_STYLE_TYPE
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_CENTER, TA_LEFT

# Import settings properly
try:
    from app.core.config import settings
    BASE_DIR = getattr(settings, 'BASE_DIR', None) or os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
except:
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))


class TemplateType:
    ISO27001_POLICY = "iso27001_policy"
    ISO27001_SOP = "iso27001_sop"
    OWASP_CHECKLIST = "owasp_checklist"
    SBOM = "sbom"  # Software Bill of Materials
    HR_ONBOARDING = "hr_onboarding"
    HR_OFFBOARDING = "hr_offboarding"
    INCIDENT_REPORT = "incident_report"
    CHANGE_REQUEST = "change_request"
    RISK_ASSESSMENT = "risk_assessment"
    MEETING_MINUTES = "meeting_minutes"
    PROJECT_CHARTER = "project_charter"
    NDA = "nda"  # Non-Disclosure Agreement
    CUSTOM = "custom"


TEMPLATE_CATEGORIES = {
    "Compliance & Security": [
        TemplateType.ISO27001_POLICY,
        TemplateType.ISO27001_SOP,
        TemplateType.OWASP_CHECKLIST,
        TemplateType.RISK_ASSESSMENT,
    ],
    "Software Development": [
        TemplateType.SBOM,
        TemplateType.CHANGE_REQUEST,
        TemplateType.PROJECT_CHARTER,
    ],
    "Human Resources": [
        TemplateType.HR_ONBOARDING,
        TemplateType.HR_OFFBOARDING,
        TemplateType.NDA,
    ],
    "Operations": [
        TemplateType.INCIDENT_REPORT,
        TemplateType.MEETING_MINUTES,
    ],
}


class DocumentTemplateService:
    """Service for generating standardized document templates."""
    
    def __init__(self):
        self.template_dir = Path(BASE_DIR) / "templates" / "documents"
        self.template_dir.mkdir(parents=True, exist_ok=True)
    
    def generate_docx(self, template_type: str, data: Dict[str, Any]) -> bytes:
        """Generate a Word document from template."""
        doc = Document()
        
        # Setup styles
        self._setup_styles(doc)
        
        if template_type == TemplateType.ISO27001_POLICY:
            self._generate_iso27001_policy(doc, data)
        elif template_type == TemplateType.ISO27001_SOP:
            self._generate_iso27001_sop(doc, data)
        elif template_type == TemplateType.OWASP_CHECKLIST:
            self._generate_owasp_checklist(doc, data)
        elif template_type == TemplateType.SBOM:
            self._generate_sbom(doc, data)
        elif template_type == TemplateType.HR_ONBOARDING:
            self._generate_hr_onboarding(doc, data)
        elif template_type == TemplateType.HR_OFFBOARDING:
            self._generate_hr_offboarding(doc, data)
        elif template_type == TemplateType.INCIDENT_REPORT:
            self._generate_incident_report(doc, data)
        elif template_type == TemplateType.CHANGE_REQUEST:
            self._generate_change_request(doc, data)
        elif template_type == TemplateType.RISK_ASSESSMENT:
            self._generate_risk_assessment(doc, data)
        elif template_type == TemplateType.MEETING_MINUTES:
            self._generate_meeting_minutes(doc, data)
        elif template_type == TemplateType.PROJECT_CHARTER:
            self._generate_project_charter(doc, data)
        elif template_type == TemplateType.NDA:
            self._generate_nda(doc, data)
        else:
            self._generate_custom(doc, data)
        
        # Save to bytes
        buffer = io.BytesIO()
        doc.save(buffer)
        buffer.seek(0)
        return buffer.getvalue()
    
    def generate_pdf(self, template_type: str, data: Dict[str, Any]) -> bytes:
        """Generate a PDF document from template."""
        buffer = io.BytesIO()
        
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            rightMargin=0.75*inch,
            leftMargin=0.75*inch,
            topMargin=0.75*inch,
            bottomMargin=0.75*inch
        )
        
        elements = []
        styles = getSampleStyleSheet()
        
        # Custom styles
        styles.add(ParagraphStyle(
            name='CustomTitle',
            parent=styles['Heading1'],
            fontSize=24,
            textColor=colors.HexColor('#1a365d'),
            spaceAfter=30,
            alignment=TA_CENTER
        ))
        
        styles.add(ParagraphStyle(
            name='CustomHeading',
            parent=styles['Heading2'],
            fontSize=16,
            textColor=colors.HexColor('#2c5282'),
            spaceBefore=12,
            spaceAfter=6
        ))
        
        if template_type == TemplateType.ISO27001_POLICY:
            elements = self._generate_iso27001_policy_pdf(elements, styles, data)
        elif template_type == TemplateType.ISO27001_SOP:
            elements = self._generate_iso27001_sop_pdf(elements, styles, data)
        elif template_type == TemplateType.OWASP_CHECKLIST:
            elements = self._generate_owasp_checklist_pdf(elements, styles, data)
        elif template_type == TemplateType.SBOM:
            elements = self._generate_sbom_pdf(elements, styles, data)
        elif template_type == TemplateType.HR_ONBOARDING:
            elements = self._generate_hr_onboarding_pdf(elements, styles, data)
        elif template_type == TemplateType.HR_OFFBOARDING:
            elements = self._generate_hr_offboarding_pdf(elements, styles, data)
        elif template_type == TemplateType.INCIDENT_REPORT:
            elements = self._generate_incident_report_pdf(elements, styles, data)
        elif template_type == TemplateType.CHANGE_REQUEST:
            elements = self._generate_change_request_pdf(elements, styles, data)
        elif template_type == TemplateType.RISK_ASSESSMENT:
            elements = self._generate_risk_assessment_pdf(elements, styles, data)
        elif template_type == TemplateType.MEETING_MINUTES:
            elements = self._generate_meeting_minutes_pdf(elements, styles, data)
        elif template_type == TemplateType.PROJECT_CHARTER:
            elements = self._generate_project_charter_pdf(elements, styles, data)
        elif template_type == TemplateType.NDA:
            elements = self._generate_nda_pdf(elements, styles, data)
        else:
            elements = self._generate_custom_pdf(elements, styles, data)
        
        doc.build(elements)
        buffer.seek(0)
        return buffer.getvalue()
    
    def _setup_styles(self, doc: Document):
        """Setup default styles for Word document."""
        # Title style
        if 'Title' in doc.styles:
            title_style = doc.styles['Title']
            title_font = title_style.font
            title_font.size = Pt(24)
            title_font.bold = True
            title_font.color.rgb = None  # Default color
        
        # Heading 1 style
        if 'Heading 1' in doc.styles:
            h1_style = doc.styles['Heading 1']
            h1_font = h1_style.font
            h1_font.size = Pt(16)
            h1_font.bold = True
    
    def _add_header(self, doc: Document, title: str, subtitle: str = ""):
        """Add document header."""
        title_para = doc.add_heading(title, level=1)
        title_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        
        if subtitle:
            subtitle_para = doc.add_paragraph(subtitle)
            subtitle_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
            subtitle_para.runs[0].italic = True
        
        doc.add_paragraph()  # Spacer
    
    def _add_section(self, doc: Document, heading: str, content: str = ""):
        """Add a section with heading and optional content."""
        doc.add_heading(heading, level=2)
        if content:
            doc.add_paragraph(content)
    
    def _add_table(self, doc: Document, headers: List[str], rows: List[List[str]]):
        """Add a table to the document."""
        table = doc.add_table(rows=1, cols=len(headers))
        table.style = 'Table Grid'
        
        # Header row
        header_cells = table.rows[0].cells
        for i, header in enumerate(headers):
            header_cells[i].text = header
            header_cells[i].paragraphs[0].runs[0].bold = True
        
        # Data rows
        for row_data in rows:
            row = table.add_row()
            for i, cell_data in enumerate(row_data):
                row.cells[i].text = str(cell_data)
        
        doc.add_paragraph()  # Spacer
    
    # ==================== ISO 27001 Templates ====================
    
    def _generate_iso27001_policy(self, doc: Document, data: Dict[str, Any]):
        """Generate ISO 27001 Policy document."""
        org_name = data.get('organization_name', 'Organization Name')
        policy_name = data.get('policy_name', 'Information Security Policy')
        version = data.get('version', '1.0')
        effective_date = data.get('effective_date', datetime.now().strftime('%Y-%m-%d'))
        owner = data.get('owner', 'CISO')
        
        self._add_header(doc, policy_name, f"ISO/IEC 27001:2022 Compliant")
        
        # Document Control
        self._add_section(doc, "1. Document Control")
        control_data = [
            ["Version", version],
            ["Effective Date", effective_date],
            ["Owner", owner],
            ["Classification", "Internal"],
            ["Review Cycle", "Annual"]
        ]
        self._add_table(doc, ["Attribute", "Value"], control_data)
        
        # Purpose
        self._add_section(doc, "2. Purpose", 
            f"This policy establishes the information security management framework for {org_name} "
            "in accordance with ISO/IEC 27001:2022 requirements. It defines the roles, responsibilities, "
            "and controls necessary to protect information assets.")
        
        # Scope
        self._add_section(doc, "3. Scope",
            "This policy applies to all employees, contractors, consultants, temporary staff, "
            "and third parties who have access to organizational information assets.")
        
        # Policy Statements
        self._add_section(doc, "4. Policy Statements")
        policies = [
            "4.1 Information Security Objectives shall be established and measured annually",
            "4.2 Risk assessments shall be conducted at least annually or when significant changes occur",
            "4.3 All personnel must complete information security awareness training",
            "4.4 Access to information assets shall be granted based on least privilege principle",
            "4.5 Incident management procedures shall be maintained and tested",
            "4.6 Business continuity plans shall be documented and reviewed annually",
            "4.7 Supplier relationships shall include security requirements",
            "4.8 Compliance with legal and regulatory requirements shall be maintained"
        ]
        for policy in policies:
            doc.add_paragraph(policy, style='List Bullet')
        
        # Roles and Responsibilities
        self._add_section(doc, "5. Roles and Responsibilities")
        roles_data = [
            ["Board of Directors", "Ultimate accountability for ISMS"],
            ["CISO", "Day-to-day ISMS management and implementation"],
            ["Department Heads", "Ensure compliance within their areas"],
            ["All Personnel", "Follow security policies and report incidents"],
            ["IT Security Team", "Implement technical controls and monitoring"]
        ]
        self._add_table(doc, ["Role", "Responsibility"], roles_data)
        
        # Compliance
        self._add_section(doc, "6. Compliance and Enforcement",
            "Non-compliance with this policy may result in disciplinary action up to and including "
            "termination of employment or contractual relationship. Violations may also result in "
            "legal action where applicable.")
        
        # Review and Approval
        self._add_section(doc, "7. Review and Approval")
        approval_data = [
            ["Prepared By", data.get('prepared_by', 'Security Team')],
            ["Reviewed By", data.get('reviewed_by', 'Legal & Compliance')],
            ["Approved By", data.get('approved_by', 'CEO/CISO')],
            ["Next Review Date", data.get('next_review', '2025-12-31')]
        ]
        self._add_table(doc, ["Role", "Name/Date"], approval_data)
    
    def _generate_iso27001_sop(self, doc: Document, data: Dict[str, Any]):
        """Generate ISO 27001 Standard Operating Procedure."""
        sop_title = data.get('title', 'Standard Operating Procedure')
        sop_id = data.get('sop_id', 'SOP-001')
        department = data.get('department', 'IT Security')
        
        self._add_header(doc, sop_title, f"SOP ID: {sop_id}")
        
        sections = [
            ("1. Purpose", "Define the purpose and objectives of this procedure."),
            ("2. Scope", "Specify the scope and applicability of this procedure."),
            ("3. Definitions", "List key terms and definitions used in this procedure."),
            ("4. Responsibilities", "Detail roles and responsibilities for executing this procedure."),
            ("5. Procedure Steps", "Provide step-by-step instructions for execution."),
            ("6. Related Documents", "List related policies, procedures, and forms."),
            ("7. Records", "Specify records to be maintained and retention periods."),
            ("8. Revision History", "Track changes and revisions to this procedure.")
        ]
        
        for heading, content in sections:
            self._add_section(doc, heading, content)
        
        # Procedure Steps Table
        self._add_section(doc, "5.1 Detailed Procedure Steps")
        steps_data = [
            ["Step", "Action", "Responsible Role", "Frequency", "Evidence"],
            ["1", "Initiate process", "Role A", "As needed", "Form A"],
            ["2", "Review and approve", "Role B", "Within 2 days", "Approval record"],
            ["3", "Execute control", "Role C", "Per schedule", "Log entry"],
            ["4", "Verify completion", "Role D", "After execution", "Verification report"],
            ["5", "Document results", "Role A", "Within 1 day", "Final report"]
        ]
        self._add_table(doc, steps_data[0], steps_data[1:])
    
    # ==================== OWASP Templates ====================
    
    def _generate_owasp_checklist(self, doc: Document, data: Dict[str, Any]):
        """Generate OWASP Security Checklist."""
        project_name = data.get('project_name', 'Project Name')
        application_type = data.get('application_type', 'Web Application')
        
        self._add_header(doc, "OWASP Security Checklist", f"Project: {project_name}")
        
        doc.add_paragraph(f"Application Type: {application_type}")
        doc.add_paragraph(f"Assessment Date: {datetime.now().strftime('%Y-%m-%d')}")
        doc.add_paragraph()
        
        # OWASP Top 10 Categories
        categories = [
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
        ]
        
        for category in categories:
            self._add_section(doc, category)
            
            # Sample checks for each category
            checks = [
                f"✓ Verify access control enforcement",
                f"✓ Implement proper authentication mechanisms",
                f"✓ Validate and sanitize all inputs",
                f"✓ Configure security headers",
                f"✓ Keep dependencies updated",
                f"✓ Implement logging and monitoring"
            ]
            
            for check in checks:
                para = doc.add_paragraph(check)
                para.style = 'List Bullet'
            
            doc.add_paragraph("Status: ☐ Pass  ☐ Fail  ☐ N/A")
            doc.add_paragraph("Notes: _________________________________________________")
            doc.add_paragraph()
    
    # ==================== SBOM Template ====================
    
    def _generate_sbom(self, doc: Document, data: Dict[str, Any]):
        """Generate Software Bill of Materials (SBOM)."""
        product_name = data.get('product_name', 'Product Name')
        version = data.get('version', '1.0.0')
        supplier = data.get('supplier', 'Organization Name')
        
        self._add_header(doc, "Software Bill of Materials (SBOM)", f"Product: {product_name} v{version}")
        
        # Metadata
        self._add_section(doc, "1. Product Information")
        meta_data = [
            ["Product Name", product_name],
            ["Version", version],
            ["Supplier", supplier],
            ["Generation Date", datetime.now().strftime('%Y-%m-%d %H:%M:%S')],
            ["SBOM Format", "SPDX 2.3 / CycloneDX"],
            ["SBOM Version", data.get('sbom_version', '1.0')]
        ]
        self._add_table(doc, ["Attribute", "Value"], meta_data)
        
        # Components Table
        self._add_section(doc, "2. Component Inventory")
        components = data.get('components', [
            {"name": "Example Library", "version": "1.2.3", "license": "MIT", "supplier": "Example Corp"},
            {"name": "Another Package", "version": "4.5.6", "license": "Apache-2.0", "supplier": "Another Inc"}
        ])
        
        headers = ["Component Name", "Version", "License", "Supplier", "PURL/CPE"]
        rows = [[c.get('name', ''), c.get('version', ''), c.get('license', ''), 
                 c.get('supplier', ''), c.get('purl', '')] for c in components]
        self._add_table(doc, headers, rows)
        
        # Vulnerabilities
        self._add_section(doc, "3. Known Vulnerabilities")
        vuln_data = [
            ["Component", "CVE ID", "Severity", "Status", "Remediation"],
            ["Example Library", "CVE-2023-XXXX", "High", "Patched", "Upgrade to 1.2.4"],
            ["No known vulnerabilities", "-", "-", "-", "-"]
        ]
        self._add_table(doc, vuln_data[0], vuln_data[1:])
        
        # Dependencies
        self._add_section(doc, "4. Dependency Relationships")
        doc.add_paragraph("This section documents the dependency tree and relationships between components.")
    
    # ==================== HR Templates ====================
    
    def _generate_hr_onboarding(self, doc: Document, data: Dict[str, Any]):
        """Generate HR Onboarding Checklist."""
        employee_name = data.get('employee_name', 'Employee Name')
        position = data.get('position', 'Position Title')
        department = data.get('department', 'Department')
        start_date = data.get('start_date', datetime.now().strftime('%Y-%m-%d'))
        manager = data.get('manager', 'Manager Name')
        
        self._add_header(doc, "Employee Onboarding Checklist", f"Welcome: {employee_name}")
        
        # Employee Info
        self._add_section(doc, "1. Employee Information")
        emp_data = [
            ["Full Name", employee_name],
            ["Position", position],
            ["Department", department],
            ["Start Date", start_date],
            ["Manager", manager],
            ["Location", data.get('location', 'Office Location')]
        ]
        self._add_table(doc, ["Attribute", "Details"], emp_data)
        
        # Pre-Arrival Tasks
        self._add_section(doc, "2. Pre-Arrival Tasks")
        pre_arrival = [
            "☐ Prepare workspace and equipment",
            "☐ Create email account and system access",
            "☐ Order business cards (if applicable)",
            "☐ Schedule orientation meetings",
            "☐ Prepare welcome package",
            "☐ Assign buddy/mentor"
        ]
        for task in pre_arrival:
            doc.add_paragraph(task, style='List Bullet')
        
        # Day 1 Tasks
        self._add_section(doc, "3. First Day Checklist")
        day1 = [
            "☐ Welcome and office tour",
            "☐ Complete HR paperwork",
            "☐ Review company policies",
            "☐ Set up workstation",
            "☐ Meet team members",
            "☐ Lunch with manager/team",
            "☐ Review job expectations"
        ]
        for task in day1:
            doc.add_paragraph(task, style='List Bullet')
        
        # First Week Tasks
        self._add_section(doc, "4. First Week Goals")
        week1 = [
            "☐ Complete mandatory training",
            "☐ Review department procedures",
            "☐ Set up 30-60-90 day goals",
            "☐ Attend team meetings",
            "☐ Complete IT security training",
            "☐ Schedule follow-up meetings"
        ]
        for task in week1:
            doc.add_paragraph(task, style='List Bullet')
        
        # Signatures
        self._add_section(doc, "5. Acknowledgments")
        sig_data = [
            ["Employee", "___________________ Date: _______"],
            ["Manager", "___________________ Date: _______"],
            ["HR Representative", "___________________ Date: _______"]
        ]
        self._add_table(doc, ["Role", "Signature"], sig_data)
    
    def _generate_hr_offboarding(self, doc: Document, data: Dict[str, Any]):
        """Generate HR Offboarding Checklist."""
        employee_name = data.get('employee_name', 'Employee Name')
        position = data.get('position', 'Position Title')
        last_day = data.get('last_day', datetime.now().strftime('%Y-%m-%d'))
        reason = data.get('reason', 'Voluntary Resignation')
        
        self._add_header(doc, "Employee Offboarding Checklist", f"Departing: {employee_name}")
        
        # Employee Info
        self._add_section(doc, "1. Departure Information")
        emp_data = [
            ["Full Name", employee_name],
            ["Position", position],
            ["Last Working Day", last_day],
            ["Reason for Leaving", reason],
            ["Eligible for Rehire", data.get('rehire_eligible', 'To Be Determined')]
        ]
        self._add_table(doc, ["Attribute", "Details"], emp_data)
        
        # Asset Return
        self._add_section(doc, "2. Asset Return Checklist")
        assets = [
            "☐ Laptop/Computer",
            "☐ Mobile phone/SIM card",
            "☐ Access badges/keys",
            "☐ Company credit card",
            "☐ Parking pass/transit card",
            "☐ Uniforms/equipment",
            "☐ Documents/files",
            "☐ Other: _______________"
        ]
        for item in assets:
            doc.add_paragraph(item, style='List Bullet')
        
        # Access Revocation
        self._add_section(doc, "3. Access Revocation")
        access_items = [
            "☐ Email account disabled",
            "☐ Network access revoked",
            "☐ Application access removed",
            "☐ VPN access disabled",
            "☐ Building access deactivated",
            "☐ Shared mailbox ownership transferred",
            "☐ Distribution lists updated"
        ]
        for item in access_items:
            doc.add_paragraph(item, style='List Bullet')
        
        # Knowledge Transfer
        self._add_section(doc, "4. Knowledge Transfer")
        kt_items = [
            "☐ Document current projects status",
            "☐ Transfer file ownership",
            "☐ Update procedure documentation",
            "☐ Brief replacement/colleagues",
            "☐ Export important contacts",
            "☐ Clean up personal files"
        ]
        for item in kt_items:
            doc.add_paragraph(item, style='List Bullet')
        
        # Exit Interview
        self._add_section(doc, "5. Exit Interview")
        doc.add_paragraph("Scheduled Date: _______________")
        doc.add_paragraph("Conducted By: _______________")
        doc.add_paragraph()
        doc.add_paragraph("Key Feedback:")
        doc.add_paragraph("_______________________________________________________")
        doc.add_paragraph("_______________________________________________________")
        
        # Signatures
        self._add_section(doc, "6. Final Approvals")
        sig_data = [
            ["Employee", "___________________ Date: _______"],
            ["Manager", "___________________ Date: _______"],
            ["IT Department", "___________________ Date: _______"],
            ["HR Department", "___________________ Date: _______"]
        ]
        self._add_table(doc, ["Role", "Signature"], sig_data)
    
    # ==================== Incident Report Template ====================
    
    def _generate_incident_report(self, doc: Document, data: Dict[str, Any]):
        """Generate Security Incident Report."""
        incident_id = data.get('incident_id', 'INC-2024-001')
        severity = data.get('severity', 'Medium')
        status = data.get('status', 'Open')
        
        self._add_header(doc, "Security Incident Report", f"Incident ID: {incident_id}")
        
        # Incident Details
        self._add_section(doc, "1. Incident Details")
        details_data = [
            ["Incident ID", incident_id],
            ["Date/Time Detected", data.get('detected_at', datetime.now().strftime('%Y-%m-%d %H:%M'))],
            ["Severity", severity],
            ["Status", status],
            ["Incident Type", data.get('incident_type', 'Security Event')],
            ["Reporter", data.get('reporter', 'Unknown')]
        ]
        self._add_table(doc, ["Attribute", "Value"], details_data)
        
        # Description
        self._add_section(doc, "2. Incident Description")
        doc.add_paragraph(data.get('description', 'Describe the incident in detail...'))
        
        # Impact Assessment
        self._add_section(doc, "3. Impact Assessment")
        impact_data = [
            ["Systems Affected", data.get('systems_affected', 'List affected systems')],
            ["Data Compromised", data.get('data_compromised', 'Yes/No/Unknown')],
            ["Users Affected", data.get('users_affected', 'Number/Description')],
            ["Business Impact", data.get('business_impact', 'Low/Medium/High')]
        ]
        self._add_table(doc, ["Category", "Details"], impact_data)
        
        # Timeline
        self._add_section(doc, "4. Incident Timeline")
        timeline_data = [
            ["Date/Time", "Event", "Action Taken", "Responsible"],
            [data.get('detected_at', ''), 'Incident detected', 'Initial assessment', data.get('reporter', '')],
            ['', 'Escalated', 'Notified response team', 'SOC Analyst'],
            ['', 'Containment initiated', 'Isolated affected systems', 'IR Team'],
            ['', 'Investigation started', 'Forensic analysis', 'IR Team'],
            ['', 'Recovery completed', 'Systems restored', 'IT Operations']
        ]
        self._add_table(doc, timeline_data[0], timeline_data[1:])
        
        # Root Cause
        self._add_section(doc, "5. Root Cause Analysis")
        doc.add_paragraph(data.get('root_cause', 'Describe root cause...'))
        
        # Remediation
        self._add_section(doc, "6. Remediation Actions")
        actions = data.get('actions', [
            "Immediate containment measures",
            "System patches applied",
            "Passwords reset",
            "Monitoring enhanced",
            "User awareness notification sent"
        ])
        for action in actions:
            doc.add_paragraph(f"☐ {action}", style='List Bullet')
        
        # Lessons Learned
        self._add_section(doc, "7. Lessons Learned")
        doc.add_paragraph("What went well:")
        doc.add_paragraph("_______________________________________________________")
        doc.add_paragraph("What could be improved:")
        doc.add_paragraph("_______________________________________________________")
        
        # Approval
        self._add_section(doc, "8. Report Approval")
        approval_data = [
            ["Prepared By", data.get('prepared_by', 'Incident Responder')],
            ["Reviewed By", data.get('reviewed_by', 'Security Manager')],
            ["Approved By", data.get('approved_by', 'CISO')],
            ["Date", datetime.now().strftime('%Y-%m-%d')]
        ]
        self._add_table(doc, ["Role", "Name/Date"], approval_data)
    
    # ==================== Placeholder methods for other templates ====================
    
    def _generate_change_request(self, doc: Document, data: Dict[str, Any]):
        """Generate Change Request document."""
        self._add_header(doc, "Change Request Form", f"CR-{data.get('id', '001')}")
        self._add_section(doc, "1. Change Information")
        self._add_section(doc, "2. Justification")
        self._add_section(doc, "3. Risk Assessment")
        self._add_section(doc, "4. Implementation Plan")
        self._add_section(doc, "5. Rollback Plan")
        self._add_section(doc, "6. Approval")
    
    def _generate_risk_assessment(self, doc: Document, data: Dict[str, Any]):
        """Generate Risk Assessment document."""
        self._add_header(doc, "Risk Assessment Report", data.get('title', 'Risk Assessment'))
        self._add_section(doc, "1. Executive Summary")
        self._add_section(doc, "2. Scope and Methodology")
        self._add_section(doc, "3. Asset Inventory")
        self._add_section(doc, "4. Threat Identification")
        self._add_section(doc, "5. Risk Analysis")
        self._add_section(doc, "6. Risk Treatment Plan")
        self._add_section(doc, "7. Recommendations")
    
    def _generate_meeting_minutes(self, doc: Document, data: Dict[str, Any]):
        """Generate Meeting Minutes document."""
        self._add_header(doc, "Meeting Minutes", data.get('meeting_title', 'Team Meeting'))
        self._add_section(doc, "1. Meeting Details")
        self._add_section(doc, "2. Attendees")
        self._add_section(doc, "3. Agenda Items")
        self._add_section(doc, "4. Discussion Points")
        self._add_section(doc, "5. Action Items")
        self._add_section(doc, "6. Next Meeting")
    
    def _generate_project_charter(self, doc: Document, data: Dict[str, Any]):
        """Generate Project Charter document."""
        self._add_header(doc, "Project Charter", data.get('project_name', 'Project Name'))
        self._add_section(doc, "1. Project Overview")
        self._add_section(doc, "2. Business Case")
        self._add_section(doc, "3. Objectives and Success Criteria")
        self._add_section(doc, "4. Scope")
        self._add_section(doc, "5. Stakeholders")
        self._add_section(doc, "6. Timeline and Milestones")
        self._add_section(doc, "7. Budget and Resources")
        self._add_section(doc, "8. Risks and Assumptions")
        self._add_section(doc, "9. Approval")
    
    def _generate_nda(self, doc: Document, data: Dict[str, Any]):
        """Generate Non-Disclosure Agreement."""
        self._add_header(doc, "Non-Disclosure Agreement", "Confidential")
        self._add_section(doc, "1. Parties")
        self._add_section(doc, "2. Definition of Confidential Information")
        self._add_section(doc, "3. Obligations")
        self._add_section(doc, "4. Exclusions")
        self._add_section(doc, "5. Term")
        self._add_section(doc, "6. Return of Information")
        self._add_section(doc, "7. Remedies")
        self._add_section(doc, "8. General Provisions")
        self._add_section(doc, "9. Signatures")
    
    def _generate_custom(self, doc: Document, data: Dict[str, Any]):
        """Generate custom document from data."""
        title = data.get('title', 'Custom Document')
        self._add_header(doc, title)
        
        for section in data.get('sections', []):
            self._add_section(doc, section.get('heading', 'Section'), section.get('content', ''))
        
        if 'tables' in data:
            for table_data in data['tables']:
                self._add_table(doc, table_data.get('headers', []), table_data.get('rows', []))
    
    # ==================== PDF Generation Methods (Placeholders) ====================
    # For brevity, PDF methods call similar logic but use ReportLab
    
    def _generate_iso27001_policy_pdf(self, elements, styles, data):
        elements.append(Paragraph(f"{data.get('policy_name', 'Policy')}", styles['CustomTitle']))
        elements.append(Spacer(1, 0.25*inch))
        elements.append(Paragraph("ISO/IEC 27001:2022 Compliant", styles['Normal']))
        elements.append(Spacer(1, 0.5*inch))
        elements.append(Paragraph("1. Document Control", styles['CustomHeading']))
        # Add table and more content...
        elements.append(Spacer(1, 0.25*inch))
        return elements
    
    def _generate_iso27001_sop_pdf(self, elements, styles, data):
        elements.append(Paragraph(f"{data.get('title', 'SOP')}", styles['CustomTitle']))
        elements.append(Spacer(1, 0.5*inch))
        return elements
    
    def _generate_owasp_checklist_pdf(self, elements, styles, data):
        elements.append(Paragraph("OWASP Security Checklist", styles['CustomTitle']))
        elements.append(Spacer(1, 0.5*inch))
        return elements
    
    def _generate_sbom_pdf(self, elements, styles, data):
        elements.append(Paragraph("Software Bill of Materials", styles['CustomTitle']))
        elements.append(Spacer(1, 0.5*inch))
        return elements
    
    def _generate_hr_onboarding_pdf(self, elements, styles, data):
        elements.append(Paragraph("Employee Onboarding Checklist", styles['CustomTitle']))
        elements.append(Spacer(1, 0.5*inch))
        return elements
    
    def _generate_hr_offboarding_pdf(self, elements, styles, data):
        elements.append(Paragraph("Employee Offboarding Checklist", styles['CustomTitle']))
        elements.append(Spacer(1, 0.5*inch))
        return elements
    
    def _generate_incident_report_pdf(self, elements, styles, data):
        elements.append(Paragraph("Security Incident Report", styles['CustomTitle']))
        elements.append(Spacer(1, 0.5*inch))
        return elements
    
    def _generate_change_request_pdf(self, elements, styles, data):
        elements.append(Paragraph("Change Request Form", styles['CustomTitle']))
        elements.append(Spacer(1, 0.5*inch))
        return elements
    
    def _generate_risk_assessment_pdf(self, elements, styles, data):
        elements.append(Paragraph("Risk Assessment Report", styles['CustomTitle']))
        elements.append(Spacer(1, 0.5*inch))
        return elements
    
    def _generate_meeting_minutes_pdf(self, elements, styles, data):
        elements.append(Paragraph("Meeting Minutes", styles['CustomTitle']))
        elements.append(Spacer(1, 0.5*inch))
        return elements
    
    def _generate_project_charter_pdf(self, elements, styles, data):
        elements.append(Paragraph("Project Charter", styles['CustomTitle']))
        elements.append(Spacer(1, 0.5*inch))
        return elements
    
    def _generate_nda_pdf(self, elements, styles, data):
        elements.append(Paragraph("Non-Disclosure Agreement", styles['CustomTitle']))
        elements.append(Spacer(1, 0.5*inch))
        return elements
    
    def _generate_custom_pdf(self, elements, styles, data):
        elements.append(Paragraph(data.get('title', 'Custom Document'), styles['CustomTitle']))
        elements.append(Spacer(1, 0.5*inch))
        return elements


# Singleton instance
template_service = DocumentTemplateService()
