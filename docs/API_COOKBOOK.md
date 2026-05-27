# API Cookbook

Copy-pasteable curl examples for all EDMS API endpoints. All examples assume the server is running at `http://localhost:8000`.

## Authentication

### Register a new user

```bash
curl -X POST http://localhost:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "username": "johndoe",
    "email": "john@example.com",
    "password": "SecurePass123!"
  }'
```

**Response:**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "username": "johndoe",
  "email": "john@example.com",
  "is_active": true,
  "roles": [],
  "created_at": "2024-01-15T10:30:00",
  "updated_at": "2024-01-15T10:30:00"
}
```

### Login (get JWT token)

```bash
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "username": "admin",
    "password": "admin"
  }'
```

**Response:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

### Get current user

```bash
TOKEN="eyJhbGciOiJIUzI1NiIs..."

curl http://localhost:8000/api/auth/me \
  -H "Authorization: Bearer $TOKEN"
```

---

## Groups

### Create a group

```bash
curl -X POST http://localhost:8000/api/groups \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Engineering Docs",
    "description": "Technical documentation for engineering team"
  }'
```

**Response:**
```json
{
  "id": 1,
  "name": "Engineering Docs",
  "description": "Technical documentation for engineering team",
  "parent_id": null,
  "created_at": "2024-01-15T10:30:00",
  "updated_at": "2024-01-15T10:30:00"
}
```

### List all groups

```bash
curl http://localhost:8000/api/groups
```

### Get a specific group

```bash
curl http://localhost:8000/api/groups/1
```

### Update a group

```bash
curl -X PUT http://localhost:8000/api/groups/1 \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Engineering Documentation",
    "description": "Updated description"
  }'
```

### Delete a group

```bash
curl -X DELETE http://localhost:8000/api/groups/1
```

---

## Documents

### Upload a document

```bash
curl -X POST http://localhost:8000/api/groups/1/documents \
  -F "file=@/path/to/document.pdf"
```

**Response:**
```json
{
  "id": 1,
  "group_id": 1,
  "original_filename": "document.pdf",
  "storage_path": "storage/1/document.pdf",
  "encrypted_pdf_path": "storage/1/document_encrypted.pdf",
  "file_type": "application/pdf",
  "file_size": 245780,
  "status": "processing",
  "summary": null,
  "keywords": null,
  "created_at": "2024-01-15T10:30:00",
  "updated_at": "2024-01-15T10:30:00"
}
```

### List all documents

```bash
curl http://localhost:8000/api/documents
```

**Response:**
```json
{
  "documents": [...],
  "total": 5
}
```

### Get a specific document

```bash
curl http://localhost:8000/api/documents/1
```

### Delete a document

```bash
curl -X DELETE http://localhost:8000/api/documents/1
```

### Download a document

```bash
curl http://localhost:8000/api/documents/1/download -o downloaded_file.pdf
```

### Get document processing status

```bash
curl http://localhost:8000/api/documents/1/status
```

**Response:**
```json
{
  "id": 1,
  "status": "processed"
}
```

### Get document markdown content

```bash
curl http://localhost:8000/api/documents/1/markdown
```

Returns plain text markdown content of the processed document.

---

## Bulk Operations

### Bulk upload with group_id

```bash
curl -X POST http://localhost:8000/api/bulk/upload \
  -H "Authorization: Bearer $TOKEN" \
  -F "files=@file1.pdf" \
  -F "files=@file2.docx" \
  -F "files=@file3.txt" \
  -F "group_id=1"
```

### Bulk upload with folder_path (auto-creates group)

```bash
curl -X POST http://localhost:8000/api/bulk/upload \
  -H "Authorization: Bearer $TOKEN" \
  -F "files=@report1.pdf" \
  -F "files=@report2.pdf" \
  -F "folder_path=Engineering/Reports/Q1"
```

**Response:**
```json
{
  "results": [
    {"document_id": 10, "filename": "report1.pdf", "success": true, "error": null},
    {"document_id": 11, "filename": "report2.pdf", "success": true, "error": null}
  ],
  "total": 2,
  "successful": 2,
  "failed": 0
}
```

### Bulk workflow action

```bash
curl -X POST http://localhost:8000/api/bulk/workflow \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "document_ids": [1, 2, 3],
    "action": "submit_review",
    "comment": "Ready for team review"
  }'
