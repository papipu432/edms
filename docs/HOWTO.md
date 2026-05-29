# How-To Guides

Step-by-step guides for common EDMS tasks. For API curl examples, see [API_COOKBOOK.md](API_COOKBOOK.md).

## Upload a Single Document

1. **Create a group** (if you do not have one):
   ```bash
   curl -X POST http://localhost:8000/api/groups \
     -H "Content-Type: application/json" \
     -d '{"name": "My Project", "description": "Project documentation"}'
   ```
   Note the `id` in the response (e.g., `1`).

2. **Upload the file**:
   ```bash
   curl -X POST http://localhost:8000/api/groups/1/documents \
     -F "file=@/path/to/your/document.pdf"
   ```

3. **Check processing status**:
   ```bash
   curl http://localhost:8000/api/documents/1/status
   ```
   Wait until status is `"processed"`.

4. **View the converted markdown**:
   ```bash
   curl http://localhost:8000/api/documents/1/markdown
   ```

The document is now searchable via the semantic search and wiki endpoints.

---

## Bulk Upload Documents with Auto-Folder Creation

Upload multiple files at once. If you specify a `folder_path`, EDMS automatically creates the group hierarchy.

1. **Login and get a token** (requires editor or admin role):
   ```bash
   TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/login \
     -H "Content-Type: application/json" \
     -d '{"username": "admin", "password": "admin"}' | jq -r .access_token)
   ```

2. **Upload files with folder_path**:
   ```bash
   curl -X POST http://localhost:8000/api/bulk/upload \
     -H "Authorization: Bearer $TOKEN" \
     -F "files=@report1.pdf" \
     -F "files=@report2.pdf" \
     -F "files=@report3.docx" \
     -F "folder_path=Engineering/Reports/2024-Q1"
   ```

   This creates a group named "Engineering/Reports/2024-Q1" and uploads all three files into it.

3. **Review results**: Each file gets its own result entry showing success or failure:
   ```json
   {
     "results": [
       {"document_id": 10, "filename": "report1.pdf", "success": true, "error": null},
       {"document_id": 11, "filename": "report2.pdf", "success": true, "error": null},
       {"document_id": 12, "filename": "report3.docx", "success": true, "error": null}
     ],
     "total": 3,
     "successful": 3,
     "failed": 0
   }
   ```

Alternatively, use `group_id` instead of `folder_path` to upload into an existing group.

---

## Set Up Document Lifecycle

Assign a lifecycle to track document validity and schedule reviews.

### Permanent Document (never expires)

```bash
curl -X POST http://localhost:8000/api/documents/1/lifecycle \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"lifecycle_type": "permanent"}'
```

### Expiring Document (has a deadline)

```bash
curl -X POST http://localhost:8000/api/documents/1/lifecycle \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "lifecycle_type": "expiring",
    "expires_at": "2025-06-30T23:59:59"
  }'
```

### Recurring Document (periodic reviews)

```bash
curl -X POST http://localhost:8000/api/documents/1/lifecycle \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "lifecycle_type": "recurring",
    "review_interval_days": 90,
    "assigned_reviewer_id": "REVIEWER_USER_UUID"
  }'
```

---

## Transition a Document Through the Lifecycle

The lifecycle state machine has defined valid transitions. Follow this sequence for a typical review cycle:

1. **Draft -> In Review** (submit for review):
   ```bash
   curl -X POST http://localhost:8000/api/documents/1/lifecycle/transition \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"target_state": "in_review", "comment": "Ready for review"}'
   ```

2. **In Review -> Approved**:
   ```bash
   curl -X POST http://localhost:8000/api/documents/1/lifecycle/transition \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"target_state": "approved", "comment": "Content verified"}'
   ```

3. **Approved -> Up to Date**:
   ```bash
   curl -X POST http://localhost:8000/api/documents/1/lifecycle/transition \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"target_state": "up_to_date", "comment": "Published"}'
   ```

4. For recurring documents, when the review interval passes, transition to **Needs Re-Review**:
   ```bash
   curl -X POST http://localhost:8000/api/documents/1/lifecycle/transition \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"target_state": "needs_re_review", "comment": "Review interval elapsed"}'
   ```

5. Then back to **In Review** to restart the cycle:
   ```bash
   curl -X POST http://localhost:8000/api/documents/1/lifecycle/transition \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"target_state": "in_review", "comment": "Starting re-review"}'
   ```

