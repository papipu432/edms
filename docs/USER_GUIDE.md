# User Guide

This guide is for end users of the EDMS system. It covers day-to-day tasks like uploading documents, using workflows, and searching content.

## Logging In

### Username and Password

1. Navigate to the EDMS login page
2. Enter your **username** and **password**
3. Click **Login**

If you do not have an account, contact your administrator or use the registration endpoint (if enabled):

```
POST /api/auth/register
```

### LDAP / Active Directory

If your organization uses LDAP:
1. Enter your corporate credentials (same as your network login)
2. EDMS authenticates against the corporate directory
3. Your account is automatically created on first login with default permissions

### Session Duration

- API tokens expire after 30 minutes by default
- Web sessions use secure cookies
- You will need to re-authenticate when your session expires

---

## Dashboard Navigation

EDMS provides both an API interface and a web dashboard:

- **API Docs** - Interactive documentation at `/docs` (Swagger UI)
- **Org Dashboard** - `/org/dashboard` for organizational structure
- **RBAC Management** - `/rbac/roles` for role management
- **LDAP Config** - `/ldap/config` for LDAP administration
- **Security** - `/settings/security` for security monitoring
- **Backup** - `/settings/backup` for backup management
- **Profile** - `/auth/profile` for viewing your profile and permissions

---

## Uploading Documents

### Single File Upload

1. Identify the target group (folder) for your document
2. Upload the file:
   ```
   POST /api/groups/{group_id}/documents
   Content-Type: multipart/form-data
   File: your-document.pdf
   ```
3. The system immediately returns document metadata with status `"processing"`
4. A background task converts, summarizes, and indexes the document
5. Check status until it shows `"processed"`:
   ```
   GET /api/documents/{id}/status
   ```

### Supported File Formats

| Format | Processing |
|--------|-----------|
| PDF | Text extraction via PyMuPDF, OCR for scanned pages |
| DOCX | Text extraction via python-docx |
| Images (PNG, JPG, TIFF) | OCR via Tesseract |
| Plain text | Direct ingestion |

### Bulk Upload

Upload multiple files at once (requires editor or admin role):

```
POST /api/bulk/upload
Files: file1.pdf, file2.docx, file3.txt
Parameters: group_id=1 OR folder_path="Department/Subfolder"
```

If using `folder_path`, the system automatically creates the group if it does not exist.

Results are returned per file, showing which succeeded and which failed:
```json
{
  "results": [
    {"filename": "file1.pdf", "success": true, "document_id": 10},
    {"filename": "file2.docx", "success": true, "document_id": 11},
    {"filename": "file3.txt", "success": false, "error": "File read error"}
  ],
  "total": 3,
  "successful": 2,
  "failed": 1
}
```

---

## Organizing with Groups/Folders

Groups provide a hierarchical folder structure for documents:

### Creating Groups

```
POST /api/groups
{
  "name": "Engineering",
  "description": "Engineering department documents"
}
```

### Nested Groups

Groups support parent-child hierarchy:

```
POST /api/groups
{
  "name": "Reports",
  "description": "Engineering reports",
  "parent_id": 1
}
```

This creates: Engineering / Reports

### Viewing Group Contents

```
GET /api/groups/{group_id}/documents
```

---

## Document Status Tracking

Each document goes through a processing pipeline. Track progress via:

```
GET /api/documents/{id}/status
```

### Status Values

| Status | Meaning |
|--------|---------|
| `uploaded` | File received, queued for processing |
| `processing` | Pipeline is running (conversion, summarization, indexing) |
| `processed` | Successfully processed, searchable, wiki-integrated |
| `failed` | Processing encountered an error |

### After Processing

Once processed, you can:
- **View markdown** - `GET /api/documents/{id}/markdown`
- **Search content** - `POST /api/search`
- **Download** - `GET /api/documents/{id}/download`

---

## Using Workflows

Workflows track the approval status of documents through a series of actions.

### Workflow Actions

| Action | Purpose | Who Can Do It |
|--------|---------|---------------|
| Submit for Review | Send document for review | Editors, Annotators, Admins |
| Approve | Approve the document | Approvers, Admins |
| Reject | Reject the document | Reviewers, Admins |
| Request Changes | Ask author to revise | Reviewers, Admins |
| Sign Off | Final sign-off | Approvers, Admins |

### Submitting for Review

```
POST /api/documents/{id}/workflow/submit_review
{"comment": "Please review the updated policy document"}
```

### Approving a Document

```
POST /api/documents/{id}/workflow/approve
{"comment": "Content verified and approved"}
```

### Viewing Workflow History