```

**Response:**
```json
{
  "results": [
    {"document_id": 1, "success": true, "error": null},
    {"document_id": 2, "success": true, "error": null},
    {"document_id": 3, "success": true, "error": null}
  ],
  "total": 3,
  "successful": 3,
  "failed": 0
}
```

### Bulk approve

```bash
curl -X POST http://localhost:8000/api/bulk/approve \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "document_ids": [1, 2, 3],
    "comment": "Approved after review meeting"
  }'
```

### Bulk sign off

```bash
curl -X POST http://localhost:8000/api/bulk/signoff \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "document_ids": [1, 2, 3],
    "comment": "Final sign-off"
  }'
```

---

## Lifecycle Management

### Create a lifecycle for a document

**Permanent lifecycle:**
```bash
curl -X POST http://localhost:8000/api/documents/1/lifecycle \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "lifecycle_type": "permanent"
  }'
```

**Expiring lifecycle:**
```bash
curl -X POST http://localhost:8000/api/documents/1/lifecycle \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "lifecycle_type": "expiring",
    "expires_at": "2025-12-31T23:59:59"
  }'
```

**Recurring lifecycle:**
```bash
curl -X POST http://localhost:8000/api/documents/1/lifecycle \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "lifecycle_type": "recurring",
    "review_interval_days": 90,
    "assigned_reviewer_id": "user-uuid-here"
  }'
```

**Response:**
```json
{
  "id": 1,
  "document_id": 1,
  "lifecycle_type": "recurring",
  "state": "draft",
  "expires_at": null,
  "review_interval_days": 90,
  "next_review_at": null,
  "last_reviewed_at": null,
  "last_approved_at": null,
  "assigned_reviewer_id": "user-uuid-here",
  "created_at": "2024-01-15T10:30:00",
  "updated_at": "2024-01-15T10:30:00"
}
```

### Get document lifecycle

```bash
curl http://localhost:8000/api/documents/1/lifecycle
```

### Transition lifecycle state

```bash
curl -X POST http://localhost:8000/api/documents/1/lifecycle/transition \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "target_state": "in_review",
    "comment": "Submitting for quarterly review"
  }'
```

### Get lifecycle transition history

```bash
curl http://localhost:8000/api/documents/1/lifecycle/history
```

**Response:**
```json
[
  {
    "id": 1,
    "lifecycle_id": 1,
    "from_state": "draft",
    "to_state": "in_review",
    "transitioned_by": "user-uuid",
    "comment": "Submitting for quarterly review",
    "created_at": "2024-01-15T11:00:00"
  }
]
```

### Get lifecycle alerts

```bash
curl "http://localhost:8000/api/lifecycle/alerts?days_before_expiry=30&days_before_review=14"
```

**Response:**
```json
{
  "alerts": [
    {
      "document_id": 5,
      "document_name": "policy.pdf",
      "lifecycle_id": 3,
      "alert_type": "expiry",
      "days_remaining": 15,
      "expires_at": "2024-02-01T00:00:00",
      "next_review_at": null
    }
  ],
  "total": 1
}
```

### Trigger alert check and email notifications

```bash
curl -X POST http://localhost:8000/api/lifecycle/check-alerts \
  -H "Authorization: Bearer $TOKEN"
```

**Response:**
```json
{
  "alerts_sent": 3
}
```

---

## Workflow

### Submit document for review

```bash
curl -X POST http://localhost:8000/api/documents/1/workflow/submit_review \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"comment": "Please review the updated specifications"}'
```

**Response:**
```json
{
  "id": 1,
  "document_id": 1,
  "user_id": "user-uuid",
  "action": "submit_review",
  "comment": "Please review the updated specifications",
  "created_at": "2024-01-15T10:30:00"
}
```

### Approve a document

```bash
curl -X POST http://localhost:8000/api/documents/1/workflow/approve \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"comment": "Looks good, approved"}'
```

### Reject a document

```bash
curl -X POST http://localhost:8000/api/documents/1/workflow/reject \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"comment": "Needs corrections in section 3"}'
```

### Request changes

```bash
curl -X POST http://localhost:8000/api/documents/1/workflow/request_changes \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"comment": "Please update the figures"}'
```

### Sign off

```bash
curl -X POST http://localhost:8000/api/documents/1/workflow/sign_off \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"comment": "Final sign-off complete"}'
```

### Get workflow history

```bash
curl http://localhost:8000/api/documents/1/workflow
```

---

## Search & Chat

### Semantic search

```bash
curl -X POST http://localhost:8000/api/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "database migration procedures",
    "group_id": null,
    "top_k": 5
  }'
