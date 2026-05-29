# User Guide

This guide is for end users of the EDMS system. It covers day-to-day tasks like uploading documents, using workflows, and searching content.

## New Features (Latest Release)

### 🎨 Drag-Drop Organizational Chart

**Access**: `/org/chart`

The organizational chart now features:
- **Drag-and-drop reordering** - Move org units by dragging
- **Edit mode toggle** - Safe editing with visual indicators
- **Inline actions** - Add, edit, delete units directly on the chart
- **Visual tree structure** - Clear hierarchy with connectors
- **Real-time refresh** - Updates immediately after changes

**How to Use**:
1. Navigate to `/org/chart`
2. Click "Toggle Edit Mode" to enable editing
3. Drag org units to reorder them
4. Hover over a unit to see action buttons (+ add, ✏️ edit, 🗑️ delete)
5. Click "Save" when done

### 📋 Kanban Workflow Board

**Access**: `/workflow/kanban`

Manage document workflows visually:
- **Drag cards between stages** - Move documents through workflow
- **Flow note editor** - Add notes when moving documents
- **Priority badges** - Visual priority indicators
- **Due date tracking** - See upcoming deadlines
- **Assignment indicators** - Know who's responsible

**How to Use**:
1. Navigate to `/workflow/kanban`
2. Drag a document card from one column to another
3. A confirmation modal appears
4. Select assignee (if needed) and click "Move"
5. Add flow notes in the editor that appears
6. Notes are attached to the workflow history

### ⚡ Auto-Reassignment on User Status Change

When a user's status changes (resigned, terminated, MIA):
- Their pending workflow tasks are automatically reassigned
- Escalation follows org hierarchy: same position → unit head → parent unit → admin
- All reassignments are logged for audit

---

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
13. **Use the command palette** - Press Ctrl+K for quick access to any action
14. **Drag and drop** - Drop files directly on folder cards in the dashboard for fast uploads
15. **Use the Kanban board** - Visualize and manage document lifecycle stages by dragging between columns
16. **Create templates** - Set up document templates for common document types to enforce consistency
17. **Request access** - Use the access request workflow instead of asking admins directly
18. **Use canvas** - Create spatial arrangements of related documents for visual project planning
19. **Check knowledge graph** - Discover hidden connections between documents through the graph view
20. **Natural language search** - Try describing what you want in plain English for smarter results

---

## Using the Command Palette

The command palette provides quick access to any action from anywhere in the interface.

### Opening the Palette

Press **Ctrl+K** (or **Cmd+K** on Mac) to open the command palette.

### Available Actions

Type to search for commands:
- **Navigate** - Jump to any group, document, or settings page
- **Upload** - Quick upload a document
- **Search** - Start a semantic search
- **Create** - Create new groups, templates, or canvases
- **Admin** - Access admin functions (if you have the role)

### Keyboard Navigation

- **Up/Down arrows** - Navigate results
- **Enter** - Execute selected command
- **Escape** - Close the palette

---

## Drag-and-Drop Uploads

Upload documents quickly by dragging files from your file manager.

### Dashboard Upload

1. Navigate to the dashboard view
2. Drag one or more files from your desktop/file manager
3. Drop them on a folder card
4. Files are automatically uploaded to that group
5. Processing starts immediately

### Supported Behaviors

- Drop multiple files at once for batch upload
- Drop on a specific folder card to target that group
- The system shows a visual indicator when hovering over a valid drop target

---

## Using the Kanban Board

The Kanban board provides a visual interface for managing document lifecycles.

### Accessing the Board

Navigate to `/kanban` or use the command palette to search "Kanban".

### Board Layout

Documents are organized into columns by lifecycle state:
- **Draft** - New documents not yet submitted
- **In Review** - Documents awaiting review
- **Approved** - Documents that passed review
- **Up to Date** - Active, valid documents
- **Needs Re-Review** - Documents due for re-review
- **Expired** - Documents past their expiration

### Moving Documents

Drag a document card from one column to another to trigger a lifecycle transition. Only valid transitions are allowed (invalid drops are rejected).

### Filtering

Use the filter controls above the board to:
- Filter by group/folder
- Filter by assigned reviewer
- Show only your documents

---

## Managing Document Templates

Templates define standard configurations for common document types.

### What Templates Provide

- **Required Fields** - Metadata fields that must be filled on upload
- **Default Folder** - Automatic placement in the correct group
- **Default Lifecycle** - Automatic lifecycle assignment (permanent, expiring, recurring)
- **Extraction Prompt** - LLM prompt for automatic form data extraction

### Using a Template

