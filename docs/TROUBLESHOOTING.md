# Troubleshooting

Common issues with symptoms, causes, and solutions.

## Database Locked Errors

**Symptoms:**
- `sqlite3.OperationalError: database is locked`
- Timeouts on write operations
- Intermittent 500 errors on API calls

**Causes:**
- Multiple processes writing to SQLite simultaneously
- Long-running background tasks holding database locks
- WAL mode not enabled

**Solutions:**
1. Ensure only one application process writes to the database (or switch to PostgreSQL for concurrent access)
2. Increase SQLite busy timeout:
   ```python
   DATABASE_URL=sqlite+aiosqlite:///./edms.db?timeout=30
   ```
3. Enable WAL mode (better concurrent read performance):
   ```sql
   PRAGMA journal_mode=WAL;
   ```
4. For production with multiple workers, switch to PostgreSQL:
   ```env
   DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/edms
   ```

---

## Migration Failures

**Symptoms:**
- `alembic.util.exc.CommandError: Target database is not up to date`
- `sqlalchemy.exc.OperationalError: no such table`
- Application fails to start after code update

**Causes:**
- Database schema out of sync with models
- Missing migration files
- Migrations applied out of order

**Solutions:**
1. Check current migration state:
   ```bash
   uv run alembic current
   ```
2. Generate a new migration if models changed:
   ```bash
   uv run alembic revision --autogenerate -m "fix schema"
   ```
3. Apply pending migrations:
   ```bash
   uv run alembic upgrade head
   ```
4. For development, delete the database and let the app recreate it:
   ```bash
   rm edms.db
   uv run uvicorn app.main:app --reload  # auto-creates tables
   ```

---

## OpenAI API Key Not Set

**Symptoms:**
- Documents stuck in `processing` status
- `openai.AuthenticationError: No API key provided`
- Wiki operations return errors
- Search returns no results (embeddings not generated)

**Causes:**
- `OPENAI_API_KEY` not set in `.env`
- API key expired or revoked
- Rate limit exceeded

**Solutions:**
1. Set the API key in `.env`:
   ```env
   OPENAI_API_KEY=sk-your-key-here
   ```
2. Verify the key works:
   ```bash
   curl https://api.openai.com/v1/models \
     -H "Authorization: Bearer sk-your-key-here"
   ```
3. If using Ollama instead, set:
   ```env
   LLM_PROVIDER=ollama
   OLLAMA_BASE_URL=http://localhost:11434
   ```