See all actions taken on a document:

```
GET /api/documents/{id}/workflow
```

Returns a chronological list of all workflow entries with actor, action, comment, and timestamp.

### Bulk Workflow Actions

Approve or sign off multiple documents at once:

```
POST /api/bulk/approve
{"document_ids": [1, 2, 3], "comment": "Batch approval"}

POST /api/bulk/signoff
{"document_ids": [1, 2, 3], "comment": "Final sign-off"}
```

---

## Document Lifecycle Management

Lifecycle management tracks the validity and review schedule of documents.

### Lifecycle Types

| Type | Behavior |
|------|----------|
| **Permanent** | Document never expires, stays valid indefinitely |
| **Expiring** | Document has a hard expiration date |
| **Recurring** | Document requires periodic re-review |

### Setting Up a Lifecycle

```
POST /api/documents/{id}/lifecycle
{
  "lifecycle_type": "recurring",
  "review_interval_days": 90,
  "assigned_reviewer_id": "reviewer-user-uuid"
}
```

### Lifecycle States

Documents move through these states:

1. **Draft** - Initial state
2. **In Review** - Being reviewed
3. **Approved** - Passed review
4. **Up to Date** - Currently valid and active
5. **Needs Re-Review** - Review interval has passed
6. **Expired** - Document is no longer valid

### Transitioning States

```
POST /api/documents/{id}/lifecycle/transition
{"target_state": "in_review", "comment": "Submitting for quarterly review"}
```

### Viewing Lifecycle History

```
GET /api/documents/{id}/lifecycle/history
```

### Alerts

The system generates alerts when documents are approaching expiry or review dates:

```
GET /api/lifecycle/alerts
```

---

## Using Annotations

Add comments and notes to specific parts of documents.

### Creating an Annotation

```
POST /api/documents/{id}/annotations
{
  "text": "This paragraph contradicts section 3.2",
  "start_offset": 1500,
  "end_offset": 1650
}
```

- `text` - Your annotation content
- `start_offset` / `end_offset` - Character positions in the document (optional)

### Viewing Annotations

```
GET /api/documents/{id}/annotations
```

Returns all annotations for the document, ordered by creation time.

---

## Searching Documents

### Semantic Search

Search by meaning, not just keywords:

```
POST /api/search
{
  "query": "quarterly financial reporting procedures",
  "top_k": 5
}
```

Returns the most relevant document chunks with similarity scores.

### Scoped Search

Search within a specific group:

```
POST /api/search
{
  "query": "deployment checklist",
  "group_id": 3,
  "top_k": 10
}
```

### RAG Chat

Have a conversation about your documents:

```
POST /api/chat
{
  "query": "What are the key steps in the onboarding process?",
  "history": []
}
```

The system retrieves relevant context from your documents and generates an informed answer, citing sources.

---

## Chatting with the Wiki

The LLM Wiki is a knowledge base that grows as documents are ingested.

### Browsing the Wiki

View the wiki index to see all knowledge pages:

```
GET /api/wiki/index
```

Read a specific page:

```
GET /api/wiki/pages/entities/company-name.md
```

### Asking Questions

Ask natural language questions against the wiki:

```
POST /api/wiki/query
{"question": "Who are the key stakeholders mentioned in our documents?"}
```

The system synthesizes answers from multiple wiki pages.

### Wiki Structure

- **entities/** - Pages about people, organizations, technologies
- **topics/** - Pages about concepts and themes
- **summaries/** - One-page summaries per ingested document
- **index.md** - Catalog of all wiki content
- **log.md** - Timeline of wiki operations

---

## Managing Your Profile

View your profile, roles, and permissions:

```
GET /api/auth/me
```

Or visit `/auth/profile` in the web interface.

### What You Can See

- Your username and email
- Your assigned roles (editor, reviewer, approver, etc.)
- Your effective permissions (what you can do)
- Your folder assignments (where you have special access)

### Changing Your Password

Contact your administrator to change your password. If you authenticated via LDAP, password changes must be made in the corporate directory.

---

## Tips and Best Practices

1. **Use descriptive filenames** - The original filename is preserved and displayed in search results
2. **Organize with groups** - Create a logical folder hierarchy before bulk uploading
3. **Check processing status** - Wait for `"processed"` status before searching for document content
4. **Use workflows** - Track document approval status through the workflow system
5. **Set up lifecycles** - For important documents that need periodic review
6. **Add annotations** - Share feedback on documents with your team
7. **Use bulk operations** - Save time when approving or signing off multiple documents
8. **Leverage the wiki** - The more documents you ingest, the more knowledgeable the wiki becomes