```

**Response:**
```json
{
  "results": [
    {
      "chunk_text": "To perform a database migration...",
      "document_id": 3,
      "document_name": "ops-guide.pdf",
      "score": 0.89
    }
  ]
}
```

### RAG chat

```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "query": "How do I configure backups?",
    "group_id": null,
    "history": []
  }'
```

**Response:**
```json
{
  "answer": "To configure backups in EDMS, you need to...",
  "sources": [
    {
      "document_id": 7,
      "document_name": "admin-guide.pdf",
      "chunk_text": "Backup configuration involves..."
    }
  ]
}
```

---

## Wiki

### Get wiki index

```bash
curl http://localhost:8000/api/wiki/index
```

**Response:**
```json
{
  "content": "# Wiki Index\n...",
  "pages": ["entities/openai.md", "topics/machine-learning.md", "summaries/doc-1.md"]
}
```

### Get a wiki page

```bash
curl http://localhost:8000/api/wiki/pages/entities/openai.md
```

**Response:**
```json
{
  "path": "entities/openai.md",
  "content": "# OpenAI\n\nOpenAI is an AI research company..."
}
```

### Query the wiki

```bash
curl -X POST http://localhost:8000/api/wiki/query \
  -H "Content-Type: application/json" \
  -d '{"question": "What is the main architecture pattern used?"}'
```

**Response:**
```json
{
  "answer": "The system uses a three-layer pipeline architecture...",
  "sources": ["topics/architecture.md"]
}
```

### Lint the wiki

```bash
curl -X POST http://localhost:8000/api/wiki/lint
```

**Response:**
```json
{
  "issues": [
    "Orphaned page: entities/old-entity.md",
    "Broken link in topics/overview.md"
  ]
}
```

### Get wiki log

```bash
curl http://localhost:8000/api/wiki/log
```

---

## Annotations

### Create an annotation

```bash
curl -X POST http://localhost:8000/api/documents/1/annotations \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "This section needs to reference the new policy",
    "start_offset": 150,
    "end_offset": 200
  }'
```

**Response:**
```json
{
  "id": 1,
  "document_id": 1,
  "user_id": "user-uuid",
  "text": "This section needs to reference the new policy",
  "start_offset": 150,
  "end_offset": 200,
  "created_at": "2024-01-15T10:30:00"
}
```

### List annotations for a document

```bash
curl http://localhost:8000/api/documents/1/annotations
```

---

## Users

### List all users (admin only)

```bash
curl http://localhost:8000/api/users \
  -H "Authorization: Bearer $TOKEN"
```

### Get a specific user

```bash
curl http://localhost:8000/api/users/USER_UUID \
  -H "Authorization: Bearer $TOKEN"
```

### Assign a role to a user

```bash
curl -X POST http://localhost:8000/api/users/USER_UUID/roles \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"role_name": "editor"}'
```

### Remove a role from a user

```bash
curl -X DELETE http://localhost:8000/api/users/USER_UUID/roles/editor \
  -H "Authorization: Bearer $TOKEN"
```

### Assign a folder to a user

```bash
curl -X POST http://localhost:8000/api/users/USER_UUID/folders \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "folder_path": "/Engineering/Reports",
    "role_name": "editor"
  }'
```

### List folder assignments

```bash
curl http://localhost:8000/api/users/USER_UUID/folders \
  -H "Authorization: Bearer $TOKEN"
```

### Remove a folder assignment

```bash
curl -X DELETE http://localhost:8000/api/users/USER_UUID/folders/1 \
  -H "Authorization: Bearer $TOKEN"
```

---

## RBAC

### List all roles

```bash
curl http://localhost:8000/rbac/api/roles \
  -H "Authorization: Bearer $TOKEN"
```

### Create a custom role

```bash
curl -X POST http://localhost:8000/rbac/api/roles \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "code": "auditor",
    "name": "Auditor",
    "description": "Can view audit logs and reports"
  }'
```

### Update a role

```bash
curl -X PUT http://localhost:8000/rbac/api/roles/ROLE_ID \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "code": "auditor",
    "name": "Senior Auditor",
    "description": "Updated description"
  }'
```

### Delete a role

```bash
curl -X DELETE http://localhost:8000/rbac/api/roles/ROLE_ID \
  -H "Authorization: Bearer $TOKEN"
```

### List all permissions

```bash
curl http://localhost:8000/rbac/api/permissions \
  -H "Authorization: Bearer $TOKEN"
```

### Create a permission

```bash
curl -X POST http://localhost:8000/rbac/api/permissions \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "resource": "reports",
    "action": "export",
    "description": "Export reports to CSV"
  }'
