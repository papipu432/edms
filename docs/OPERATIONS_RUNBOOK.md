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
