# Operations Runbook

Production deployment, monitoring, backup, and incident response procedures for EDMS.

## Production Deployment

### Uvicorn with Gunicorn Workers

For production, run uvicorn behind gunicorn with multiple workers:

```bash
# Install gunicorn
pip install gunicorn

# Run with gunicorn (4 uvicorn workers)
gunicorn app.main:app \
  --workers 4 \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000 \
  --timeout 120 \
  --access-logfile /var/log/edms/access.log \
  --error-logfile /var/log/edms/error.log
```

### Docker Deployment

Create a `Dockerfile`:

```dockerfile
FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    libgl1-mesa-glx \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install uv
RUN pip install uv

# Copy project files
COPY pyproject.toml uv.lock* ./
RUN uv sync --no-dev

COPY app/ app/
COPY wiki/ wiki/

# Create storage directories
RUN mkdir -p storage chroma_db data

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

Build and run:

```bash
docker build -t edms:latest .
docker run -d \
  --name edms \
  -p 8000:8000 \
  -v /data/edms/storage:/app/storage \
  -v /data/edms/db:/app/data \
  -v /data/edms/chroma:/app/chroma_db \
  --env-file .env.production \
  edms:latest
```

### Docker Compose

```yaml
version: "3.8"
services:
  edms:
    build: .
    ports:
      - "8000:8000"
    volumes:
      - edms-storage:/app/storage
      - edms-db:/app/data
      - edms-chroma:/app/chroma_db
      - edms-wiki:/app/wiki
    env_file:
      - .env.production
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/docs"]
      interval: 30s
      timeout: 10s
      retries: 3

volumes:
  edms-storage:
  edms-db:
  edms-chroma:
  edms-wiki:
```

---

## Environment Variables for Production

Critical variables to set for production (never use defaults):

```env
# Security - MUST CHANGE
SECRET_KEY=<random-64-char-string>
PDF_ENCRYPTION_PASSWORD=<strong-password>
BOOTSTRAP_ADMIN_PASSWORD=<strong-admin-password>

# Database
DATABASE_URL=sqlite+aiosqlite:///./data/edms.db

# Or for PostgreSQL:
# DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/edms

# LLM
OPENAI_API_KEY=sk-...

# Disable open registration in production
ALLOW_REGISTRATION=false

# SMTP for alerts
SMTP_HOST=smtp.company.com
SMTP_PORT=587
SMTP_USER=edms@company.com
SMTP_PASSWORD=smtp-password
SMTP_FROM_EMAIL=edms-alerts@company.com

# Backup
MINIO_PRIMARY_ENDPOINT=minio.internal:9000
MINIO_PRIMARY_ACCESS_KEY=...
MINIO_PRIMARY_SECRET_KEY=...
```

---

## Database Setup and Migrations

### Initial Setup

On first startup, EDMS automatically:
1. Creates all tables via `Base.metadata.create_all`
2. Seeds system roles, permissions, unit types, grades
3. Creates the bootstrap admin user

### Production Migrations

For schema changes in production:

```bash
# Generate migration
uv run alembic revision --autogenerate -m "description"

# Review the generated migration file
# Then apply:
uv run alembic upgrade head

# Rollback if needed:
uv run alembic downgrade -1
```

### Database Backup

SQLite:
```bash
sqlite3 edms.db ".backup '/backup/edms-$(date +%Y%m%d).db'"
```

---

## Monitoring and Health Checks

### Health Check Endpoint

The FastAPI docs endpoint serves as a basic health check:

```bash
curl -f http://localhost:8000/docs
```

### Application Logs

Configure Python logging:

```python
import logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler("/var/log/edms/app.log"),
        logging.StreamHandler(),
    ],
)
```

### Key Metrics to Monitor

- Response latency on document upload endpoints
- Background task queue depth (document processing)
- Database connection pool usage
- Disk space for storage, ChromaDB, and wiki directories
- Memory usage (ChromaDB can be memory-intensive)
- OpenAI API rate limit errors

### Log Files

| Log | Location | Purpose |
|-----|----------|---------|
| Application | stdout / app.log | Application events |
| Access | access.log (gunicorn) | HTTP request log |
| LDAP sync | Database (ldap_sync_logs table) | Sync operations |
| Backup | Database (backup_jobs table) | Backup job history |
| Security | Database (security_alerts table) | Security events |
| Wiki | wiki/log.md | Wiki operations |

---

## Backup Procedures

### MinIO Backup (Primary and DR)

EDMS supports two MinIO targets:
- **Primary** - Main backup storage
- **DR** - Disaster recovery (geographically separate)

Configure via environment variables or API:

```bash
# Check backup configuration
curl http://localhost:8000/api/settings/backup/config \
  -H "Authorization: Bearer $TOKEN"