```

### Assign permission to role

```bash
curl -X POST http://localhost:8000/rbac/api/roles/ROLE_ID/permissions \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"permission_id": "PERMISSION_UUID"}'
```

### Remove permission from role

```bash
curl -X DELETE http://localhost:8000/rbac/api/roles/ROLE_ID/permissions/PERMISSION_ID \
  -H "Authorization: Bearer $TOKEN"
```

---

## Organization Structure

### List unit types

```bash
curl http://localhost:8000/org/api/unit-types \
  -H "Authorization: Bearer $TOKEN"
```

### List org units

```bash
curl http://localhost:8000/org/api/units \
  -H "Authorization: Bearer $TOKEN"
```

### Create an org unit

```bash
curl -X POST http://localhost:8000/org/api/units \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "code": "ENG",
    "name": "Engineering Department",
    "short_name": "Engineering",
    "type_id": "unit-type-uuid",
    "parent_id": null,
    "sort_order": 1
  }'
```

### Get org chart (tree structure)

```bash
curl http://localhost:8000/org/api/chart \
  -H "Authorization: Bearer $TOKEN"
```

### List positions

```bash
curl http://localhost:8000/org/api/positions \
  -H "Authorization: Bearer $TOKEN"
```

### Create a position

```bash
curl -X POST http://localhost:8000/org/api/positions \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "unit_id": "unit-uuid",
    "position_code": "SE",
    "position_name": "Senior Engineer",
    "grade_id": "grade-uuid",
    "is_head": false,
    "max_occupants": 5
  }'
```

### List grades

```bash
curl http://localhost:8000/org/api/grades \
  -H "Authorization: Bearer $TOKEN"
```

### List assignments

```bash
curl http://localhost:8000/org/api/assignments \
  -H "Authorization: Bearer $TOKEN"
```

### Create an assignment

```bash
curl -X POST http://localhost:8000/org/api/assignments \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user-uuid",
    "position_id": "position-uuid",
    "unit_id": "unit-uuid",
    "assignment_type": "primary",
    "is_primary": true
  }'
```

### View org change history

```bash
curl http://localhost:8000/org/api/history \
  -H "Authorization: Bearer $TOKEN"
```

---

## LDAP

### List LDAP configurations

```bash
curl http://localhost:8000/ldap/api/configs \
  -H "Authorization: Bearer $TOKEN"
```

### Create LDAP configuration

```bash
curl -X POST http://localhost:8000/ldap/api/configs \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Corporate AD",
    "server_url": "ldap://ad.company.com",
    "server_port": 389,
    "base_dn": "dc=company,dc=com",
    "bind_dn": "cn=svc-edms,ou=service-accounts,dc=company,dc=com",
    "bind_password": "secret",
    "sync_enabled": true,
    "sync_create_users": true,
    "default_role": "viewer"
  }'
```

### Test LDAP connection

```bash
curl -X POST http://localhost:8000/ldap/api/configs/CONFIG_ID/test \
  -H "Authorization: Bearer $TOKEN"
```

### Trigger LDAP sync

```bash
curl -X POST http://localhost:8000/ldap/api/configs/CONFIG_ID/sync \
  -H "Authorization: Bearer $TOKEN"
```

### View sync logs

```bash
curl http://localhost:8000/ldap/api/configs/CONFIG_ID/logs \
  -H "Authorization: Bearer $TOKEN"
```

### Manage group-role mappings

```bash
# List mappings
curl http://localhost:8000/ldap/api/configs/CONFIG_ID/group-roles \
  -H "Authorization: Bearer $TOKEN"

# Create mapping
curl -X POST http://localhost:8000/ldap/api/configs/CONFIG_ID/group-roles \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "ldap_group_dn": "cn=editors,ou=groups,dc=company,dc=com",
    "role_code": "editor"
  }'

# Delete mapping
curl -X DELETE http://localhost:8000/ldap/api/configs/CONFIG_ID/group-roles/MAPPING_ID \
  -H "Authorization: Bearer $TOKEN"
```

---

## Security Monitoring

### Get security status

```bash
curl http://localhost:8000/api/security/status \
  -H "Authorization: Bearer $TOKEN"
```

### List security alerts

```bash
curl "http://localhost:8000/api/security/alerts?limit=50&offset=0" \
  -H "Authorization: Bearer $TOKEN"
```

### Acknowledge an alert

```bash
curl -X POST http://localhost:8000/api/security/alerts/ALERT_ID/acknowledge \
  -H "Authorization: Bearer $TOKEN"
