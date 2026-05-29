# Document Templates Guide

## Overview

The EDMS includes a comprehensive document template system that allows users to generate standardized Word (.docx) and PDF documents from pre-built templates. This feature supports compliance, HR operations, security assessments, and general business documentation.

## Available Templates

### Compliance & Security

#### 1. ISO 27001 Information Security Policy (`iso27001_policy`)
**Description:** Comprehensive ISO/IEC 27001:2022 compliant information security policy template.

**Sections:**
- Document Control
- Purpose
- Scope
- Policy Statements
- Roles and Responsibilities
- Compliance and Enforcement
- Review and Approval

**Required Fields:**
- `organization_name`: Name of the organization
- `policy_name`: Title of the policy document
- `version`: Policy version number
- `owner`: Policy owner (e.g., "CISO")

**Optional Fields:**
- `effective_date`: Date when policy becomes effective
- `prepared_by`: Person who prepared the document
- `reviewed_by`: Person who reviewed the document
- `approved_by`: Person who approved the document
- `next_review`: Next review date

**Example Usage:**
```python
data = {
    "organization_name": "Acme Corp",
    "policy_name": "Information Security Policy",
    "version": "1.0",
    "owner": "CISO",
    "effective_date": "2024-01-01"
}
```

#### 2. ISO 27001 Standard Operating Procedure (`iso27001_sop`)
**Description:** Standard operating procedure template aligned with ISO 27001 requirements.

**Sections:**
- Purpose
- Scope
- Definitions
- Responsibilities
- Procedure Steps
- Related Documents
- Records
- Revision History

**Required Fields:**
- `title`: SOP title
- `sop_id`: SOP identifier (e.g., "SOP-001")
- `department`: Department owning the SOP

#### 3. OWASP Security Checklist (`owasp_checklist`)
**Description:** Security assessment checklist based on OWASP Top 10.

**Sections:**
- A01: Broken Access Control
- A02: Cryptographic Failures
- A03: Injection
- A04: Insecure Design
- A05: Security Misconfiguration
- A06: Vulnerable and Outdated Components
- A07: Identification and Authentication Failures
- A08: Software and Data Integrity Failures
- A09: Security Logging and Monitoring Failures
- A10: Server-Side Request Forgery (SSRF)

**Required Fields:**
- `project_name`: Name of the project being assessed

**Optional Fields:**
- `application_type`: Type of application (e.g., "Web Application", "API")

#### 4. Risk Assessment Report (`risk_assessment`)
**Description:** Comprehensive risk assessment and treatment planning template.

**Sections:**
- Executive Summary
- Scope and Methodology
- Asset Inventory
- Threat Identification
- Risk Analysis
- Risk Treatment Plan
- Recommendations

### Software Development

#### 5. Software Bill of Materials (`sbom`)
**Description:** SPDX/CycloneDX compatible software bill of materials template.

**Sections:**
- Product Information
- Component Inventory
- Known Vulnerabilities
- Dependency Relationships

**Required Fields:**
- `product_name`: Name of the product
- `version`: Product version
- `supplier`: Supplier/organization name

**Optional Fields:**
- `sbom_version`: SBOM format version
- `components`: List of components with name, version, license, supplier, purl

**Example Usage:**
```python
data = {
    "product_name": "EDMS Platform",
    "version": "2.0.0",
    "supplier": "Acme Corp",
    "components": [
        {
            "name": "FastAPI",
            "version": "0.109.0",
            "license": "MIT",
            "supplier": "FastAPI",
            "purl": "pkg:pypi/fastapi@0.109.0"
        }
    ]
}
```

#### 6. Change Request Form (`change_request`)
**Description:** IT change management request and approval form.

**Sections:**
- Change Information
- Justification
- Risk Assessment
- Implementation Plan
- Rollback Plan
- Approval

#### 7. Project Charter (`project_charter`)
**Description:** Project initiation charter with objectives and stakeholder alignment.

**Sections:**
- Project Overview
- Business Case
- Objectives and Success Criteria
- Scope
- Stakeholders
- Timeline and Milestones
- Budget and Resources
- Risks and Assumptions
- Approval

### Human Resources

#### 8. Employee Onboarding Checklist (`hr_onboarding`)
**Description:** Comprehensive new employee onboarding checklist.

**Sections:**
- Employee Information
- Pre-Arrival Tasks
- First Day Checklist
- First Week Goals
- Acknowledgments

**Required Fields:**
- `employee_name`: Full name of the employee
- `position`: Job title/position
- `department`: Department name
- `start_date`: Start date (YYYY-MM-DD)
- `manager`: Manager's name

**Optional Fields:**
- `location`: Office location

#### 9. Employee Offboarding Checklist (`hr_offboarding`)
**Description:** Employee departure and knowledge transfer checklist.

**Sections:**
- Departure Information
- Asset Return Checklist
- Access Revocation
- Knowledge Transfer
- Exit Interview
- Final Approvals

**Required Fields:**
- `employee_name`: Full name of the departing employee
- `position`: Job title/position
- `last_day`: Last working day (YYYY-MM-DD)