# Trigger backup to primary
curl -X POST http://localhost:8000/api/settings/backup/run \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"target": "primary"}'

# Trigger backup to DR
curl -X POST http://localhost:8000/api/settings/backup/run \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"target": "dr"}'
```

### Restic Backup

For file-level backup with deduplication:

```env
RESTIC_REPOSITORY=s3:https://s3.amazonaws.com/edms-restic-repo
RESTIC_PASSWORD=restic-encryption-password
```

### Backup Schedule

Default schedule: `0 2 * * *` (2 AM daily)

Update via API:
```bash
curl -X POST http://localhost:8000/api/settings/backup/schedule \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"cron_expression": "0 2 * * *", "is_active": true}'
```

### Retention Policy

Default: 30 days. Configure via `BACKUP_RETENTION_DAYS` environment variable.

---

## Disaster Recovery

### Recovery Procedure

1. **Restore database** from latest backup:
   ```bash
   cp /backup/edms-latest.db ./data/edms.db
   ```

2. **Restore storage files** from MinIO/Restic:
   ```bash
   # From MinIO
   mc cp --recursive minio/edms-backup/ ./storage/

   # From Restic
   restic restore latest --target ./storage/
   ```

3. **Restore ChromaDB** (if backed up):
   ```bash
   cp -r /backup/chroma_db/ ./chroma_db/
   ```

4. **Restore wiki files**:
   ```bash
   cp -r /backup/wiki/ ./wiki/
   ```

5. **Restart the application**.

### Recovery Time Objective (RTO)

Target: 1 hour for full recovery from backup.

### Recovery Point Objective (RPO)

Depends on backup frequency. Default daily backups = maximum 24 hours data loss.

---

## Incident Response

### Security Alert Received

1. Check the alert details:
   ```bash
   curl http://localhost:8000/api/security/alerts \
     -H "Authorization: Bearer $TOKEN"
   ```

2. Assess severity (low/medium/high/critical).

3. For ransomware alerts:
   - Check quarantine directory for isolated files
   - Stop the file monitor if false positive: `POST /api/security/monitor/stop`
   - Investigate the source path in the alert

4. Acknowledge the alert:
   ```bash
   curl -X POST http://localhost:8000/api/security/alerts/ALERT_ID/acknowledge \
     -H "Authorization: Bearer $TOKEN"
   ```

### Unauthorized Access Attempt

1. Check access logs for the source IP.
2. Verify the target user account is not compromised.
3. If compromised, deactivate the user via the admin panel.
4. Rotate the `SECRET_KEY` and force re-authentication for all users.

### Data Corruption

1. Stop the application immediately.
2. Take a snapshot of the current database state.
3. Restore from the last known good backup.
4. Re-process any documents uploaded since the backup.

---

## Performance Tuning

### Database

- For SQLite: Ensure WAL mode is enabled for concurrent reads
- For PostgreSQL: Configure connection pooling (pgbouncer), tune shared_buffers
- Add database indexes for frequently queried fields

### ChromaDB

- Monitor memory usage (embeddings are held in memory)
- Consider running ChromaDB as a separate server for large collections:
  ```env
  CHROMA_HOST=chromadb-server
  CHROMA_PORT=8000
  ```

### File Storage

- Use SSD storage for the document storage directory
- Consider NFS or distributed storage for multi-node deployments
- Monitor disk space (documents + encrypted copies + markdown)

### Application

- Increase gunicorn workers for more concurrent requests (2-4x CPU cores)
- Configure async database connection pooling
- Use Redis for session storage in multi-node deployments

---

## Scaling Considerations

### Vertical Scaling

- Add more CPU cores (more gunicorn workers)
- Add more RAM (ChromaDB, document processing)
- Faster storage (SSD/NVMe for database and documents)

### Horizontal Scaling

- Run multiple application instances behind a load balancer
- Use PostgreSQL instead of SQLite for multi-node database access
- Run ChromaDB as a shared server
- Use shared storage (NFS, S3) for document files
- Use Redis for distributed session management

---

## ChromaDB Maintenance

### Collection Management

ChromaDB stores vector embeddings organized by group. Over time:
- Monitor collection sizes
- Consider archiving old collections for deleted groups
- Rebuild indexes if search quality degrades

### Disk Space

ChromaDB persists to `CHROMA_DB_PATH` (default: `./chroma_db`). Monitor disk usage:

```bash
du -sh ./chroma_db/
```

### Migration

To migrate ChromaDB from local to server mode:
1. Set `CHROMA_HOST` and `CHROMA_PORT` in environment
2. Export existing collections and re-import (or re-process all documents)

---

## Security Hardening

See [SECURITY.md](SECURITY.md) for the full security hardening checklist. Key items:

1. Change all default passwords (`SECRET_KEY`, `PDF_ENCRYPTION_PASSWORD`, admin password)
2. Disable registration (`ALLOW_REGISTRATION=false`)
3. Use HTTPS (terminate TLS at reverse proxy)
4. Set restrictive CORS origins (replace `allow_origins=["*"]`)
5. Enable LDAP for enterprise authentication
6. Initialize envelope encryption
7. Enable ransomware monitoring
8. Configure automated backups
9. Restrict file upload sizes at reverse proxy level
10. Run as non-root user in Docker

---

## Security Monitoring Deployment

### auditd Configuration

Deploy auditd rules to monitor EDMS storage directories:

```bash
# /etc/audit/rules.d/edms.rules
-w /data/edms/storage -p wa -k edms_file_modify
-w /data/edms/db -p wa -k edms_db_modify
-w /app/storage/.keys -p rwa -k edms_key_access
```

Configure auditd to forward alerts to EDMS:
```bash
# Script to forward auditd alerts to EDMS webhook
ausearch -k edms_file_modify --format json | \
  curl -X POST http://localhost:8000/api/security/alerts \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d @- <<EOF
{
  "source": "auditd",
  "severity": "medium",
  "message": "File modification detected in storage",
  "details": {}
}
EOF
```

### Falco Deployment

Deploy Falco for container/process monitoring:

```yaml
# falco_rules_edms.yaml
- rule: EDMS Unexpected Process
  desc: Detect unexpected processes in EDMS container
  condition: container.name = "edms" and spawned_process and not proc.name in (python, uvicorn, gunicorn)
  output: "Unexpected process in EDMS container (user=%user.name process=%proc.name)"
  priority: WARNING
  tags: [edms, process]