**Valid transitions:**
- draft -> in_review
- in_review -> approved, draft
- approved -> up_to_date
- up_to_date -> needs_re_review, expired
- needs_re_review -> in_review, expired

---

## Approve Documents in Bulk

1. **Get your token** (must have approver or admin role):
   ```bash
   TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/login \
     -H "Content-Type: application/json" \
     -d '{"username": "admin", "password": "admin"}' | jq -r .access_token)
   ```

2. **Approve multiple documents**:
   ```bash
   curl -X POST http://localhost:8000/api/bulk/approve \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{
       "document_ids": [1, 2, 3, 4, 5],
       "comment": "Batch approved after team review meeting"
     }'
   ```

3. **Check results** for any failures:
   ```json
   {
     "results": [
       {"document_id": 1, "success": true, "error": null},
       {"document_id": 2, "success": true, "error": null},
       {"document_id": 3, "success": false, "error": "Document not found"}
     ],
     "total": 3,
     "successful": 2,
     "failed": 1
   }
   ```

---

## Sign Off Documents in Bulk

Similar to bulk approve, but uses the `sign_off` action for final sign-off:

```bash
curl -X POST http://localhost:8000/api/bulk/signoff \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "document_ids": [1, 2, 3],
    "comment": "Final sign-off for release"
  }'
```

---

## Configure Email Alerts for Lifecycle

Email alerts notify reviewers when documents are about to expire or need re-review.

1. **Set SMTP configuration** in your `.env` file:
   ```env
   SMTP_HOST=smtp.company.com
   SMTP_PORT=587
   SMTP_USER=edms-noreply@company.com
   SMTP_PASSWORD=smtp-password
   SMTP_FROM_EMAIL=edms@company.com
   ALERT_DAYS_BEFORE_EXPIRY=30
   ALERT_DAYS_BEFORE_REVIEW=14
   ```

2. **Manually trigger alert check** (or set up a cron job):
   ```bash
   curl -X POST http://localhost:8000/api/lifecycle/check-alerts \
     -H "Authorization: Bearer $TOKEN"
   ```

3. **View pending alerts** without sending emails:
   ```bash
   curl "http://localhost:8000/api/lifecycle/alerts?days_before_expiry=30&days_before_review=14"
   ```

To automate, set up a cron job or external scheduler to call the check-alerts endpoint periodically.

---

## Add a New User with Roles

1. **Register the user** (if registration is enabled):
   ```bash
   curl -X POST http://localhost:8000/api/auth/register \
     -H "Content-Type: application/json" \
     -d '{
       "username": "jane.smith",
       "email": "jane@company.com",
       "password": "SecurePassword123!"
     }'
   ```
   Note the returned user `id`.

2. **Assign roles** (requires admin):
   ```bash
   # Assign editor role
   curl -X POST http://localhost:8000/api/users/USER_UUID/roles \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"role_name": "editor"}'

   # Assign reviewer role
   curl -X POST http://localhost:8000/api/users/USER_UUID/roles \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"role_name": "reviewer"}'
   ```

3. **Optionally assign folder permissions**:
   ```bash
   curl -X POST http://localhost:8000/api/users/USER_UUID/folders \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{
       "folder_path": "/Engineering",
       "role_name": "editor"
     }'
   ```

---

## Set Up LDAP Synchronization

1. **Create an LDAP configuration**:
   ```bash
   curl -X POST http://localhost:8000/ldap/api/configs \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{
       "name": "Corporate Active Directory",
       "server_url": "ldap://ad.company.com",
       "server_port": 389,
       "base_dn": "dc=company,dc=com",
       "bind_dn": "cn=svc-edms,ou=service-accounts,dc=company,dc=com",
       "bind_password": "service-account-password",
       "sync_enabled": true,
       "sync_create_users": true,
       "sync_update_users": true,
       "sync_disable_missing": false,
       "default_role": "viewer"
     }'
   ```

2. **Test the connection**:
   ```bash
   curl -X POST http://localhost:8000/ldap/api/configs/CONFIG_ID/test \
     -H "Authorization: Bearer $TOKEN"
   ```

3. **Set up group-role mappings**:
   ```bash
   curl -X POST http://localhost:8000/ldap/api/configs/CONFIG_ID/group-roles \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{
       "ldap_group_dn": "cn=editors,ou=groups,dc=company,dc=com",
       "role_code": "editor"
     }'
   ```