**Optional Fields:**
- `reason`: Reason for leaving (e.g., "Voluntary Resignation")
- `rehire_eligible`: Whether eligible for rehire

#### 10. Non-Disclosure Agreement (`nda`)
**Description:** Mutual non-disclosure agreement template.

**Sections:**
- Parties
- Definition of Confidential Information
- Obligations
- Exclusions
- Term
- Return of Information
- Remedies
- General Provisions
- Signatures

### Operations

#### 11. Security Incident Report (`incident_report`)
**Description:** Detailed security incident documentation and analysis template.

**Sections:**
- Incident Details
- Incident Description
- Impact Assessment
- Incident Timeline
- Root Cause Analysis
- Remediation Actions
- Lessons Learned
- Report Approval

**Required Fields:**
- `incident_id`: Unique incident identifier (e.g., "INC-2024-001")
- `severity`: Severity level (Low/Medium/High/Critical)

**Optional Fields:**
- `detected_at`: Detection date/time
- `status`: Current status (Open/Investigating/Contained/Resolved)
- `incident_type`: Type of incident
- `reporter`: Person who reported
- `description`: Detailed description
- `systems_affected`: List of affected systems
- `data_compromised`: Whether data was compromised
- `users_affected`: Number/description of affected users
- `business_impact`: Business impact assessment
- `root_cause`: Root cause analysis
- `actions`: List of remediation actions

#### 12. Meeting Minutes (`meeting_minutes`)
**Description:** Professional meeting minutes template with action items tracking.

**Sections:**
- Meeting Details
- Attendees
- Agenda Items
- Discussion Points
- Action Items
- Next Meeting

## API Usage

### List Available Templates

```bash
curl -X GET "http://localhost:8000/api/templates/list" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

Response:
```json
{
  "templates": [
    {
      "type": "iso27001_policy",
      "name": "Iso27001 Policy",
      "category": "Compliance & Security",
      "formats": ["docx", "pdf"],
      "description": "ISO 27001 Information Security Policy"
    }
  ]
}
```

### List Template Categories

```bash
curl -X GET "http://localhost:8000/api/templates/categories" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Get Template Preview

```bash
curl -X GET "http://localhost:8000/api/templates/preview/iso27001_policy" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Generate Document (DOCX)

```bash
curl -X POST "http://localhost:8000/api/templates/generate/iso27001_policy?format=docx" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "data": {
      "organization_name": "Acme Corp",
      "policy_name": "Information Security Policy",
      "version": "1.0",
      "owner": "CISO"
    },
    "filename_prefix": "Acme_ISMS_Policy_v1"
  }' \
  --output policy.docx
```

### Generate Document (PDF)

```bash
curl -X POST "http://localhost:8000/api/templates/generate/iso27001_policy?format=pdf" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "data": {
      "organization_name": "Acme Corp",
      "policy_name": "Information Security Policy",
      "version": "1.0",
      "owner": "CISO"
    }
  }' \
  --output policy.pdf
```

## UI Integration

The document templates feature is accessible from the EDMS web interface:

1. Navigate to **Documents** → **Templates**
2. Browse templates by category
3. Click on a template to see preview and required fields
4. Fill in the form with your organization's data
5. Choose output format (DOCX or PDF)
6. Click **Generate** to download the document

## Custom Templates

You can create custom templates using the `custom` template type:

```python
data = {
    "title": "Custom Report",
    "sections": [
        {
            "heading": "Executive Summary",
            "content": "This report summarizes..."
        },
        {
            "heading": "Findings",
            "content": "Key findings include..."
        }
    ],
    "tables": [
        {
            "headers": ["Item", "Status", "Owner"],
            "rows": [
                ["Task 1", "Complete", "John"],
                ["Task 2", "In Progress", "Jane"]
            ]
        }
    ]
}
```

## Best Practices

1. **Version Control**: Always include version numbers in policy documents
2. **Review Dates**: Set next review dates for all compliance documents
3. **Approval Workflow**: Route generated documents through approval workflows before finalizing
4. **Document Retention**: Store generated documents in appropriate EDMS folders with retention policies
5. **Access Control**: Restrict template generation to authorized personnel
6. **Audit Trail**: All template generations are logged for audit purposes

## Integration with Workflows

Generated documents can be automatically submitted to workflows:

1. Generate document from template
2. Upload to EDMS document library
3. Initiate review/approval workflow
4. Track document through lifecycle stages
5. Archive upon approval

## Troubleshooting

### Issue: Document generation fails
**Solution:** Verify all required fields are provided in the request data.

### Issue: PDF formatting issues
**Solution:** Some complex templates work better in DOCX format. Use DOCX for editing, then convert to PDF.

### Issue: Missing template
**Solution:** Check template type spelling against the list of available templates.

## Future Enhancements

- Custom template builder UI
- Template versioning and history
- Multi-language template support
- Digital signature integration
- Automated population from EDMS metadata
- Template sharing across organizations
