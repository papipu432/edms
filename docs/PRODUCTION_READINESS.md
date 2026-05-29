# Production Readiness Guide

Complete checklist and recommendations for deploying EDMS to production environments.

## Table of Contents

1. [Pre-Deployment Checklist](#pre-deployment-checklist)
2. [Security Hardening](#security-hardening)
3. [Performance Optimization](#performance-optimization)
4. [High Availability Setup](#high-availability-setup)
5. [Monitoring & Alerting](#monitoring--alerting)
6. [Backup & Disaster Recovery](#backup--disaster-recovery)
7. [Compliance Considerations](#compliance-considerations)
8. [Post-Deployment Validation](#post-deployment-validation)

---

## Pre-Deployment Checklist

### Infrastructure Requirements

| Component | Minimum | Recommended | Notes |
|-----------|---------|-------------|-------|
| CPU | 2 cores | 4+ cores | More for LLM processing |
| RAM | 4 GB | 8+ GB | ChromaDB is memory-intensive |
| Storage | 50 GB SSD | 500 GB+ NVMe | Depends on document volume |
| Network | 1 Gbps | 10 Gbps | For large file transfers |

### Software Dependencies

```bash
# Required system packages
apt-get install -y \
    tesseract-ocr \
    tesseract-ocr-eng \
    libgl1-mesa-glx \
    libglib2.0-0 \
    redis-server \
    postgresql-client

# Python dependencies (via uv)
uv sync --no-dev
```

### Environment Variables Audit

**Critical Security Variables:**
```bash
# Must be changed from defaults
SECRET_KEY=<64+ random characters>
PDF_ENCRYPTION_PASSWORD=<strong password>
DATABASE_URL=postgresql+async://user:pass@host/db
MINIO_ENDPOINT=s3.yourcompany.com
MINIO_ACCESS_KEY=<access key>
MINIO_SECRET_KEY=<secret key>

# KMS Configuration
KMS_PROVIDER=vault  # or cosmian, local_file
VAULT_URL=https://vault.yourcompany.com
VAULT_TOKEN=<approle token>

# LDAP (if enabled)
LDAP_BIND_DN=cn=edms,ou=services,dc=company,dc=com
LDAP_BIND_PASSWORD=<encrypted password>

# Email Notifications
SMTP_HOST=smtp.yourcompany.com
SMTP_USER=edms@yourcompany.com
SMTP_PASSWORD=<app password>
```

**Feature Toggles:**
```bash
ALLOW_REGISTRATION=false
LDAP_ENABLED=true
BACKUP_ENABLED=true
RANSOMWARE_DETECTION_ENABLED=true
PROMPT_INJECTION_PROTECTION=true
GEOFENCING_ENABLED=true
```

---

## Security Hardening

### 1. Network Security

#### Reverse Proxy Configuration (Nginx)

```nginx
server {
    listen 443 ssl http2;
    server_name edms.yourcompany.com;

    # TLS 1.3 only
    ssl_protocols TLSv1.3;
    ssl_ciphers TLS_AES_256_GCM_SHA384:TLS_CHACHA20_POLY1305_SHA256;
    ssl_prefer_server_ciphers off;

    # Certificate
    ssl_certificate /etc/ssl/certs/edms.crt;
    ssl_certificate_key /etc/ssl/private/edms.key;

    # Security headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "DENY" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self'; connect-src 'self' ws: wss:;" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    add_header Permissions-Policy "geolocation=(), microphone=(), camera=()" always;

    # Rate limiting
    limit_req_zone $binary_remote_addr zone=api_limit:10m rate=10r/s;
    limit_req zone=api_limit burst=20 nodelay;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # Timeouts
        proxy_connect_timeout 60s;
        proxy_send_timeout 120s;
        proxy_read_timeout 120s;
        
        # File upload size
        client_max_body_size 500M;
    }

    # Block sensitive paths
    location ~ /\. {
        deny all;
    }
}
```

#### Firewall Rules (UFW Example)

```bash
# Allow only necessary ports
ufw default deny incoming
ufw default allow outgoing

# SSH (restrict to admin IPs)
ufw allow from 10.0.0.0/8 to any port 22

# HTTPS
ufw allow 443/tcp

# If using separate monitoring
ufw allow from 10.0.0.0/8 to any port 9090  # Prometheus
```

### 2. Application Security

#### Enable All Security Features

```bash
# In .env or config
RANSOMWARE_DETECTION_ENABLED=true
RANSOMWARE_THRESHOLD_OPS_PER_SEC=50
RANSOMWARE_WINDOW_SECONDS=10

PROMPT_INJECTION_PROTECTION=true

GEOFENCING_ENABLED=true
# Configure allowed IP ranges in UI or API

KMS_RATE_LIMIT_MAX_CALLS=10
KMS_RATE_LIMIT_WINDOW_SECONDS=60

# Session security
SESSION_EXPIRE_MINUTES=30
MAX_LOGIN_ATTEMPTS=5
LOCKOUT_DURATION_MINUTES=15
```

#### Database Security

```sql
-- Create dedicated database user with minimal privileges
CREATE USER edms_app WITH PASSWORD '<strong_password>';
GRANT CONNECT ON DATABASE edms TO edms_app;
GRANT USAGE ON SCHEMA public TO edms_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO edms_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO edms_app;

-- Revoke dangerous permissions
REVOKE CREATE ON SCHEMA public FROM edms_app;
REVOKE ALL ON DATABASE edms FROM edms_app;
```

#### Secret Management

**DO NOT store secrets in .env files in production.** Use one of:

1. **HashiCorp Vault** (Recommended)
```bash
# Mount secrets engine
vault secrets enable -path=edms kv-v2

# Store secrets
vault kv put edms/config \
    secret_key="..." \
    pdf_encryption_password="..." \
    database_url="..."

# App reads via Vault agent or API
```

2. **Kubernetes Secrets**
```yaml
apiVersion: v1
kind: Secret
metadata:
  name: edms-secrets
type: Opaque
stringData:
  SECRET_KEY: "..."
  PDF_ENCRYPTION_PASSWORD: "..."
```

3. **AWS Secrets Manager**
```python
import boto3
client = boto3.client('secretsmanager')
response = client.get_secret_value(SecretId='edms/production')
```

### 3. User Access Control

#### Mandatory RBAC Configuration

1. **Disable default admin account or change credentials immediately**
```bash
# After first login as admin
curl -X PUT http://localhost:8000/api/users/admin/password \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"current_password": "admin", "new_password": "<strong_password>"}'
```

2. **Create role-based accounts**
```bash
# Create manager account
curl -X POST http://localhost:8000/api/users \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -d '{
    "username": "org_manager",
    "email": "manager@company.com",
    "full_name": "Organization Manager",
    "password": "<strong_password>",
    "roles": ["manager"]
  }'
```

3. **Enable MFA for admin accounts** (Future enhancement)
   - Plan to implement TOTP/WebAuthn

#### Organizational Structure Best Practices

1. **Define clear hierarchy before adding users**
   - Use drag-drop org chart builder at `/org/chart`
   - Establish escalation paths for auto-reassignment

2. **Configure automatic reassignment rules**
   - When user status changes to resigned/terminated/MIA
   - Tasks automatically escalate to position head → parent unit → admin

3. **Regular access reviews**
   - Monthly review of role assignments
   - Quarterly review of folder-level permissions

---

## Performance Optimization

### 1. Database Tuning

#### PostgreSQL Configuration (postgresql.conf)

```conf
# Memory settings
shared_buffers = 2GB           # 25% of RAM
effective_cache_size = 6GB     # 75% of RAM
work_mem = 64MB                # Per-operation memory
maintenance_work_mem = 512MB   # For VACUUM, CREATE INDEX

# Connection settings
max_connections = 100
superuser_reserved_connections = 3

# WAL settings
wal_buffers = 64MB
checkpoint_completion_target = 0.9

# Query logging (for slow query analysis)
log_min_duration_statement = 1000  # Log queries > 1 second
```

#### Index Optimization

```sql
-- Ensure critical indexes exist
CREATE INDEX IF NOT EXISTS idx_documents_group_id ON documents(group_id);
CREATE INDEX IF NOT EXISTS idx_documents_lifecycle_state ON documents(lifecycle_state);
CREATE INDEX IF NOT EXISTS idx_documents_created_at ON documents(created_at);
CREATE INDEX IF NOT EXISTS idx_workflow_entries_document_id ON workflow_entries(document_id);
CREATE INDEX IF NOT EXISTS idx_workflow_entries_stage_id ON workflow_entries(stage_id);
CREATE INDEX IF NOT EXISTS idx_users_status ON users(status);
CREATE INDEX IF NOT EXISTS idx_org_units_parent_id ON org_units(parent_id);

-- Analyze tables for query planner
ANALYZE documents;
ANALYZE workflow_entries;
ANALYZE users;
```

### 2. Caching Strategy

#### Redis Cache Configuration

```bash
# Install and configure Redis
apt-get install redis-server

# Edit /etc/redis/redis.conf
maxmemory 2gb
maxmemory-policy allkeys-lru
appendonly yes
appendfsync everysec
```

#### Application-Level Caching

```python
# Cache frequently accessed data
from functools import lru_cache
import asyncio

@lru_cache(maxsize=1000)
def get_org_structure():
    # Cache org chart for 5 minutes
    pass

# Use Redis for shared cache in multi-worker setups
import redis
redis_client = redis.Redis(host='localhost', port=6379, db=0)

async def get_cached_user_roles(user_id):
    cached = redis_client.get(f"user_roles:{user_id}")
    if cached:
        return json.loads(cached)
    # Fetch from DB and cache for 10 minutes
    roles = await fetch_user_roles(user_id)
    redis_client.setex(f"user_roles:{user_id}", 600, json.dumps(roles))
    return roles
```

### 3. Async Processing

#### Celery Task Queue Setup

```bash
# Install Celery with Redis broker
pip install celery[redis]

# Start Celery worker
celery -A app.celery worker --loglevel=info --concurrency=4

# Start Celery beat for scheduled tasks
celery -A app.celery beat --loglevel=info
```

#### Background Tasks Configuration

```python
# tasks that should run async
- Document processing pipeline (OCR, embedding, wiki ingest)
- Backup operations
- Ransomware detection monitoring
- Email notifications
- LDAP synchronization
- Report generation
- Vector index rebuilding
```

### 4. Vector Database Optimization

#### ChromaDB Performance Tuning

```python
# Collection settings for better performance
collection = client.create_collection(
    name="documents",
    metadata={
        "hnsw:space": "cosine",
        "hnsw:construction_ef": 128,
        "hnsw:search_ef": 64,
        "hnsw:M": 16
    }
)

# Batch insert instead of individual
collection.add(
    embeddings=batch_embeddings,  # List of embeddings
    documents=batch_texts,
    ids=batch_ids,
    metadatas=batch_metadata
)
```

---

## High Availability Setup

### Architecture Overview

```
                    ┌─────────────┐
                    │   Load      │
                    │   Balancer  │
                    │   (HAProxy) │
                    └──────┬──────┘
                           │
          ┌────────────────┼────────────────┐
          │                │                │
    ┌─────▼─────┐   ┌─────▼─────┐   ┌─────▼─────┐
    │  EDMS     │   │  EDMS     │   │  EDMS     │
    │  Node 1   │   │  Node 2   │   │  Node 3   │
    └─────┬─────┘   └─────┬─────┘   └─────┬─────┘
          │               │               │
          └───────────────┼───────────────┘
                          │
              ┌───────────┴───────────┐
              │                       │
        ┌─────▼─────┐         ┌─────▼─────┐
        │ PostgreSQL│         │   MinIO   │
        │  Primary  │────────▶│  Cluster  │
        └─────┬─────┘         └───────────┘
              │
        ┌─────▼─────┐
        │ PostgreSQL│
        │  Replica  │
        └───────────┘
```

### Load Balancer Configuration (HAProxy)

```haproxy
global
    log /dev/log local0
    maxconn 4096
    daemon

defaults
    log global
    mode http
    option httplog
    option dontlognull
    timeout connect 5000ms
    timeout client 50000ms
    timeout server 50000ms
    retries 3

frontend edms_frontend
    bind *:80
    bind *:443 ssl crt /etc/haproxy/certs/edms.pem
    http-request redirect scheme https unless { ssl_fc }
    
    # Health check endpoint
    acl health_check path /health
    
    use_backend edms_servers if !health_check
    backend edms_health
        server health_check localhost:8000 check

backend edms_servers
    balance roundrobin
    option httpchk GET /docs
    http-check expect status 200
    
    server edms1 10.0.1.10:8000 check inter 5s fall 3 rise 2
    server edms2 10.0.1.11:8000 check inter 5s fall 3 rise 2
    server edms3 10.0.1.12:8000 check inter 5s fall 3 rise 2
```

### Database Replication

#### PostgreSQL Streaming Replication Setup

```bash
# On primary server
# postgresql.conf
wal_level = replica
max_wal_senders = 3
wal_keep_size = 1GB

# pg_hba.conf
host replication replicator 10.0.1.0/24 md5

# On replica server
pg_basebackup -h primary_host -U replicator -D /var/lib/postgresql/data -Fp -Xs -P -R
```

### Session Stickiness (Optional)

For WebSocket connections, enable sticky sessions:

```haproxy
backend edms_servers
    balance source
    cookie SERVERID insert indirect nocache
    
    server edms1 10.0.1.10:8000 check cookie s1
    server edms2 10.0.1.11:8000 check cookie s2
    server edms3 10.0.1.12:8000 check cookie s3
```

---

## Monitoring & Alerting

### Metrics to Monitor

| Category | Metric | Threshold | Alert Level |
|----------|--------|-----------|-------------|
| Application | Request latency p95 | > 500ms | Warning |
| Application | Request latency p99 | > 2s | Critical |
| Application | Error rate | > 1% | Warning |
| Application | Error rate | > 5% | Critical |
| Database | Connection pool usage | > 80% | Warning |
| Database | Query duration | > 1s | Warning |
| Database | Replication lag | > 30s | Critical |
| Storage | Disk usage | > 80% | Warning |
| Storage | Disk usage | > 95% | Critical |
| Backup | Last successful backup | > 24h | Critical |
| Security | Failed login attempts | > 10/min | Warning |
| Security | Ransomware alerts | Any | Critical |
| Security | KMS rate limit hits | > 5/min | Warning |

### Prometheus Configuration

```yaml
# prometheus.yml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'edms'
    static_configs:
      - targets: ['edms1:8000', 'edms2:8000', 'edms3:8000']
    metrics_path: '/metrics'
    
  - job_name: 'postgres'
    static_configs:
      - targets: ['postgres-exporter:9187']
      
  - job_name: 'redis'
    static_configs:
      - targets: ['redis-exporter:9121']
```

### Grafana Dashboard Panels

Create dashboards for:
1. **Application Health**: Request rates, latency, error rates
2. **Database Performance**: Queries/sec, connection usage, replication lag
3. **Storage Metrics**: Disk usage, I/O operations, backup status
4. **Security Monitoring**: Failed logins, ransomware alerts, KMS activity
5. **Business Metrics**: Documents uploaded, workflows completed, active users

### Alert Rules (Prometheus)

```yaml
# alert_rules.yml
groups:
  - name: edms_alerts
    rules:
      - alert: HighErrorRate
        expr: rate(http_requests_total{status=~"5.."}[5m]) / rate(http_requests_total[5m]) > 0.05
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "High error rate detected"
          
      - alert: BackupStale
        expr: time() - backup_last_successful_timestamp > 86400
        for: 0m
        labels:
          severity: critical
        annotations:
          summary: "No successful backup in 24 hours"
          
      - alert: RansomwareDetected
        expr: ransomware_alerts_total > 0
        for: 0m
        labels:
          severity: critical
        annotations:
          summary: "Ransomware behavior detected"
```

### Health Check Endpoints

```bash
# Basic health check
GET /health
# Returns: {"status": "healthy", "timestamp": "..."}

# Detailed health dashboard
GET /health/dashboard
# Returns: Component-by-component health status

# Health score (0-100)
GET /health/score
# Returns: {"score": 95, "breakdown": {...}}
```

---

## Backup & Disaster Recovery

### Backup Strategy

#### 3-2-1 Rule Implementation

- **3 copies** of data (production + 2 backups)
- **2 different media** (disk + object storage)
- **1 offsite copy** (DR site or cloud)

#### Backup Schedule

| Data Type | Frequency | Retention | Method |
|-----------|-----------|-----------|--------|
| Database | Hourly | 7 days | pg_dump + WAL archiving |
| Database | Daily | 30 days | Full dump |
| Database | Weekly | 1 year | Full dump + verification |
| Documents | Continuous | N/A | MinIO versioning |
| Documents | Daily | 30 days | Restic snapshot |
| Wiki | Daily | 30 days | Git repository |
| Config | On change | 90 days | Git repository |

### Restic Backup Configuration

```bash
# Initialize repository
restic init --repo s3:s3.yourcompany.com/edms-backup-primary

# Set up automated backup script
#!/bin/bash
# /usr/local/bin/edms-backup.sh

set -e

REPO_PRIMARY="s3:s3.yourcompany.com/edms-backup-primary"
REPO_DR="s3:s3-dr.yourcompany.com/edms-backup-dr"
STORAGE_PATH="/app/storage"
DB_DUMP_PATH="/tmp/edms-db-dump.sql"

# Dump database
pg_dump -h db_host -U edms_app edms > $DB_DUMP_PATH

# Backup to primary
restic -r $REPO_PRIMARY backup $STORAGE_PATH $DB_DUMP_PATH

# Backup to DR
restic -r $REPO_DR backup $STORAGE_PATH $DB_DUMP_PATH

# Prune old snapshots
restic -r $REPO_PRIMARY forget --keep-daily 7 --keep-weekly 4 --keep-monthly 12 --prune
restic -r $REPO_DR forget --keep-daily 7 --keep-weekly 4 --keep-monthly 12 --prune

# Verify latest snapshot
restic -r $REPO_PRIMARY check --last
```

#### Cron Schedule

```cron
# EDMS backup schedule
0 * * * * /usr/local/bin/edms-backup-hourly.sh  # Hourly DB dump
0 2 * * * /usr/local/bin/edms-backup-daily.sh   # Daily full backup
0 3 * * 0 /usr/local/bin/edms-backup-weekly.sh  # Weekly verification
```

### Disaster Recovery Procedures

#### RTO/RPO Targets

| Scenario | RTO (Recovery Time) | RPO (Recovery Point) |
|----------|---------------------|----------------------|
| Single node failure | < 5 minutes | 0 (HA setup) |
| Database corruption | < 1 hour | < 1 hour |
| Site disaster | < 4 hours | < 24 hours |
| Ransomware attack | < 2 hours | Last clean backup |

#### DR Failover Procedure

1. **Assess damage**: Identify scope of failure
2. **Activate DR site**: Power on DR infrastructure
3. **Restore database**: From latest verified backup
4. **Restore documents**: From Restic snapshot
5. **Update DNS**: Point to DR site
6. **Verify functionality**: Run smoke tests
7. **Notify stakeholders**: Communication plan
8. **Document incident**: Post-mortem preparation

#### Backup Verification

```bash
# Monthly backup restoration test
#!/bin/bash

TEST_DIR="/tmp/backup-test-$(date +%Y%m%d)"
mkdir -p $TEST_DIR

# Restore latest snapshot
restic -r $REPO_PRIMARY restore latest --target $TEST_DIR

# Verify database dump
pg_restore -l $TEST_DIR/edms-db-dump.sql > /dev/null

# Verify document count
DOC_COUNT=$(find $TEST_DIR/storage -type f | wc -l)
echo "Restored $DOC_COUNT documents"

# Cleanup
rm -rf $TEST_DIR

# Log result
echo "$(date): Backup verification successful" >> /var/log/edms/backup-verification.log
```

---

## Compliance Considerations

### Data Protection (GDPR, CCPA)

#### Right to Erasure

```python
# Implement soft delete with retention period
# Hard delete after retention expires

@app.delete("/api/documents/{doc_id}")
async def delete_document(doc_id: int, current_user: User = Depends(get_current_user)):
    doc = await get_document(doc_id)
    
    # Mark for deletion
    doc.deleted_at = datetime.utcnow()
    doc.deleted_by = current_user.id
    
    # Schedule hard delete after retention period
    retention_days = get_retention_period(doc.group_id)
    schedule_hard_delete(doc_id, days=retention_days)
    
    return {"message": "Document marked for deletion"}
```

#### Data Portability

```bash
# Export all user data
GET /api/users/{user_id}/export

# Returns ZIP containing:
# - Uploaded documents
# - Comments and annotations
# - Workflow history
# - Audit trail entries
# - Profile information
```

#### Consent Management

- Document consent for processing in privacy policy
- Log consent timestamps
- Allow consent withdrawal
- Respect do-not-process requests

### Audit Trail Requirements

| Requirement | Implementation |
|-------------|----------------|
| Immutable logs | Append-only audit_log table |
| Tamper detection | Hash chain validation |
| Retention | 7 years minimum |
| Search capability | Full-text search on audit logs |
| Export format | JSON, CSV, PDF reports |

### Access Logging

All access must be logged:
- Who accessed what document
- When and from where (IP)
- What action was performed
- Result of the action

```sql
-- Audit log query for compliance report
SELECT 
    al.timestamp,
    u.username,
    d.title as document_title,
    al.action,
    al.ip_address,
    al.result
FROM audit_log al
JOIN users u ON al.user_id = u.id
JOIN documents d ON al.document_id = d.id
WHERE al.timestamp BETWEEN :start_date AND :end_date
ORDER BY al.timestamp;
```

---

## Post-Deployment Validation

### Smoke Tests

```bash
#!/bin/bash
# /usr/local/bin/edms-smoke-test.sh

BASE_URL="https://edms.yourcompany.com"
TOKEN=$(curl -s -X POST $BASE_URL/api/auth/login \
  -d "username=admin&password=<test_password>" \
  | jq -r '.access_token')

echo "Running EDMS smoke tests..."

# Test 1: Health check
echo -n "Health check... "
curl -s $BASE_URL/health | jq -r '.status' | grep -q "healthy" && echo "✓" || echo "✗"

# Test 2: List documents
echo -n "List documents... "
curl -s -H "Authorization: Bearer $TOKEN" $BASE_URL/api/documents | jq -r '.documents' | grep -q "\[" && echo "✓" || echo "✗"

# Test 3: Upload document
echo -n "Upload document... "
curl -s -X POST -H "Authorization: Bearer $TOKEN" \
  -F "file=@/tmp/test.pdf" \
  -F "title=Smoke Test Document" \
  -F "group_id=1" \
  $BASE_URL/api/documents/upload | jq -r '.id' | grep -q "[0-9]" && echo "✓" || echo "✗"

# Test 4: Create workflow
echo -n "Create workflow... "
curl -s -X POST -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"document_id": 1, "stage_id": 1}' \
  $BASE_URL/api/workflow/documents/1/move | jq -r '.success' | grep -q "true" && echo "✓" || echo "✗"

# Test 5: Org chart access
echo -n "Org chart access... "
curl -s -H "Authorization: Bearer $TOKEN" $BASE_URL/org/chart | grep -q "Organizational Chart" && echo "✓" || echo "✗"

# Test 6: Kanban board
echo -n "Kanban board... "
curl -s -H "Authorization: Bearer $TOKEN" $BASE_URL/workflow/kanban | grep -q "Kanban Board" && echo "✓" || echo "✗"

# Test 7: Backup status
echo -n "Backup status... "
curl -s -H "Authorization: Bearer $TOKEN" $BASE_URL/api/backup/status | jq -r '.last_backup' | grep -q "[0-9]" && echo "✓" || echo "✗"

# Test 8: Ransomware detection
echo -n "Ransomware detection... "
curl -s -H "Authorization: Bearer $TOKEN" $BASE_URL/api/security/monitor/status | jq -r '.monitoring' | grep -q "true" && echo "✓" || echo "✗"

echo "Smoke tests complete!"
```

### Performance Benchmarks

Run load tests to verify performance:

```bash
# Install k6
sudo apt-get install k6

# Run load test
k6 run tests/load/smoke_test.js

# Expected results:
# - HTTP request duration p(95): < 500ms
# - HTTP request duration p(99): < 2s
# - Failed requests: < 0.1%
```

### Security Validation

```bash
# Run security scan
npm install -g @owasp/zap2docker-stable
zap-baseline.py -t https://edms.yourcompany.com

# Check SSL configuration
testssl.sh edms.yourcompany.com

# Verify security headers
curl -I https://edms.yourcompany.com | grep -E "(Strict-Transport-Security|X-Content-Type-Options|X-Frame-Options|Content-Security-Policy)"
```

### User Acceptance Testing Checklist

- [ ] Users can log in with LDAP credentials
- [ ] Organizational chart displays correctly with drag-drop
- [ ] Users can upload documents to assigned folders
- [ ] Workflow kanban board functions with drag-drop moves
- [ ] Flow notes appear after workflow stage changes
- [ ] Auto-reassignment triggers on user status change
- [ ] Ransomware detection alerts on suspicious activity
- [ ] Backups complete successfully per schedule
- [ ] Search returns relevant results
- [ ] PDF preview renders correctly
- [ ] Mobile responsiveness acceptable
- [ ] Accessibility features functional (WCAG 2.1 AA)

---

## Maintenance Schedule

### Daily Tasks

- [ ] Review backup logs
- [ ] Check disk space usage
- [ ] Monitor error logs
- [ ] Review security alerts

### Weekly Tasks

- [ ] Review slow query logs
- [ ] Check for software updates
- [ ] Review user access patterns
- [ ] Test backup restoration (sample)

### Monthly Tasks

- [ ] Full backup restoration test
- [ ] Security patch assessment
- [ ] Performance trend analysis
- [ ] Capacity planning review
- [ ] Access rights audit

### Quarterly Tasks

- [ ] Disaster recovery drill
- [ ] Penetration testing
- [ ] Compliance audit
- [ ] Documentation review
- [ ] Staff training refresh

---

## Support Contacts

| Role | Contact | Escalation Path |
|------|---------|-----------------|
| On-call Engineer | oncall@company.com | → Engineering Manager |
| Database Admin | dba@company.com | → Infrastructure Lead |
| Security Team | security@company.com | → CISO |
| Vendor Support | support@vendor.com | → Account Manager |

---

## Appendix: Troubleshooting Common Issues

### Issue: High Memory Usage

**Symptoms**: OOM killer activates, application crashes

**Diagnosis**:
```bash
free -h
ps aux --sort=-%mem | head -10
```

**Solutions**:
1. Increase `work_mem` in PostgreSQL config
2. Reduce ChromaDB collection size or batch sizes
3. Add swap space as temporary measure
4. Scale horizontally with more nodes

### Issue: Slow Document Uploads

**Symptoms**: Uploads timeout or take > 30 seconds

**Diagnosis**:
```bash
# Check network throughput
iperf3 -c server_ip

# Check disk I/O
iostat -x 1
```

**Solutions**:
1. Increase `client_max_body_size` in nginx
2. Use faster storage (NVMe SSD)
3. Enable HTTP/2 in reverse proxy
4. Implement chunked uploads for large files

### Issue: Workflow Stuck in Stage

**Symptoms**: Documents not progressing through workflow

**Diagnosis**:
```sql
SELECT * FROM workflow_entries WHERE stage_id = X AND updated_at < NOW() - INTERVAL '1 day';
```

**Solutions**:
1. Check assignee availability (not resigned/terminated)
2. Verify SLA escalation rules
3. Manually reassign using admin panel
4. Review auto-reassignment logs

### Issue: Backup Failures

**Symptoms**: Backup jobs fail consistently

**Diagnosis**:
```bash
restic -r $REPO check
tail -100 /var/log/edms/backup.log
```

**Solutions**:
1. Verify S3 credentials and connectivity
2. Check available disk space for temporary files
3. Increase backup timeout settings
4. Test manual backup execution

---

*Last Updated: $(date)*
*Version: 1.0*