4. **Trigger a sync**:
   ```bash
   curl -X POST http://localhost:8000/ldap/api/configs/CONFIG_ID/sync \
     -H "Authorization: Bearer $TOKEN"
   ```

5. **Check sync logs**:
   ```bash
   curl http://localhost:8000/ldap/api/configs/CONFIG_ID/logs \
     -H "Authorization: Bearer $TOKEN"
   ```

---

## Configure Encryption

1. **Initialize encryption** (generates KEK, splits into Shamir shares):
   ```bash
   curl -X POST http://localhost:8000/api/settings/encryption/init \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{
       "threshold": 2,
       "num_shares": 3,
       "passphrase": "master-passphrase",
       "share_holders": ["security_officer", "cto", "backup_admin"]
     }'
   ```

2. **Distribute shares** to designated holders securely. Shares are only shown once.

3. **To recover the key** (if passphrase is lost), collect the threshold number of shares:
   ```bash
   curl -X POST http://localhost:8000/api/settings/encryption/recover \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{
       "shares": [
         {"index": 1, "share_hex": "share-hex-from-holder-1"},
         {"index": 3, "share_hex": "share-hex-from-holder-3"}
       ]
     }'
   ```

---

## Backup and Restore

1. **Configure MinIO endpoint**:
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

2. **Set backup schedule**:
   ```bash
   curl -X POST http://localhost:8000/api/settings/backup/schedule \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"cron_expression": "0 2 * * *", "is_active": true}'
   ```

3. **Trigger manual backup**:
   ```bash
   curl -X POST http://localhost:8000/api/settings/backup/run \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"target": "primary"}'
   ```

4. **Check backup status and history**:
   ```bash
   curl http://localhost:8000/api/settings/backup/status \
     -H "Authorization: Bearer $TOKEN"

   curl http://localhost:8000/api/settings/backup/history \
     -H "Authorization: Bearer $TOKEN"
   ```

---

## Search Documents

1. **Semantic search** across all documents:
   ```bash
   curl -X POST http://localhost:8000/api/search \
     -H "Content-Type: application/json" \
     -d '{"query": "quarterly budget report procedures", "top_k": 5}'
   ```

2. **Search within a specific group**:
   ```bash
   curl -X POST http://localhost:8000/api/search \
     -H "Content-Type: application/json" \
     -d '{"query": "deployment checklist", "group_id": 3, "top_k": 10}'
   ```

3. **RAG chat** (conversational search with context):
   ```bash
   curl -X POST http://localhost:8000/api/chat \
     -H "Content-Type: application/json" \
     -d '{
       "query": "What are the backup retention policies?",
       "history": [
         {"role": "user", "content": "Tell me about backups"},
         {"role": "assistant", "content": "EDMS supports MinIO and Restic backups..."}
       ]
     }'
   ```

---

## Use the Wiki Chat

1. **Check the wiki index** to see what knowledge exists:
   ```bash
   curl http://localhost:8000/api/wiki/index
   ```

2. **Ask a question**:
   ```bash
   curl -X POST http://localhost:8000/api/wiki/query \
     -H "Content-Type: application/json" \
     -d '{"question": "What technologies are mentioned in the architecture documents?"}'
   ```

3. **Browse specific wiki pages**:
   ```bash
   curl http://localhost:8000/api/wiki/pages/entities/openai.md
   ```

4. **Run wiki health check**:
   ```bash
   curl -X POST http://localhost:8000/api/wiki/lint
   ```

---

## Configure Ollama Instead of OpenAI

To use locally-hosted LLM models via Ollama instead of OpenAI:

