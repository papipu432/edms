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