```

### Start/stop file monitoring

```bash
# Start
curl -X POST http://localhost:8000/api/security/monitor/start \
  -H "Authorization: Bearer $TOKEN"

# Stop
curl -X POST http://localhost:8000/api/security/monitor/stop \
  -H "Authorization: Bearer $TOKEN"
```

### Get/update security config

```bash
# Get config
curl http://localhost:8000/api/security/config \
  -H "Authorization: Bearer $TOKEN"

# Update config
curl -X POST http://localhost:8000/api/security/config \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "threshold_ops_per_sec": 50,
    "window_seconds": 10,
    "monitored_dir": "/data/storage"
  }'
```

---

## Backup Settings

### Get backup configuration

```bash
curl http://localhost:8000/api/settings/backup/config \
  -H "Authorization: Bearer $TOKEN"
```

### Update backup configuration

```bash
curl -X POST http://localhost:8000/api/settings/backup/config \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "minio_primary_endpoint": "minio.company.com:9000",
    "minio_primary_access_key": "minioadmin",
    "minio_primary_secret_key": "minioadmin",
    "minio_primary_bucket": "edms-backup"
  }'
```

### Trigger manual backup

```bash
curl -X POST http://localhost:8000/api/settings/backup/run \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"target": "primary"}'
```

### View backup history

```bash
curl http://localhost:8000/api/settings/backup/history \
  -H "Authorization: Bearer $TOKEN"
```

### Get backup status

```bash
curl http://localhost:8000/api/settings/backup/status \
  -H "Authorization: Bearer $TOKEN"
```

### Update backup schedule

```bash
curl -X POST http://localhost:8000/api/settings/backup/schedule \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "cron_expression": "0 3 * * *",
    "is_active": true
  }'
```

---

## Encryption Settings

### Get encryption status

```bash
curl http://localhost:8000/api/settings/encryption/status \
  -H "Authorization: Bearer $TOKEN"
```

### Initialize encryption (generate KEK with Shamir shares)

```bash
curl -X POST http://localhost:8000/api/settings/encryption/init \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "threshold": 2,
    "num_shares": 3,
    "passphrase": "super-secret-passphrase",
    "share_holders": ["alice", "bob", "charlie"]
  }'
```

**Response:**
```json
{
  "status": "initialized",
  "key_id": "a1b2c3d4e5f6g7h8",
  "threshold": 2,
  "shares": [
    {"index": 1, "holder": "alice", "share_hex": "abcdef1234..."},
    {"index": 2, "holder": "bob", "share_hex": "567890abcd..."},
    {"index": 3, "holder": "charlie", "share_hex": "ef1234567890..."}
  ],
  "message": "Store each share securely with the designated holder. Shares are shown only once."
}
```

### Recover encryption key from shares

```bash
curl -X POST http://localhost:8000/api/settings/encryption/recover \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "shares": [
      {"index": 1, "share_hex": "abcdef1234..."},
      {"index": 2, "share_hex": "567890abcd..."}
    ]
  }'
```

---

## Document Versioning

### Upload a new version

```bash
curl -X POST http://localhost:8000/api/documents/1/versions \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@updated-document.pdf" \
  -F "changelog=Fixed formatting issues in section 3"
```

**Response:**
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "document_id": 1,
  "version_number": 2,
  "storage_path": "versions/1/v2_updated-document.pdf",
  "encrypted_path": "versions/1/v2_updated-document.pdf.enc",
  "file_size": 245780,
  "file_type": "application/pdf",
  "uploader_id": "user-uuid",
  "changelog": "Fixed formatting issues in section 3",
  "created_at": "2024-01-15T10:30:00"
}
```

### List all versions of a document

```bash
curl http://localhost:8000/api/documents/1/versions
```

**Response:**
```json
{
  "versions": [
    {
      "id": "a1b2c3d4-...",
      "document_id": 1,
      "version_number": 2,
      "file_size": 245780,
      "file_type": "application/pdf",
      "uploader_id": "user-uuid",
      "changelog": "Fixed formatting issues in section 3",
      "created_at": "2024-01-15T10:30:00"
    },
    {
      "id": "f7e8d9c0-...",
      "document_id": 1,
      "version_number": 1,
      "file_size": 234500,
      "file_type": "application/pdf",
      "uploader_id": "user-uuid",
      "changelog": null,
      "created_at": "2024-01-14T09:00:00"
    }
  ],
  "total": 2
}
```

### Get a specific version