When uploading a document:
1. Select a template from the dropdown
2. Fill in the required fields defined by the template
3. The document is automatically placed in the template's default folder
4. Lifecycle is assigned according to template settings
5. If an extraction prompt is defined, the LLM extracts structured data after processing

### Viewing Templates

```
GET /api/templates
```

---

## Requesting Access to Resources

If you need access to a document or group that is restricted:

### Submit an Access Request

```
POST /api/request-access
{
  "resource_type": "document",
  "resource_id": 5,
  "reason": "Need to review for quarterly audit"
}
```

### Track Your Request

View your pending requests and their status:
```
GET /api/access-requests/mine
```

### Request Lifecycle

1. **Pending** - Awaiting admin review
2. **Approved** - Access granted (you can now view the resource)
3. **Denied** - Access refused (contact admin for alternative arrangements)

---

## Using the Canvas/Whiteboard

Canvas provides a spatial workspace for organizing documents visually.

### Creating a Canvas

1. Use the command palette or navigate to the canvas section
2. Click "New Canvas" and give it a name
3. Start adding items by dragging documents onto the canvas

### Canvas Items

- **Document Cards** - Link to actual documents in the system
- **Text Notes** - Freeform text for annotations and labels
- **Connections** - Lines between items showing relationships

### Arranging Items

- Drag items to reposition them
- Resize items by dragging edges
- Use colors to categorize items visually
- Add labels to connections for clarity

### Exporting

Export your canvas in Obsidian-compatible `.canvas` format:
```
GET /api/canvas/{id}/export
```

The exported file can be opened directly in Obsidian.

---

## Viewing the Knowledge Graph

The knowledge graph visualizes relationships between documents, entities, and topics.

### Accessing the Graph

Navigate to the knowledge graph view or use:
```
GET /api/knowledge-graph
```

### Understanding the Graph

- **Blue nodes** - Documents
- **Green nodes** - Entities (people, organizations, technologies)
- **Orange nodes** - Topics (concepts, themes)
- **Edges** - Relationships between nodes (mentions, references, related)

### Interacting

- Click a node to view details
- Drag nodes to rearrange the layout
- Use mouse wheel to zoom in/out
- Filter by group, entity type, or relationship type

### Filtering

Narrow the graph to relevant content:
```
GET /api/knowledge-graph?group_id=1
GET /api/knowledge-graph?entity=OpenAI
GET /api/knowledge-graph?document_id=5
```

---

## Natural Language Search

Search for documents using plain English descriptions instead of keywords.

### How It Works

Type a natural description of what you are looking for:
- "Documents approved last week in engineering"
- "Contracts that mention data retention"
- "Files uploaded by John this month"

The system uses an LLM to translate your query into structured search filters.

### Using Natural Language Search

```
POST /api/search/natural
{"query": "policies that expire next month"}
```

The response includes both the interpreted filters and the matching documents.

---

## Offline Document Packages

Access documents without an internet connection.

### Generating a Package

Create an offline package for selected documents:
```
POST /api/offline/generate
{"document_ids": [1, 2, 3]}
```

Or for an entire group:
```
POST /api/offline/generate
{"group_id": 1}
```

### Using Offline Packages

1. Download the ZIP file
2. Extract to any location
3. Open `index.html` in a web browser
4. Browse, read, and search documents - no server needed

### What is Included

- Document files (PDF, original format)
- Markdown-rendered content
- Document metadata (status, keywords, summary)
- A searchable index

---

## Approval Workflows

### Multi-Stage Approvals

For documents requiring multiple levels of approval:

1. An admin sets up an approval chain with sequential/parallel steps
2. You submit your document to the chain
3. Each step's approvers are notified
4. Track progress as approvers make decisions
5. Document is fully approved only when all steps pass

### Checking Approval Status

View where your document is in the approval process:
```
GET /api/approval-chains/requests?document_id=5
```

### Delegating Approval Authority

If you will be unavailable, delegate your approval authority:
```
POST /api/delegations
{
  "delegate_id": "COLLEAGUE_USER_ID",
  "start_date": "2024-01-15T00:00:00",
  "end_date": "2024-01-22T23:59:59",
  "scope_type": "all"
}
```

---

## Signing Documents

### E-Signature

Sign documents to create a verifiable proof of approval:
```
POST /api/documents/{id}/sign
{"reason": "Final review approval"}
```

### What Happens When You Sign

1. A SHA-256 hash of the document content is computed
2. A signature record is created linking you to the document
3. A QR code is generated for quick verification
4. Optionally, an X.509 certificate can be used for stronger binding

### Verifying Signatures

Anyone with the verification URL or signature hash can verify:
```
GET /api/signatures/verify/{signature_hash}
```

### Viewing Document Signatures

See all signatures on a document:
```
GET /api/documents/{id}/signatures
```

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