4. Check rate limits at [OpenAI dashboard](https://platform.openai.com/usage)

---

## ChromaDB Connection Issues

**Symptoms:**
- `chromadb.errors.ConnectionError`
- Search endpoint returns 500 errors
- Documents process successfully but search returns nothing

**Causes:**
- ChromaDB server not running (if using server mode)
- Wrong host/port configuration
- Disk space full for local ChromaDB
- Incompatible ChromaDB version

**Solutions:**
1. For local mode, check disk space:
   ```bash
   du -sh ./chroma_db/
   df -h .
   ```
2. For server mode, verify connectivity:
   ```bash
   curl http://${CHROMA_HOST}:${CHROMA_PORT}/api/v1/heartbeat
   ```
3. Reset ChromaDB if corrupted:
   ```bash
   rm -rf ./chroma_db/
   # Re-process documents to rebuild embeddings
   ```
4. Check configuration:
   ```env
   # Local mode (leave CHROMA_HOST empty)
   CHROMA_DB_PATH=./chroma_db
   CHROMA_HOST=

   # Server mode
   CHROMA_HOST=chromadb-server
   CHROMA_PORT=8000
   ```

---

## PDF Processing Failures

**Symptoms:**
- Documents stuck in `processing` or moved to `failed` status
- Errors in logs mentioning PyMuPDF or Tesseract
- `FileNotFoundError: tesseract is not installed`

**Causes:**
- Tesseract OCR not installed (required for image-based PDFs)
- Corrupted PDF file
- Password-protected PDF (not the EDMS encryption)
- PyMuPDF version incompatibility
- Insufficient disk space for temporary files

**Solutions:**
1. Install Tesseract:
   ```bash
   # Ubuntu/Debian
   sudo apt-get install tesseract-ocr

   # macOS
   brew install tesseract
   ```
2. Check document status:
   ```bash
   curl http://localhost:8000/api/documents/1/status
   ```
3. For corrupted PDFs, try re-uploading
4. Check disk space for temp files:
   ```bash
   df -h /tmp
   ```
5. Verify PyMuPDF works:
   ```bash
   uv run python -c "import fitz; print(fitz.version)"
   ```

---

## LDAP Connection/Auth Failures

**Symptoms:**
- `ldap3.core.exceptions.LDAPSocketOpenError`
- `LDAPBindError: invalid credentials`
- LDAP sync shows 0 users found
- Users cannot log in via LDAP

**Causes:**
- LDAP server unreachable (firewall, DNS)
- Wrong bind credentials
- Incorrect base DN or search filters
- SSL/TLS misconfiguration
- Connection timeout too short

**Solutions:**
1. Test connectivity:
   ```bash
   # Test basic connectivity
   nc -zv ldap-server 389

   # Test LDAP bind
   ldapsearch -H ldap://server:389 -D "bind_dn" -w "password" -b "base_dn" "(objectClass=person)"
   ```
2. Use the test endpoint:
   ```bash
   curl -X POST http://localhost:8000/ldap/api/configs/CONFIG_ID/test \
     -H "Authorization: Bearer $TOKEN"
   ```
3. Increase connection timeout:
   ```json
   {"connect_timeout": 30}
   ```
4. Verify DN format matches your directory structure
5. Check sync logs for detailed errors:
   ```bash
   curl http://localhost:8000/ldap/api/configs/CONFIG_ID/logs \
     -H "Authorization: Bearer $TOKEN"
   ```

---

## Permission Denied (RBAC Misconfiguration)

**Symptoms:**
- HTTP 403 Forbidden responses
- `{"detail": "Insufficient permissions for action '...'"}`
- User cannot access endpoints they should have access to

**Causes:**
- User missing required role
- Role missing required permission
- Folder assignment not set up
- User role expired (`expires_at` passed)

**Solutions:**
1. Check user roles:
   ```bash
   curl http://localhost:8000/api/users/USER_ID \
     -H "Authorization: Bearer $ADMIN_TOKEN"
   ```
2. Assign the missing role:
   ```bash
   curl -X POST http://localhost:8000/api/users/USER_ID/roles \
     -H "Authorization: Bearer $ADMIN_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"role_name": "editor"}'
   ```
3. Check role permissions:
   ```bash
   curl http://localhost:8000/rbac/api/roles \
     -H "Authorization: Bearer $TOKEN"
   ```
4. For endpoint-specific issues, check which roles are required in the route's `Depends()` decorator

---

## File Upload Size Limits

**Symptoms:**
- `413 Request Entity Too Large`
- Upload hangs and eventually times out
- Large file uploads fail silently

**Causes:**
- Reverse proxy (nginx) has a lower limit than expected
- Client timeout too short for large uploads
- Disk space insufficient

**Solutions:**
1. Configure nginx (if used as reverse proxy):
   ```nginx
   client_max_body_size 500M;
   proxy_read_timeout 300;
   proxy_send_timeout 300;
   ```
2. Configure gunicorn timeout:
   ```bash
   gunicorn ... --timeout 300
   ```
3. Check available disk space:
   ```bash
   df -h $(grep STORAGE_PATH .env | cut -d= -f2)
   ```
4. For very large files, consider chunked upload (not currently supported natively)

---

## Background Task Failures

**Symptoms:**
- Documents stay in `processing` status indefinitely
- No summary or keywords generated
- ChromaDB not populated with new documents

**Causes:**
- Background task threw an unhandled exception
- OpenAI API call failed (rate limit, network)
- Database session expired during long processing
- Storage path not writable

**Solutions:**
1. Check document status:
   ```bash
   curl http://localhost:8000/api/documents/ID/status
   ```
2. If stuck in `processing`, the background task likely failed. Check application logs.
3. Verify OpenAI key is set and has quota
4. Check storage path permissions:
   ```bash
   ls -la storage/
   ```
5. To re-process a stuck document, the simplest approach is to re-upload it

---

## Search Returning No Results

**Symptoms:**
- `POST /api/search` returns empty results array
- Documents are processed but not findable
- Wiki queries return generic responses

**Causes:**
- Documents not fully processed (still in `processing` or `failed` state)
- ChromaDB not populated (embedding step failed)
- Wrong `group_id` filter
- OpenAI embedding API failed silently

**Solutions:**
1. Verify documents are processed:
   ```bash
   curl http://localhost:8000/api/documents
   ```
   Check that status is `"processed"` for target documents.

2. Check ChromaDB has data:
   ```bash
   du -sh ./chroma_db/
   ```

3. Try searching without group filter:
   ```bash
   curl -X POST http://localhost:8000/api/search \
     -H "Content-Type: application/json" \
     -d '{"query": "test", "group_id": null, "top_k": 10}'
   ```

4. If ChromaDB is empty, re-process documents by re-uploading them

---

## Wiki Operations Failing

**Symptoms:**
- `POST /api/wiki/query` returns errors
- Wiki index is empty
- Wiki pages not created after document processing

**Causes:**
- `WIKI_PATH` directory does not exist or is not writable
- OpenAI API key not set (wiki operations require LLM)
- Wiki directory corrupted

**Solutions:**
1. Check wiki directory exists and is writable:
   ```bash
   ls -la wiki/
   mkdir -p wiki/entities wiki/topics wiki/summaries
   ```
2. Check wiki index:
   ```bash
   curl http://localhost:8000/api/wiki/index
   ```
3. Run wiki lint to find issues:
   ```bash
   curl -X POST http://localhost:8000/api/wiki/lint
   ```
4. Verify `WIKI_PATH` setting:
   ```bash
   grep WIKI_PATH .env
   ```

---

## Lifecycle Transition Errors

**Symptoms:**
- `{"detail": "Invalid transition from 'X' to 'Y'"}`
- HTTP 400 on lifecycle transition attempts

**Causes:**
- Attempting an invalid state transition (not in the allowed graph)
- Document does not have a lifecycle assigned
- Lifecycle already in target state

**Solutions:**
1. Check current lifecycle state:
   ```bash
   curl http://localhost:8000/api/documents/1/lifecycle
   ```
2. Review valid transitions:
   - `draft` -> `in_review`
   - `in_review` -> `approved` or `draft`
   - `approved` -> `up_to_date`
   - `up_to_date` -> `needs_re_review` or `expired`
   - `needs_re_review` -> `in_review` or `expired`

3. Check transition history:
   ```bash
   curl http://localhost:8000/api/documents/1/lifecycle/history
   ```

---

## Bulk Upload Partial Failures

**Symptoms:**
- Bulk upload response shows some items with `"success": false`
- Some files uploaded, others failed
- `"failed"` count > 0 in response

**Causes:**
- Individual file read errors (corrupted file)
- Duplicate filenames in the same group
- Storage path not writable for some files
- Database constraint violations

**Solutions:**
1. Check the `error` field for each failed item in the response
2. Retry failed files individually:
   ```bash
   curl -X POST http://localhost:8000/api/groups/GROUP_ID/documents \
     -F "file=@failed_file.pdf"
   ```
3. Verify storage directory permissions
4. Check disk space

---

## JWT Token Expired

**Symptoms:**
- `{"detail": "Could not validate credentials"}`
- HTTP 401 on previously working requests
- Happens after `ACCESS_TOKEN_EXPIRE_MINUTES` (default: 30 min)

**Causes:**
- Token naturally expired
- Server time clock skew
- `SECRET_KEY` was rotated (invalidates all existing tokens)

**Solutions:**
1. Re-authenticate to get a new token:
   ```bash
   curl -X POST http://localhost:8000/api/auth/login \
     -H "Content-Type: application/json" \
     -d '{"username": "admin", "password": "admin"}'
   ```
2. Increase token lifetime (less secure):
   ```env
   ACCESS_TOKEN_EXPIRE_MINUTES=480
   ```
3. Implement token refresh in your client application
4. If `SECRET_KEY` was rotated, all users must re-authenticate

---

## Document Versioning Issues

**Symptoms:**
- `{"detail": "Document X not found"}` when uploading a version
- Version number not incrementing
- Encrypted path is null despite KMS being configured

**Causes:**
- Document does not exist (deleted or wrong ID)
- KMS provider not configured or passphrase missing
- Storage directory not writable
- Wrapped DEK storage failure

**Solutions:**
1. Verify the document exists:
   ```bash
   curl http://localhost:8000/api/documents/1
   ```
2. Check KMS configuration:
   ```env
   KMS_PROVIDER=local
   KMS_LOCAL_PASSPHRASE=your-passphrase
   ```
3. If encryption fails, versions are stored unencrypted (with a warning in logs). Check application logs for "storing unencrypted" messages.
4. Verify storage directory is writable:
   ```bash
   ls -la storage/versions/
   ```
5. To manually check version list:
   ```bash
   curl http://localhost:8000/api/documents/1/versions
   ```

---

## WebSocket Connection Problems

**Symptoms:**
- WebSocket connection immediately closes with code 1008
- No notifications received after connecting
- Connection drops after inactivity

**Causes:**
- Invalid or expired JWT token in query parameter
- User account deactivated
- Reverse proxy not configured for WebSocket upgrade
- No keep-alive ping being sent

**Solutions:**
1. Verify token is valid before connecting:
   ```bash
   curl http://localhost:8000/api/auth/me -H "Authorization: Bearer $TOKEN"
   ```
2. Ensure the token is passed as a query parameter:
   ```
   ws://localhost:8000/ws/notifications?token=YOUR_JWT_TOKEN
   ```
3. Send periodic ping messages to keep the connection alive:
   ```javascript
   setInterval(() => ws.send("ping"), 30000);
   ```
4. Configure nginx for WebSocket upgrade:
   ```nginx
   location /ws/ {
       proxy_pass http://backend;
       proxy_http_version 1.1;
       proxy_set_header Upgrade $http_upgrade;
       proxy_set_header Connection "upgrade";
       proxy_read_timeout 86400;
   }
   ```
5. Check that the user account is active (deactivated users are rejected)

---

## Obsidian Export Issues

**Symptoms:**
- Empty ZIP file returned
- 404 error on export endpoint
- Missing wikilinks in exported pages
- Sync endpoint returns empty results

**Causes:**
- Wiki directory has no content (no documents processed yet)
- Wiki path misconfigured
- Timestamp format incorrect for sync endpoint
- Wiki pages have no cross-references to convert to wikilinks

**Solutions:**
1. Check wiki has content:
   ```bash
   curl http://localhost:8000/api/wiki/index
   ls wiki/entities/ wiki/topics/
   ```
2. Verify wiki path configuration:
   ```env
   WIKI_PATH=wiki
   ```
3. For the sync endpoint, use ISO 8601 format:
   ```bash
   curl "http://localhost:8000/api/wiki/export/obsidian/sync?since=2024-01-14T00:00:00"
   ```
4. Process some documents first to populate the wiki before exporting
5. If ZIP is empty, check file permissions on the wiki directory

---

## Security Monitoring False Positives

**Symptoms:**
- Excessive "prompt_injection" alerts for normal documents
- KMS rate limiter blocking legitimate users
- External tool alerts flooding the security dashboard

**Causes:**
- Document content naturally contains patterns that match injection rules (e.g., "ignore previous" in legal text)
- Batch processing hitting KMS rate limit
- Monitoring tool misconfiguration generating false alerts

**Solutions:**
1. For prompt injection false positives:
   - Acknowledge the alerts: `POST /api/security/alerts/ID/acknowledge`
   - The system neutralizes the content but still processes it
   - Review `details_json.matched_text` to confirm it is benign

2. For KMS rate limiting issues:
   - Increase the limit if batch operations are needed:
     ```env
     KMS_RATE_LIMIT_MAX_CALLS=50
     ```
   - Stagger batch operations to stay within limits
   - Check which IPs are blocked via security status endpoint

3. For external alert flooding:
   - Review the source tool's rules and thresholds
   - Valid sources are limited to: `auditd`, `falco`, `suricata`
   - Adjust alert severity thresholds in the external tool

---

## Circuit Breaker Tripped

**Symptoms:**
- Fast failures on LLM or KMS operations
- Error responses with `KMS_ERROR` or `PROCESSING_ERROR` codes
- Operations that previously worked now fail immediately

**Causes:**
- External service (OpenAI, Ollama, KMS) experiencing outage
- Network connectivity issues
- Rate limits hit on external services
- Circuit breaker protecting against cascade failures

**Solutions:**
1. Check external service connectivity:
   ```bash
   # For OpenAI
   curl https://api.openai.com/v1/models -H "Authorization: Bearer $OPENAI_API_KEY"

   # For Ollama
   curl http://localhost:11434/api/tags
   ```
2. Check KMS provider status:
   ```bash
   # Verify KMS passphrase is set
   grep KMS_LOCAL_PASSPHRASE .env
   ```
3. Wait for the cooldown period and retry (circuit breaker will re-test automatically)
4. Check application logs for the underlying error that triggered the circuit breaker
5. If the external service is back, the system will resume normal operation after the cooldown

---

## Chat Session Issues

**Symptoms:**
- "Session not found" errors
- AI responses not referencing documents
- Chat history seems to reset

**Causes:**
- Session was deleted or belongs to a different user
- Session scope does not match available documents
- Windowed history (20 messages) exceeded, older context dropped

**Solutions:**
1. Verify session exists and belongs to you:
   ```bash
   curl http://localhost:8000/api/chat/sessions -H "Authorization: Bearer $TOKEN"
   ```
2. Create a new session with the correct scope:
   ```bash
   curl -X POST http://localhost:8000/api/chat/sessions \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"title": "New Discussion", "scope_type": "document", "scope_id": 1}'
   ```
3. For long conversations, start a new session to reset context window
4. Export the current session before it gets too long:
   ```bash
   curl "http://localhost:8000/api/chat/sessions/SESSION_ID/export?format=markdown" \
     -H "Authorization: Bearer $TOKEN"
   ```