```

Configure Falco to send alerts to EDMS:
```yaml
# falco.yaml (outputs section)
http_output:
  enabled: true
  url: "http://edms:8000/api/security/alerts"
  headers:
    Authorization: "Bearer <service-token>"
```

### Suricata Network Monitoring

Deploy Suricata rules for data exfiltration detection:

```
# edms.rules
alert tcp $EDMS_NET any -> $EXTERNAL_NET any (msg:"EDMS potential data exfiltration"; flow:to_server; threshold:type both,track by_src,count 100,seconds 60; sid:1000001; rev:1;)
```

Configure Suricata EVE log forwarding to EDMS webhook.

### KMS Rate Limiting Configuration

The KMS rate limiter protects against brute-force key extraction:

```env
# .env configuration
KMS_RATE_LIMIT_MAX_CALLS=10       # Maximum unwrap calls per IP per minute
KMS_RATE_LIMIT_WINDOW_SECONDS=60  # Sliding window size
```

Monitor rate limit status:
```bash
# Check which IPs are being rate-limited
curl http://localhost:8000/api/security/status \
  -H "Authorization: Bearer $TOKEN"
```

**Important:** In multi-worker deployments (gunicorn with multiple workers), rate limiting is per-process. For production, replace with a Redis-backed rate limiter.

---

## KMS Operations

### Provider Selection

Configure the KMS provider in `.env`:

```env
# Local file-based KMS (default, good for single-server deployments)
KMS_PROVIDER=local
KMS_LOCAL_PASSPHRASE=your-strong-passphrase-here

