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
9. **Use versioning** - Upload new versions rather than deleting and re-uploading to preserve history
10. **Compare before approving** - Use document comparison to verify changes between versions
11. **Export to Obsidian** - Keep a local copy of the wiki for offline reference
12. **Use chat sessions** - Have multi-turn conversations scoped to specific documents for focused research

---

## Document Versioning

Versioning lets you upload updated versions of a document while preserving its full history.

### Uploading a New Version

```
POST /api/documents/{id}/versions
Content-Type: multipart/form-data
File: updated-document.pdf
changelog: "Updated compliance section for Q1 2024"
```

Each version is independently encrypted with its own encryption key, so older versions remain accessible even if they were encrypted with different keys.

### Viewing Version History

```
GET /api/documents/{id}/versions
```

Returns all versions ordered by version number (newest first), including:
- Version number
- File size and type
- Who uploaded it
- Changelog description
- Timestamp

### Reverting to an Older Version

If a new version has issues, you can revert to any previous version:

```
POST /api/documents/{id}/versions/{version_uuid}/revert
```

This updates the document to point to the selected version. The reverted-from version is not deleted.

---

## Document Comparison

Compare two documents or two versions of the same document to see what changed.

### Comparing Two Documents

```
GET /api/documents/compare?doc_a=1&doc_b=2
```

Returns:
- **Metadata comparison** - Shows which fields differ (filename, size, type, status, etc.)
- **Content diff** - If both documents have markdown content, shows a unified diff with additions/deletions counts and a similarity ratio (0 to 1)

### HTML Visual Comparison

For a visual side-by-side view:
```
GET /api/documents/compare/html?doc_a=1&doc_b=2
```

Opens an HTML page with highlighted additions (green) and deletions (red).

### Comparing Versions

```
GET /api/documents/{id}/versions/diff?version_a=1&version_b=2
```

Shows the content differences between two versions of the same document.

---

## Document Preview

View a quick preview of documents without downloading them.

```
GET /api/documents/{id}/preview
```

The preview system supports:
- **PDF documents** - Generates a PNG thumbnail of the first page
- **Markdown documents** - Renders as HTML
- **Images** - Generates a resized thumbnail

Previews are cached on first access and served instantly on subsequent requests.

### Preview Metadata

Check if a preview exists and its type:
```
GET /api/documents/{id}/preview/metadata
```

---

## Persistent Chat Sessions

EDMS provides persistent chat sessions that maintain context across multiple exchanges.

### Creating a Chat Session

```
POST /api/chat/sessions
{
  "title": "Budget Discussion",
  "scope_type": "document",
  "scope_id": 5
}
```

Scope types:
- `global` - Chat across all documents
- `document` - Chat focused on a specific document
- `group` - Chat focused on documents in a group

### Having a Conversation

```
POST /api/chat/sessions/{session_id}/messages
{"message": "What are the main budget allocations?"}
```

The AI responds with context from the relevant documents, citing sources. The conversation history (up to 20 messages) provides context for follow-up questions.

### Exporting Conversations

Export a chat session as a markdown document for sharing:

```
GET /api/chat/sessions/{session_id}/export?format=markdown
```

### Managing Sessions

- **List sessions**: `GET /api/chat/sessions`
- **View messages**: `GET /api/chat/sessions/{id}/messages`
- **Delete session**: `DELETE /api/chat/sessions/{id}`

---

## Obsidian Vault Export

Export the EDMS wiki as an Obsidian vault for local, offline access.

### Full Export

```
GET /api/wiki/export/obsidian
```

Downloads a ZIP file containing:
- All wiki pages converted to Obsidian-compatible markdown
- [[wikilinks]] connecting related pages
- YAML frontmatter with tags and metadata
- Dataview-compatible properties for advanced queries

### Incremental Sync

After initial export, sync only changes:

```
GET /api/wiki/export/obsidian/sync?since=2024-01-14T00:00:00
```

Returns the list of pages modified since the given timestamp.

---

## Security Dashboard

The security dashboard provides visibility into system health and threats.

### Real-time Notifications

Connect to receive instant notifications via WebSocket:
- Document processing status changes
- Lifecycle alerts (expiry/review approaching)
- Security alerts (ransomware detection)
- Backup job status

### Notification Management

- **View notifications**: `GET /api/notifications`
- **Mark as read**: `POST /api/notifications/{id}/read`
- **Mark all read**: `POST /api/notifications/read-all`
- **Check unread count**: `GET /api/notifications/unread-count`

### Health Dashboard

Administrators can view the health dashboard at `/settings/health` to see:
- Documents with expired lifecycles
- Lifecycles assigned to deactivated reviewers
- Empty groups with no documents
- Documents stuck in processing