```bash
curl http://localhost:8000/api/documents/1/versions/VERSION_UUID
```

### Revert to a specific version

```bash
curl -X POST http://localhost:8000/api/documents/1/versions/VERSION_UUID/revert \
  -H "Authorization: Bearer $TOKEN"
```

### Compare two versions

```bash
curl "http://localhost:8000/api/documents/1/versions/compare?version_a=1&version_b=2"
```

**Response:**
```json
{
  "version_a": {
    "version_number": 1,
    "file_size": 234500,
    "file_type": "application/pdf",
    "uploader_id": "user-uuid",
    "created_at": "2024-01-14T09:00:00"
  },
  "version_b": {
    "version_number": 2,
    "file_size": 245780,
    "file_type": "application/pdf",
    "uploader_id": "user-uuid",
    "created_at": "2024-01-15T10:30:00"
  },
  "size_diff": 11280,
  "time_diff_seconds": 91800
}
```

---

## Document Audit Trail

### Get document history

```bash
curl "http://localhost:8000/api/documents/1/history?limit=50&offset=0" \
  -H "Authorization: Bearer $TOKEN"
```

**Response:**
```json
{
  "entries": [
    {
      "id": "uuid-1",
      "document_id": 1,
      "action": "version_create",
      "actor_id": "user-uuid",
      "actor_username": "admin",
      "ip_address": "127.0.0.1",
      "user_agent": "curl/7.68.0",
      "timestamp": "2024-01-15T10:30:00",
      "details_json": {"version_number": 2, "changelog": "Updated section 3"}
    },
    {
      "id": "uuid-2",
      "document_id": 1,
      "action": "upload",
      "actor_id": "user-uuid",
      "actor_username": "admin",
      "ip_address": "127.0.0.1",
      "timestamp": "2024-01-14T09:00:00",
      "details_json": null
    }
  ],
  "total": 2
}
```

### Filter by action type

```bash
curl "http://localhost:8000/api/documents/1/history?action=approve" \
  -H "Authorization: Bearer $TOKEN"
```

### Get system-wide recent activity

```bash
curl "http://localhost:8000/api/audit/recent?limit=50" \
  -H "Authorization: Bearer $TOKEN"
```

---

## Document Preview

### Get a document preview

```bash
# Get the default preview (PNG thumbnail or HTML)
curl http://localhost:8000/api/documents/1/preview \
  -H "Authorization: Bearer $TOKEN" \
  -o preview.png

# Force thumbnail type
curl "http://localhost:8000/api/documents/1/preview?type=thumbnail" \
  -H "Authorization: Bearer $TOKEN" \
  -o thumbnail.png

# Force HTML preview type
curl "http://localhost:8000/api/documents/1/preview?type=html" \
  -H "Authorization: Bearer $TOKEN"
```

### Get preview metadata

```bash
curl http://localhost:8000/api/documents/1/preview/metadata \
  -H "Authorization: Bearer $TOKEN"
```

**Response:**
```json
{
  "document_id": 1,
  "preview_type": "png",
  "file_size": 45230,
  "exists": true
}
```

---

## Document Comparison

### Compare two documents

```bash
curl "http://localhost:8000/api/documents/compare?doc_a=1&doc_b=2" \
  -H "Authorization: Bearer $TOKEN"
```

**Response:**
```json
{
  "metadata": {
    "fields": [
      {"field": "original_filename", "doc_a_value": "policy-v1.pdf", "doc_b_value": "policy-v2.pdf", "differs": true},
      {"field": "file_size", "doc_a_value": 45000, "doc_b_value": 48500, "differs": true},
      {"field": "file_type", "doc_a_value": "application/pdf", "doc_b_value": "application/pdf", "differs": false},
      {"field": "status", "doc_a_value": "processed", "doc_b_value": "processed", "differs": false}
    ]
  },
  "content_diff": {
    "unified_diff": "--- Document A\n+++ Document B\n@@ -1,5 +1,6 @@\n...",
    "additions_count": 12,
    "deletions_count": 3,
    "similarity_ratio": 0.87
  },
  "has_content_diff": true
}
```

### Compare version content (diff)

```bash
curl "http://localhost:8000/api/documents/1/versions/diff?version_a=1&version_b=2" \
  -H "Authorization: Bearer $TOKEN"
```

**Response:**
```json
{
  "unified_diff": "--- Document A\n+++ Document B\n@@ -10,3 +10,5 @@...",
  "additions_count": 5,
  "deletions_count": 2,
  "similarity_ratio": 0.92
}
```