# HashiCorp Vault (for enterprise deployments)
KMS_PROVIDER=vault
KMS_VAULT_URL=https://vault.company.com:8200
KMS_VAULT_TOKEN=hvs.your-vault-token

# Cosmian KMS (for FIPS/confidential computing)
KMS_PROVIDER=cosmian
```

### Key Rotation Procedure

1. Generate a new KEK through the encryption settings API
2. Re-wrap all existing DEKs with the new KEK (background task)
3. Verify all document decryption still works
4. Deactivate the old KEK

### Backup KEK Management

The backup KEK is isolated from production to prevent cross-contamination:

```bash
# Backup KEK is managed via BackupKEKManager
# It uses the same KMS provider but maintains a separate key hierarchy
# Never use the same KEK for production and backup encryption
```

---

## Prompt Injection Alert Handling

When the PromptGuard detects a prompt injection attempt:

1. **Alert Generated** - A SecurityAlert record is created with:
   - `alert_type`: "prompt_injection"
   - `severity`: "medium" or "high" depending on pattern
   - Pattern name and matched text in `details_json`

2. **Response Procedure:**
   ```bash
   # Check recent prompt injection alerts
   curl "http://localhost:8000/api/security/alerts?limit=50" \
     -H "Authorization: Bearer $TOKEN" | jq '.[] | select(.alert_type == "prompt_injection")'
   ```

3. **Investigation:**
   - Review the `source` field (e.g., "chat_message", "document_content")
   - Check the `details_json.matched_text` to understand the attempt
   - Determine if the pattern is a false positive (legitimate text that matches patterns)

4. **Resolution:**
   - If false positive: acknowledge the alert
   - If genuine attack: review the user's recent activity, consider account suspension
   - If via document content: review the uploaded document for embedded attacks

---

## Circuit Breaker Tuning

The error handling system includes a circuit breaker pattern for external services (LLM, KMS):

When external services fail repeatedly:
- Requests fail fast instead of timing out
- The system enters a degraded mode
- Services are retried after a cooldown period

Monitor circuit breaker status in application logs. Look for `KMS_ERROR` or `PROCESSING_ERROR` error codes in responses.

---

## Health Monitoring Operations

### Scheduled Health Checks

Set up a cron job to run health checks and send digest emails:

```bash
# Daily health check at 7 AM
0 7 * * * curl -X POST http://localhost:8000/api/health/send-digest -H "Authorization: Bearer $SERVICE_TOKEN" 2>/dev/null
```

### Issue Types and Actions

| Issue Type | Severity | Action |
|-----------|----------|--------|
| expired_lifecycle | High | Renew or archive the document |
| broken_reviewer | High | Reassign reviewer |
| empty_group | Low | Remove group or add documents |
| stale_document | Medium | Retry processing or mark as failed |

---

## Multi-Tenant Operations

### Tenant Provisioning

Create and manage tenants through the API:

```bash
# Create a new tenant
curl -X POST http://localhost:8000/api/tenants \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "New Client", "slug": "new-client", "settings": {"max_storage_gb": 50}}'

# List all tenants
curl http://localhost:8000/api/tenants -H "Authorization: Bearer $TOKEN"

# Deactivate a tenant
curl -X PUT http://localhost:8000/api/tenants/1 \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"is_active": false}'
```

### Tenant Isolation Verification

Periodically verify tenant isolation is functioning:
1. Attempt cross-tenant data access (should return empty results)
2. Verify storage directories are separated per tenant
3. Check that tenant-scoped queries do not leak data

### Tenant Storage Management

Monitor per-tenant storage usage and enforce quotas defined in tenant settings:
```bash
# Check storage for each tenant directory
du -sh /data/edms/storage/tenant-*/
```

---

## Webhook Monitoring

### Monitoring Webhook Delivery

Track webhook delivery status and failures:

```bash
# List configured webhooks
curl http://localhost:8000/api/webhooks -H "Authorization: Bearer $TOKEN"

