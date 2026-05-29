# Production Deployment Guide

Complete guide for deploying EDMS in production with Docker, Nginx, Fail2Ban, and security hardening.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Local Development Setup](#local-development-setup)
3. [Docker Production Deployment](#docker-production-deployment)
4. [Nginx Configuration](#nginx-configuration)
5. [Fail2Ban Setup](#fail2ban-setup)
6. [SSL/TLS Certificates](#ssl-tls-certificates)
7. [Backup Configuration](#backup-configuration)
8. [Monitoring & Health Checks](#monitoring--health-checks)
9. [Security Hardening](#security-hardening)
10. [Troubleshooting](#troubleshooting)

---

## Prerequisites

### System Requirements

- **CPU**: 4+ cores recommended (8+ for production)
- **RAM**: 8GB minimum (16GB+ recommended)
- **Storage**: 100GB+ SSD with LVM for expansion
- **OS**: Ubuntu 22.04 LTS, Debian 12, or RHEL 9
- **Docker**: 24.0+ with Docker Compose v2.20+

### Required Software

```bash
# Install Docker and Docker Compose
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER

# Install additional tools
sudo apt-get update && sudo apt-get install -y \
    fail2ban \
    certbot \
    python3-certbot-nginx \
    htop \
    iotop \
    net-tools
```

---

## Local Development Setup

### Quick Start (Development)

```bash
# Clone repository
git clone <repository-url> edms
cd edms

# Copy environment template
cp .env.example .env

# Edit .env with your settings
nano .env

# Start all services
docker-compose up -d

# Run setup wizard
docker-compose exec app python -m app.setup_wizard

# View logs
docker-compose logs -f
```

### Environment Configuration

Create `.env` file with these required variables:

```ini
# Database
DATABASE_URL=postgresql+asyncpg://edms:edms@postgres:5432/edms

# Security
SECRET_KEY=<generate-with: openssl rand -base64 32>
PDF_ENCRYPTION_PASSWORD=<generate-with: openssl rand -base64 32>
KMS_LOCAL_PASSPHRASE=<generate-with: openssl rand -base64 32>

# Admin User
BOOTSTRAP_ADMIN_USERNAME=admin
BOOTSTRAP_ADMIN_PASSWORD=<change-me>
BOOTSTRAP_ADMIN_EMAIL=admin@yourcompany.com

# Storage
STORAGE_PATH=/app/storage
WIKI_PATH=/app/wiki

# Redis
REDIS_URL=redis://redis:6379/0

# MinIO
MINIO_PRIMARY_ENDPOINT=http://minio:9000
MINIO_PRIMARY_ACCESS_KEY=minioadmin
MINIO_PRIMARY_SECRET_KEY=<change-me>
MINIO_PRIMARY_BUCKET=edms-documents

# ChromaDB
CHROMA_HOST=http://chromadb:8000

# LLM (Optional)
LLM_PROVIDER=openai
OPENAI_API_KEY=<your-key>

# SMTP (Optional for notifications)
SMTP_HOST=smtp.yourcompany.com
SMTP_PORT=587
SMTP_USER=notifications@yourcompany.com
SMTP_PASSWORD=<password>
SMTP_FROM_EMAIL=edms@yourcompany.com
```

---

## Docker Production Deployment

### Production Docker Compose

The `docker-compose.yml` includes:

- **app**: FastAPI application
- **postgres**: PostgreSQL 16 database
- **redis**: Redis cache and Celery broker
- **chromadb**: Vector database for semantic search
- **minio**: S3-compatible object storage
- **celery-worker**: Background task processor
- **celery-beat**: Scheduled task scheduler
- **nginx**: Reverse proxy with SSL termination

### Starting Production Stack

```bash
# Build images
docker-compose build --no-cache

# Start services
docker-compose up -d

# Verify all containers are running
docker-compose ps

# Check service health
docker-compose exec app curl http://localhost:8000/health
```

### Service Dependencies

```
nginx → app → postgres, redis, chromadb, minio
                      ↓
                  celery-worker, celery-beat
```

### Scaling Workers

For high-load environments:

```bash
# Scale celery workers
docker-compose up -d --scale celery-worker=3

# Scale application instances (requires external load balancer)
docker-compose up -d --scale app=2
```

---

## Nginx Configuration

### Enhanced Security Configuration

The nginx configuration includes:

#### Rate Limiting
- **API endpoints**: 30 requests/second with burst of 20
- **Auth endpoints**: 5 requests/second with burst of 10
- **Health checks**: No rate limiting

#### Security Headers
```nginx
add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
add_header X-Frame-Options "DENY" always;
add_header X-Content-Type-Options "nosniff" always;
add_header Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self' wss:" always;
add_header X-XSS-Protection "1; mode=block" always;
add_header Referrer-Policy "strict-origin-when-cross-origin" always;
```

#### TLS Configuration
- TLS 1.2 and 1.3 only
- Strong cipher suites (HIGH:!aNULL:!MD5)
- Server cipher preference enabled
- Session caching for performance

### Custom Server Block

Create `/workspace/nginx/conf.d/edms.conf`:

```nginx
server {
    listen 443 ssl http2;
    server_name edms.yourcompany.com;

    # SSL certificates
    ssl_certificate /etc/nginx/certs/fullchain.pem;
    ssl_certificate_key /etc/nginx/certs/privkey.pem;

    # Additional security
    add_header X-Robots-Tag "noindex, nofollow" always;
    
    # Logging
    access_log /var/log/nginx/edms_access.log;
    error_log /var/log/nginx/edms_error.log;

    # Proxy settings
    location / {
        proxy_pass http://app:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # Timeouts
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }
}
```

---

## Fail2Ban Setup

### Installation and Configuration

```bash
# Install fail2ban
sudo apt-get install -y fail2ban

# Create EDMS jail configuration
sudo tee /etc/fail2ban/jail.d/edms.conf > /dev/null << 'EOF'
[edms-nginx]
enabled = true
port = http,https
filter = edms-nginx
logpath = /var/log/nginx/edms_access.log
maxretry = 5
bantime = 3600
findtime = 600

[edms-auth]
enabled = true
port = http,https
filter = edms-auth
logpath = /var/log/nginx/edms_access.log
maxretry = 3
bantime = 7200
findtime = 300
EOF
```

### Custom Filters

Create `/etc/fail2ban/filter.d/edms-nginx.conf`:

```ini
[Definition]
failregex = ^<HOST> -.*"(GET|POST|PUT|DELETE).*HTTP/.*"\s(4\d{2}|5\d{2})$
ignoreregex =
```

Create `/etc/fail2ban/filter.d/edms-auth.conf`:

```ini
[Definition]
failregex = ^<HOST> -.*"(POST).*(/api/auth/|/login).*HTTP/.*"\s401$
            ^<HOST> -.*"(POST).*(/api/auth/|/login).*HTTP/.*"\s403$
ignoreregex =
```

### Enable and Start

```bash
# Restart fail2ban
sudo systemctl restart fail2ban

# Check status
sudo fail2ban-client status
sudo fail2ban-client status edms-nginx
sudo fail2ban-client status edms-auth
```

---

## SSL/TLS Certificates

### Using Let's Encrypt (Production)

```bash
# Stop nginx temporarily if running on port 80
docker-compose stop nginx

# Generate certificates with standalone mode
sudo certbot certonly --standalone \
    -d edms.yourcompany.com \
    --email admin@yourcompany.com \
    --agree-tos \
    --non-interactive

# Copy certificates to nginx directory
sudo cp /etc/letsencrypt/live/edms.yourcompany.com/fullchain.pem \
    /workspace/nginx/certs/server.crt
sudo cp /etc/letsencrypt/live/edms.yourcompany.com/privkey.pem \
    /workspace/nginx/certs/server.key

# Set permissions
sudo chmod 644 /workspace/nginx/certs/server.crt
sudo chmod 600 /workspace/nginx/certs/server.key

# Restart nginx
docker-compose restart nginx
```

### Auto-Renewal

```bash
# Add to crontab
sudo crontab -e

# Add this line for weekly renewal check
0 3 * * 0 certbot renew --quiet --post-hook "docker-compose restart nginx"
```

### Self-Signed Certificates (Development)

```bash
# Generate self-signed certificate
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
    -keyout /workspace/nginx/certs/server.key \
    -out /workspace/nginx/certs/server.crt \
    -subj "/C=US/ST=State/L=City/O=Organization/CN=localhost"

# Set permissions
chmod 644 /workspace/nginx/certs/server.crt
chmod 600 /workspace/nginx/certs/server.key
```

---

## Backup Configuration

### Automated Backups

EDMS includes automated backup with Restic:

```bash
# Configure backup in .env
BACKUP_ENABLED=true
BACKUP_SCHEDULE="0 2 * * *"  # Daily at 2 AM
BACKUP_RETENTION_DAYS=30

# Primary backup target (MinIO)
MINIO_BACKUP_ENDPOINT=http://minio:9000
MINIO_BACKUP_BUCKET=edms-backups
BACKUP_RESTIC_PASSWORD=<strong-password>

# DR backup target (optional)
BACKUP_DR_ENABLED=true
BACKUP_DR_ENDPOINT=s3.amazonaws.com
BACKUP_DR_BUCKET=edms-dr-backups
BACKUP_DR_ACCESS_KEY=<aws-access-key>
BACKUP_DR_SECRET_KEY=<aws-secret-key>
```

### Manual Backup

```bash
# Trigger immediate backup
docker-compose exec app python -m app.services.backup --full

# List available snapshots
docker-compose exec app python -m app.services.backup --list

# Restore from snapshot
docker-compose exec app python -m app.services.backup --restore <snapshot-id>
```

### Backup Verification

```bash
# Run backup integrity check
docker-compose exec app python -m app.services.backup --check

# Test restore in isolated environment
docker-compose exec app python -m app.services.backup --test-restore
```

---

## Monitoring & Health Checks

### Health Endpoints

EDMS provides comprehensive health monitoring:

- `GET /health` - Basic health check (load balancer ready)
- `GET /health/live` - Liveness probe (is service running?)
- `GET /health/ready` - Readiness probe (can service accept traffic?)
- `GET /metrics` - Prometheus metrics (restricted to internal IPs)

### Kubernetes Probes

Add to your deployment YAML:

```yaml
livenessProbe:
  httpGet:
    path: /health/live
    port: 8000
  initialDelaySeconds: 30
  periodSeconds: 10
  timeoutSeconds: 5
  failureThreshold: 3

readinessProbe:
  httpGet:
    path: /health/ready
    port: 8000
  initialDelaySeconds: 5
  periodSeconds: 5
  timeoutSeconds: 3
  failureThreshold: 3
```

### Log Aggregation

Configure log collection:

```bash
# Install Loki and Promtail (optional)
docker-compose -f docker-compose.monitoring.yml up -d

# Access Grafana at http://localhost:3000
# Default credentials: admin/admin
```

### Alerting Rules

Key metrics to monitor:

- API response time > 500ms
- Error rate > 1%
- Database connection pool exhaustion
- Disk usage > 80%
- Backup failures
- Ransomware detection alerts

---

## Security Hardening

### System-Level Hardening

```bash
# Disable root SSH login
sudo sed -i 's/^PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config

# Enable firewall
sudo ufw enable
sudo ufw allow 22/tcp    # SSH
sudo ufw allow 80/tcp    # HTTP
sudo ufw allow 443/tcp   # HTTPS
sudo ufw default deny incoming

# Automatic security updates
sudo apt-get install -y unattended-upgrades
sudo dpkg-reconfigure -plow unattended-upgrades
```

### Container Security

The Docker Compose includes security features:

- Non-root user execution
- Read-only root filesystem where possible
- Resource limits (CPU, memory)
- Network isolation
- Secret management via environment files

### Database Security

```sql
-- Connect to PostgreSQL
docker-compose exec postgres psql -U edms -d edms

-- Review user privileges
\du

-- Revoke unnecessary privileges
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
```

### Audit Logging

Enable comprehensive audit logging in `.env`:

```ini
AUDIT_LOG_ENABLED=true
AUDIT_LOG_RETENTION_DAYS=365
AUDIT_LOG_SENSITIVE_ACTIONS=true
SESSION_RECORDING_ENABLED=true
```

---

## Troubleshooting

### Common Issues

#### Application Won't Start

```bash
# Check logs
docker-compose logs app

# Verify database connection
docker-compose exec app python -c "from app.core.database import get_db; import asyncio; asyncio.run(get_db())"

# Check environment variables
docker-compose exec app env | grep -E "(DATABASE|SECRET|MINIO)"
```

#### High Memory Usage

```bash
# Check container resource usage
docker stats

# Inspect memory allocation
docker inspect edms-app-1 | grep -A 10 Memory

# Tune PostgreSQL shared buffers
docker-compose exec postgres psql -U edms -c "SHOW shared_buffers;"
```

#### Backup Failures

```bash
# Check backup logs
docker-compose logs celery-worker | grep -i backup

# Verify MinIO connectivity
docker-compose exec app python -c "from app.services.backup import BackupService; print(BackupService().list_snapshots())"

# Check disk space
docker-compose exec minio df -h
```

#### SSL Certificate Issues

```bash
# Verify certificate
openssl s_client -connect localhost:443 -servername localhost </dev/null 2>/dev/null | openssl x509 -noout -dates

# Check certificate chain
openssl s_client -connect localhost:443 -showcerts </dev/null 2>/dev/null
```

### Support Commands

```bash
# Full system diagnostic
docker-compose exec app python -m app.core.diagnostics

# Database migration status
docker-compose exec app alembic current

# Celery worker status
docker-compose exec celery-worker celery -A app.tasks inspect ping

# Redis connectivity
docker-compose exec redis redis-cli ping
```

---

## Performance Tuning

### PostgreSQL Optimization

```ini
# Add to postgresql.conf
shared_buffers = 256MB
effective_cache_size = 1GB
work_mem = 16MB
maintenance_work_mem = 128MB
max_connections = 100
```

### Redis Optimization

```ini
# Add to redis.conf
maxmemory 512mb
maxmemory-policy allkeys-lru
appendonly yes
```

### Application Tuning

```ini
# In .env for high-load environments
UVICORN_WORKERS=4
CELERYD_CONCURRENCY=8
DATABASE_POOL_SIZE=20
DATABASE_MAX_OVERFLOW=10
```

---

## Disaster Recovery

### Full System Restore

1. **Restore Database**:
```bash
docker-compose exec postgres pg_restore -U edms -d edms /backups/latest.dump
```

2. **Restore Object Storage**:
```bash
docker-compose exec app python -m app.services.backup --restore latest --include-blobs
```

3. **Restore Configuration**:
```bash
cp /backups/.env.backup .env
```

4. **Verify Integrity**:
```bash
docker-compose exec app python -m app.services.backup --verify-full
```

### Ransomware Recovery

If ransomware is detected:

1. **Isolate affected systems**
2. **Identify last clean backup** using `backup --list --verify`
3. **Restore from backup** preceding infection timestamp
4. **Rotate all credentials** (database, MinIO, API keys)
5. **Review audit logs** for attack vector
6. **Update security policies** based on findings

---

## Appendix: Complete File Checklist

Before going live, verify these files exist and are configured:

- [ ] `.env` - Environment configuration
- [ ] `docker-compose.yml` - Service orchestration
- [ ] `nginx/nginx.conf` - Nginx main configuration
- [ ] `nginx/conf.d/default.conf` - Server block configuration
- [ ] `nginx/certs/server.crt` - SSL certificate
- [ ] `nginx/certs/server.key` - SSL private key
- [ ] `/etc/fail2ban/jail.d/edms.conf` - Fail2Ban jail configuration
- [ ] `/etc/fail2ban/filter.d/edms-nginx.conf` - Nginx filter
- [ ] `/etc/fail2ban/filter.d/edms-auth.conf` - Auth filter
- [ ] `scripts/entrypoint.sh` - Container entrypoint
- [ ] `alembic.ini` - Database migration configuration

---

*Last updated: 2025*
*Version: 1.0.0*