### HTML side-by-side comparison page

```bash
curl "http://localhost:8000/api/documents/compare/html?doc_a=1&doc_b=2" \
  -H "Authorization: Bearer $TOKEN"
```

Returns a full HTML page with a visual side-by-side diff table.

---

## Document Relationships

### Create a relationship

```bash
curl -X POST http://localhost:8000/api/documents/1/relationships \
  -H "Content-Type: application/json" \
  -d '{
    "target_document_id": 2,
    "relationship_type": "references",
    "description": "Section 3 references this policy"
  }'
```

**Response:**
```json
{
  "id": 1,
  "source_document_id": 1,
  "target_document_id": 2,
  "relationship_type": "references",
  "description": "Section 3 references this policy",
  "created_at": "2024-01-15T10:30:00"
}
```

### List document relationships

```bash
curl http://localhost:8000/api/documents/1/relationships
```

### Delete a relationship

```bash
curl -X DELETE http://localhost:8000/api/relationships/1
```

### Get relationship graph

```bash
# Full graph
curl http://localhost:8000/api/relationships/graph

# Filtered by group
curl "http://localhost:8000/api/relationships/graph?group_id=1"
```

**Response:**
```json
{
  "nodes": [
    {"id": 1, "label": "policy.pdf"},
    {"id": 2, "label": "procedures.pdf"}
  ],
  "edges": [
    {"source": 1, "target": 2, "type": "references", "description": "Section 3 references this policy"}
  ]
}
```

### Detect orphaned documents

```bash
curl http://localhost:8000/api/relationships/orphaned
```

### Get transitive dependencies

```bash
curl http://localhost:8000/api/documents/1/dependencies
```

**Response:**
```json
[2, 5, 8]
```

---

## Persistent Chat Sessions

### Create a chat session

```bash
curl -X POST http://localhost:8000/api/chat/sessions \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Architecture Discussion",
    "scope_type": "document",
    "scope_id": 1
  }'
```

**Response:**
```json
{
  "id": "session-uuid",
  "title": "Architecture Discussion",
  "scope_type": "document",
  "scope_id": 1,
  "created_at": "2024-01-15T10:30:00",
  "message_count": 0
}
```

### List chat sessions

```bash
curl http://localhost:8000/api/chat/sessions \
  -H "Authorization: Bearer $TOKEN"
```

### Send a message and get AI response

```bash
curl -X POST http://localhost:8000/api/chat/sessions/SESSION_UUID/messages \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message": "What are the key security requirements?"}'
```

**Response:**
```json
{
  "message": {
    "id": "msg-uuid",
    "role": "assistant",
    "content": "Based on the documents, the key security requirements are...",
    "sources": [{"document_id": 3, "chunk_text": "..."}],
    "created_at": "2024-01-15T10:30:05"
  },
  "session": {
    "id": "session-uuid",
    "title": "Architecture Discussion",
    "scope_type": "document",
    "scope_id": 1,
    "created_at": "2024-01-15T10:30:00",
    "message_count": 2
  }
}
```

### Get session messages

```bash
curl http://localhost:8000/api/chat/sessions/SESSION_UUID/messages \
  -H "Authorization: Bearer $TOKEN"
```

### Export session as markdown

```bash
curl "http://localhost:8000/api/chat/sessions/SESSION_UUID/export?format=markdown" \
  -H "Authorization: Bearer $TOKEN"
```

**Response:**
```json
{
  "format": "markdown",
  "content": "# Architecture Discussion\n\n**User:** What are the key security requirements?\n\n**Assistant:** Based on the documents..."
}
```

### Delete a session

```bash
curl -X DELETE http://localhost:8000/api/chat/sessions/SESSION_UUID \
  -H "Authorization: Bearer $TOKEN"
```

---

## WebSocket Notifications

### Connect to real-time notifications

```javascript
// JavaScript WebSocket client example
const ws = new WebSocket("ws://localhost:8000/ws/notifications?token=YOUR_JWT_TOKEN");

ws.onmessage = (event) => {
  const notification = JSON.parse(event.data);
  console.log(notification.title, notification.message);
};

// Keep-alive ping
setInterval(() => ws.send("ping"), 30000);
```

### List notifications (REST)

```bash
curl "http://localhost:8000/api/notifications?limit=50&offset=0" \
  -H "Authorization: Bearer $TOKEN"
```