1. **Install Ollama** from [ollama.ai](https://ollama.ai)

2. **Pull required models**:
   ```bash
   ollama pull llama3
   ollama pull nomic-embed-text
   ```

3. **Update `.env`**:
   ```env
   LLM_PROVIDER=ollama
   OLLAMA_BASE_URL=http://localhost:11434
   OLLAMA_MODEL_SUMMARIZE=llama3
   OLLAMA_MODEL_KEYWORDS=llama3
   OLLAMA_MODEL_EMBEDDINGS=nomic-embed-text
   OLLAMA_MODEL_CHAT=llama3
   ```

4. **Restart the server**. The system will now use Ollama for all LLM operations.

Note: You no longer need to set `OPENAI_API_KEY` when using Ollama.

---

## Compare Two Documents

Compare documents to see metadata differences and content diffs.

### Compare by document ID

```bash
curl "http://localhost:8000/api/documents/compare?doc_a=1&doc_b=2" \
  -H "Authorization: Bearer $TOKEN"
```

The response includes:
- **Metadata comparison** - Field-by-field differences (filename, size, type, status, summary, keywords, timestamps)
- **Content diff** - Unified diff of markdown content if both documents have been processed
- **Similarity ratio** - A 0-1 score indicating how similar the content is

### View an HTML side-by-side diff

For a visual comparison, open in a browser:
```bash
curl "http://localhost:8000/api/documents/compare/html?doc_a=1&doc_b=2" \
  -H "Authorization: Bearer $TOKEN" > comparison.html
open comparison.html
```

### Compare two versions of the same document

```bash
curl "http://localhost:8000/api/documents/1/versions/diff?version_a=1&version_b=2" \
  -H "Authorization: Bearer $TOKEN"
```

---

## Manage Document Versions

### Upload a new version

When you update a document, upload it as a new version to preserve history:

```bash
curl -X POST http://localhost:8000/api/documents/1/versions \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@updated-policy.pdf" \
  -F "changelog=Updated compliance section for 2024 regulations"
```

Each version is independently encrypted with its own DEK via the KMS provider.

### View version history

```bash
curl http://localhost:8000/api/documents/1/versions
```

### Revert to an older version

If a new version has issues, revert to a previous one:

```bash
# First, find the version UUID from the list
curl http://localhost:8000/api/documents/1/versions

# Then revert to it
curl -X POST http://localhost:8000/api/documents/1/versions/VERSION_UUID/revert \
  -H "Authorization: Bearer $TOKEN"
```

This updates the document to point to the target version's storage path and file metadata.

---

## Export Wiki to Obsidian

Export the LLM wiki as an Obsidian-compatible vault for local use.

### Full export

```bash
curl http://localhost:8000/api/wiki/export/obsidian \
  -H "Authorization: Bearer $TOKEN" \
  -o obsidian-vault.zip

# Unzip into your Obsidian vaults directory
unzip obsidian-vault.zip -d ~/Documents/ObsidianVaults/EDMS-Wiki/
```

The exported vault includes:
- [[wikilink]] syntax linking related pages
- YAML frontmatter with metadata (tags, dates, sources)
- Dataview-compatible properties for advanced queries
- Folder structure matching wiki layout (entities/, topics/, summaries/)

### Incremental sync

For ongoing synchronization without re-downloading everything:

```bash
# Get pages modified since a specific timestamp
curl "http://localhost:8000/api/wiki/export/obsidian/sync?since=2024-01-14T00:00:00" \
  -H "Authorization: Bearer $TOKEN"
```

This returns a list of modified pages with their paths and timestamps, so you can update only what changed.

### Get a single page

```bash
curl http://localhost:8000/api/wiki/export/obsidian/page/entities/openai.md \
  -H "Authorization: Bearer $TOKEN"
```

---

## Configure Security Monitoring

Set up the multi-layer security monitoring stack.

### Check monitoring status

```bash
curl http://localhost:8000/api/security/status \
  -H "Authorization: Bearer $TOKEN"
```

This shows the configuration status of each monitoring layer (auditd, falco, suricata, KMS rate limiter).

### Set up external alert ingestion

Configure external monitoring tools to send alerts to EDMS:

```bash
# Example: Falco alerting to EDMS
curl -X POST http://localhost:8000/api/security/alerts \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "source": "falco",
    "severity": "high",
    "message": "Unexpected privileged container detected",
    "details": {"rule": "Launch Privileged Container", "container_id": "abc123"}
  }'
```

Valid sources: `auditd`, `falco`, `suricata`
Valid severities: `low`, `medium`, `high`, `critical`

### Configure KMS rate limiting

The KMS rate limiter is configured via environment variables:

```env
KMS_RATE_LIMIT_MAX_CALLS=10       # Max unwrap calls per IP per window
KMS_RATE_LIMIT_WINDOW_SECONDS=60  # Sliding window duration
```

If a client exceeds the limit, unwrap operations are blocked and a warning is logged.

---

## Run the Setup Wizard

### First-time setup via CLI

```bash
python -m app.setup_wizard
```

The wizard guides you through:
1. Database configuration (SQLite path or PostgreSQL connection string)
2. Storage directory setup
3. Security keys (generates SECRET_KEY, optional KEK with Shamir shares)
4. MinIO backup endpoint (optional)
5. LLM provider (OpenAI API key or Ollama URL)
6. SMTP configuration for lifecycle email alerts

It generates a `.env` file with all your settings.

### Web wizard on first launch

If no `.env` file exists when the application starts, the web wizard is served at the root URL. Complete the form to generate configuration and initialize the database.

---

## Use the Health Dashboard

Monitor system health and detect issues with documents and lifecycles.

### Run a health check

```bash
curl http://localhost:8000/api/health/check \
  -H "Authorization: Bearer $TOKEN"
```

The health check detects:
- **Expired lifecycles** - Documents past their expiration date
- **Broken reviewers** - Lifecycles assigned to deleted/deactivated users
- **Empty groups** - Groups with no documents
- **Stale documents** - Documents stuck in "processing" for over 24 hours

### View the HTML dashboard

Navigate to `/settings/health` in your browser (requires admin role).

### Send a digest email to admins

```bash
curl -X POST http://localhost:8000/api/health/send-digest \
  -H "Authorization: Bearer $TOKEN"
```

This runs the health check and emails the results to all active admin users.

---

## Configure Approval Chains

Set up multi-stage approval workflows for documents.

### Create an approval chain

```bash
curl -X POST http://localhost:8000/api/approval-chains \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Contract Approval",
    "folder_id": 1,
    "steps": [
      {"step_order": 1, "approval_type": "sequential", "role_code": "reviewer", "timeout_hours": 48},
      {"step_order": 2, "approval_type": "parallel", "role_code": "approver"}
    ]
  }'
```

### Submit a document for approval

```bash
curl -X POST http://localhost:8000/api/approval-chains/1/submit \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"document_id": 5}'
```

### Monitor approval status

Check the current status of a pending approval:
```bash
curl http://localhost:8000/api/approval-chains/requests?document_id=5 \
  -H "Authorization: Bearer $TOKEN"
```

### Approve or reject at a step

```bash
curl -X POST http://localhost:8000/api/approval-chains/requests/1/decide \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"decision": "approved", "comment": "Verified and approved"}'
```

---

## Set Up SLA Policies

Define time-bound service level agreements for document actions.

### Create an SLA policy

```bash
curl -X POST http://localhost:8000/api/sla-policies \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "folder_id": 1,
    "action": "approval",
    "max_duration_hours": 48,
    "escalation_role": "manager",
    "is_active": true
  }'
```

### Monitor SLA status

View the SLA dashboard to see which items are on time, at risk, or breached:
```bash
curl http://localhost:8000/api/sla/dashboard \
  -H "Authorization: Bearer $TOKEN"
```

### Handle SLA breaches

When an SLA is breached, the system:
1. Updates the document SLA status to "breached"
2. Sends a notification to users with the `escalation_role`
3. Sets the `escalated` flag to true
4. Emits a webhook event (if configured)

Review breached items:
```bash
curl "http://localhost:8000/api/sla/dashboard?status=breached" \
  -H "Authorization: Bearer $TOKEN"
```

---

## Enable Geo-Fencing

Restrict access to documents based on IP address or country.

### Create a global deny rule

Block access from specific IP ranges:
```bash
curl -X POST http://localhost:8000/api/geofence/rules \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "scope": "global",
    "denied_ip_ranges": ["10.0.0.0/8", "172.16.0.0/12"],
    "action": "allow",
    "enabled": true
  }'
```

### Restrict to specific countries

```bash
curl -X POST http://localhost:8000/api/geofence/rules \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "scope": "global",
    "allowed_countries": ["US", "GB", "DE", "FR"],
    "action": "allow",
    "enabled": true
  }'
```

### Apply rules to a specific folder

```bash
curl -X POST http://localhost:8000/api/geofence/rules \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "scope": "group",
    "scope_id": 3,
    "allowed_countries": ["US"],
    "action": "allow",
    "enabled": true
  }'
```

### Verify rules are applied

The geo-fence middleware runs on every request. Test by checking access from different IPs:
```bash
curl -H "X-Forwarded-For: 203.0.113.1" http://localhost:8000/api/documents \
  -H "Authorization: Bearer $TOKEN"
```

---

## Configure Webhooks

Send notifications to external systems when events occur in EDMS.

### Register a webhook

```bash
curl -X POST http://localhost:8000/api/webhooks \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://hooks.slack.com/services/T00/B00/xxxx",
    "secret": "my-signing-secret-123",
    "events": ["document.created", "document.approved", "sla.breached"],
    "is_active": true
  }'
```

### Test the webhook

Sends a test payload to verify connectivity:
```bash
curl -X POST http://localhost:8000/api/webhooks/1/test \
  -H "Authorization: Bearer $TOKEN"
```

### Verify webhook signatures

On the receiving end, verify the `X-Webhook-Signature` header:
```python
import hmac, hashlib

def verify_webhook(body: bytes, signature: str, secret: str) -> bool:
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)
```

### Available event types

- `document.created` - New document uploaded
- `document.approved` - Document approved via workflow
- `document.deleted` - Document deleted
- `lifecycle.expired` - Document lifecycle expired
- `lifecycle.transitioned` - Lifecycle state changed
- `sla.at_risk` - SLA approaching deadline
- `sla.breached` - SLA deadline passed
- `approval.submitted` - Document submitted to approval chain
- `approval.decided` - Approval decision made

---

## Use the Canvas/Whiteboard

Create spatial arrangements of documents for visual organization.

### Create a canvas

```bash
curl -X POST http://localhost:8000/api/canvas \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "Project Architecture"}'
```

### Add documents to the canvas

```bash
# Add a document card
curl -X POST http://localhost:8000/api/canvas/1/items \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "document_id": 5,
    "x_position": 100.0,
    "y_position": 200.0,
    "width": 250.0,
    "height": 150.0,
    "color": "#3b82f6"
  }'

# Add a text note
curl -X POST http://localhost:8000/api/canvas/1/items \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "note_text": "This section needs review",
    "x_position": 400.0,
    "y_position": 200.0,
    "width": 200.0,
    "height": 100.0,
    "color": "#ef4444"
  }'
```

### Connect items

```bash
curl -X POST http://localhost:8000/api/canvas/1/connections \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"from_item_id": 1, "to_item_id": 2, "label": "depends on"}'
```

### Export as .canvas format

Export the canvas in Obsidian-compatible format:
```bash
curl http://localhost:8000/api/canvas/1/export \
  -H "Authorization: Bearer $TOKEN" > project-architecture.canvas
```

---

## Generate Offline Packages

Create self-contained document packages for access without a server.

### Generate package for specific documents

```bash
curl -X POST http://localhost:8000/api/offline/generate \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"document_ids": [1, 2, 3, 4, 5]}' \
  -o offline-package.zip
```

### Generate package for an entire group

```bash
curl -X POST http://localhost:8000/api/offline/generate \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"group_id": 1}' \
  -o engineering-docs-offline.zip
```

### Using the offline package

1. Unzip the downloaded package
2. Open `index.html` in any web browser
3. Browse documents, view markdown content, and search - all without a network connection

---

## Import from External Systems

Import documents and metadata from other systems.

### Import from ZIP with manifest

Create a ZIP file containing:
- `manifest.json` - Document metadata (filenames, groups, tags)
- Document files referenced in the manifest

```bash
curl -X POST http://localhost:8000/api/import \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@migration-package.zip"
```

### Import from CSV

Create a CSV with columns: `filename`, `group`, `tags`, `lifecycle_type`:

```bash
curl -X POST http://localhost:8000/api/import \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@document-metadata.csv"
```

### Export for migration

Export all documents and metadata for migration to another system:

```bash
curl http://localhost:8000/api/export \
  -H "Authorization: Bearer $TOKEN" \
  -o full-export.zip
```

---

## Set Up Multi-Tenant

Configure EDMS for multiple isolated tenants sharing a single deployment.

### Create a tenant

```bash
curl -X POST http://localhost:8000/api/tenants \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Acme Corporation",
    "slug": "acme",
    "settings": {"max_storage_gb": 100, "max_users": 50}
  }'
```

### Access as a specific tenant

Include the `X-Tenant-ID` header with the tenant slug:
```bash
curl http://localhost:8000/api/documents \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Tenant-ID: acme"
```

### Manage tenant settings

```bash
curl -X PUT http://localhost:8000/api/tenants/1 \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"settings": {"max_storage_gb": 200, "max_users": 100, "features": ["canvas", "webhooks"]}}'
```

### Tenant isolation

Each tenant has:
- Separate document storage directories
- Isolated database queries (all data scoped by tenant_id)
- Independent settings and configurations
- Users belonging to exactly one tenant