# Test a webhook endpoint
curl -X POST http://localhost:8000/api/webhooks/1/test -H "Authorization: Bearer $TOKEN"
```

### Common Webhook Issues

| Issue | Symptom | Resolution |
|-------|---------|------------|
| Endpoint unreachable | Delivery timeouts | Check destination URL, firewall rules |
| Invalid signature | 401/403 from receiver | Verify secret matches on both sides |
| Payload too large | 413 from receiver | Reduce event data or paginate |
| Rate limiting by receiver | 429 responses | Implement exponential backoff |

### Webhook Secret Rotation

To rotate a webhook secret without downtime:
1. Update the webhook config with a new secret
2. Configure the receiver to accept both old and new signatures temporarily
3. Once all pending deliveries with old secret are processed, remove old secret from receiver

```bash
curl -X PUT http://localhost:8000/api/webhooks/1 \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"secret": "new-rotated-secret-value"}'
```

---

## SLA Breach Escalation

### Monitoring SLA Status

Regularly check SLA compliance across the system:

```bash
# Check SLA dashboard
curl http://localhost:8000/api/sla/dashboard -H "Authorization: Bearer $TOKEN"
```

### Automated SLA Monitoring

Set up a cron job to check SLA status and trigger escalations:

```bash
# Every 15 minutes, check for SLA breaches
*/15 * * * * curl -X POST http://localhost:8000/api/sla/check \
  -H "Authorization: Bearer $SERVICE_TOKEN" 2>/dev/null
```

### Escalation Procedure

When an SLA is breached:
1. The system sets `status = breached` and `escalated = true`
2. Notifications are sent to users with the `escalation_role`
3. A webhook event `sla.breached` is emitted (if webhooks configured)
4. The SLA dashboard reflects the breach with high visibility

### Resolving SLA Issues

- For false positives: Review and adjust `max_duration_hours` on the policy
- For systemic delays: Add more approvers or reduce required approval steps
- For recurring breaches: Consider splitting the workflow or delegating authority

---

## Geo-Fence Rule Management

### Reviewing Active Rules

```bash
curl http://localhost:8000/api/geofence/rules -H "Authorization: Bearer $TOKEN"
```

### Emergency Rule Disablement

If geo-fencing is blocking legitimate users:

```bash
# Disable a specific rule
curl -X PUT http://localhost:8000/api/geofence/rules/1 \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"enabled": false}'
```

### Audit Geo-Fence Denials

Check application logs for geo-fence block events. The middleware logs:
- Client IP that was blocked
- Which rule triggered the block
- The requested resource

### Best Practices

1. Always test rules with a non-critical scope before applying globally
2. Maintain a list of known office IP ranges
3. Use `allowed_countries` rather than `denied_countries` for sensitive resources
4. Keep a "break glass" admin account that bypasses geo-fencing

---

## Health Score Thresholds

### Understanding the Health Score

The composite health score (0-100) is computed from six components:

| Component | Weight | What it measures |
|-----------|--------|-----------------|
| orphan | 0.15 | Documents without valid relationships or groups |
| lifecycle | 0.20 | Expired/stuck lifecycle states |
| backup | 0.20 | Backup recency and success rate |
| security | 0.20 | Security alert count, unacknowledged alerts |
| storage | 0.15 | Disk utilization, failed processing ratio |
| sla | 0.10 | SLA compliance percentage |

### Alert Thresholds

| Score Range | Status | Action |
|-------------|--------|--------|
| 90-100 | Healthy | No action needed |
| 70-89 | Warning | Review components below 80 |
| 50-69 | Degraded | Investigate and remediate |
| 0-49 | Critical | Immediate intervention required |

### Viewing History

```bash
curl "http://localhost:8000/api/health/score/history?days=30" \
  -H "Authorization: Bearer $TOKEN"
```

Track trends to identify gradual degradation before it becomes critical.

---

## Scheduled Report Troubleshooting

### Report Not Generating

1. Verify the report is active:
   ```bash
   curl http://localhost:8000/api/reports -H "Authorization: Bearer $TOKEN"
   ```
2. Check the cron schedule is valid (use crontab.guru to validate)
3. Verify SMTP is configured (reports are delivered via email)
4. Check that recipient email addresses are valid

### Report Content Issues

- Empty reports: Verify the filter criteria match actual data
- Stale data: Ensure the cron schedule fires at the expected time
- Missing recipients: Check the `recipients` JSON array for valid addresses

### Manual Trigger for Testing

```bash
curl -X POST http://localhost:8000/api/reports/1/trigger \
  -H "Authorization: Bearer $TOKEN"
```

This immediately generates and sends the report, useful for testing configuration.