**Response:**
```json
[
  {
    "id": "notif-uuid",
    "user_id": "user-uuid",
    "notification_type": "document_status",
    "title": "Document Status: processed",
    "message": "Document 'report.pdf' status changed to 'processed'.",
    "data": {"document_id": "1", "status": "processed"},
    "is_read": false,
    "created_at": "2024-01-15T10:30:00"
  }
]
```

### Mark notification as read

```bash
curl -X POST http://localhost:8000/api/notifications/NOTIF_UUID/read \
  -H "Authorization: Bearer $TOKEN"
```

### Mark all as read

```bash
curl -X POST http://localhost:8000/api/notifications/read-all \
  -H "Authorization: Bearer $TOKEN"
```

### Get unread count

```bash
curl http://localhost:8000/api/notifications/unread-count \
  -H "Authorization: Bearer $TOKEN"
```

**Response:**
```json
{"unread_count": 3}
```

---

## Obsidian Vault Export

### Export full vault as ZIP

```bash
curl http://localhost:8000/api/wiki/export/obsidian \
  -H "Authorization: Bearer $TOKEN" \
  -o obsidian-vault.zip
```

The ZIP contains:
- Markdown files with [[wikilink]] syntax
- YAML frontmatter with Dataview properties
- Folder structure matching the wiki layout

### Incremental sync

```bash
curl "http://localhost:8000/api/wiki/export/obsidian/sync?since=2024-01-14T00:00:00" \
  -H "Authorization: Bearer $TOKEN"
```

**Response:**
```json
{
  "modified_pages": [
    {"path": "entities/openai.md", "modified_at": "2024-01-15T10:30:00"},
    {"path": "topics/architecture.md", "modified_at": "2024-01-15T09:00:00"}
  ]
}
```

### Get a single page in Obsidian format

```bash
curl http://localhost:8000/api/wiki/export/obsidian/page/entities/openai.md \
  -H "Authorization: Bearer $TOKEN"
```

**Response:**
```json
{
  "path": "entities/openai.md",
  "content": "---\ntitle: OpenAI\ntags: [entity, technology]\n---\n\n# OpenAI\n\n..."
}
```

---

## Security Monitoring (Extended)

### Get monitoring layer status

```bash
curl http://localhost:8000/api/security/status \
  -H "Authorization: Bearer $TOKEN"
```

**Response includes:**
```json
{
  "file_integrity": {"tool": "auditd", "status": "configured"},
  "process_monitoring": {"tool": "falco", "status": "configured"},
  "kms_audit": {"tool": "kms_rate_limiter", "status": "configured"},
  "network": {"tool": "suricata", "status": "configured"}
}
```

### Ingest external alert (webhook)

```bash
curl -X POST http://localhost:8000/api/security/alerts \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "source": "falco",
    "severity": "high",
    "message": "Unexpected process spawned in container",
    "details": {"process": "cryptominer", "pid": 12345}
  }'
```

---

## Health Dashboard

### Run a health check

```bash
curl http://localhost:8000/api/health/check \
  -H "Authorization: Bearer $TOKEN"
```

**Response:**
```json
{
  "issues": [
    {
      "issue_type": "expired_lifecycle",
      "severity": "high",
      "document_id": 5,
      "document_name": "old-policy.pdf",
      "detail": "Lifecycle expired on 2024-01-01T00:00:00",
      "recommended_action": "Renew or archive the document lifecycle"
    },
    {
      "issue_type": "empty_group",
      "severity": "low",
      "document_id": null,
      "document_name": null,
      "detail": "Group 'Archive' (id=3) has no documents",
      "recommended_action": "Add documents to the group or remove the empty group"
    }
  ],
  "checked_at": "2024-01-15T10:30:00",
  "summary": {"expired_lifecycle": 1, "empty_group": 1}
}
```

### Send health digest email

```bash
curl -X POST http://localhost:8000/api/health/send-digest \
  -H "Authorization: Bearer $TOKEN"
```

### View HTML dashboard

Navigate to `/settings/health` in the browser (requires admin role).

---

## Tips

- All authenticated endpoints require `Authorization: Bearer <token>` header
- The default admin credentials are `admin`/`admin` (set via `BOOTSTRAP_ADMIN_USERNAME` and `BOOTSTRAP_ADMIN_PASSWORD`)
- JWT tokens expire after `ACCESS_TOKEN_EXPIRE_MINUTES` (default: 30 minutes)
- File uploads use `multipart/form-data` encoding
- Most responses use `application/json` content type
- Error responses follow the format: `{"detail": "Error message"}`
- Use `http://localhost:8000/docs` for interactive Swagger UI documentation
