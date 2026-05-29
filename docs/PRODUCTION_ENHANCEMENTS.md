# Production Enhancement Roadmap

## Executive Summary

This document outlines critical enhancements to make EDMS production-ready for enterprise deployment in airgap environments with maximum security, reliability, and usability.

---

## 🎯 Priority 0: Critical Production Gaps

### 1. **Health Check & Readiness Probes** ⚠️ MISSING

**Current State:** No standardized health endpoints for load balancers and orchestration.

**Implementation:**
```python
# app/api/health.py
from fastapi import APIRouter, status
from app.services.database import get_db_session
from app.services.kms import get_kms_client
from app.services.backup import BackupService
import asyncio

router = APIRouter()

@router.get("/health", tags=["Health"])
async def health_check():
    """Basic liveness probe - is the application running?"""
    return {"status": "healthy", "timestamp": datetime.utcnow()}

@router.get("/ready", tags=["Health"])
async def readiness_check():
    """Readiness probe - can the application serve traffic?"""
    checks = {}
    
    # Database connectivity
    try:
        async with get_db_session() as db:
            await db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = f"failed: {str(e)}"
    
    # KMS connectivity
    try:
        kms = get_kms_client()
        await kms.health_check()
        checks["kms"] = "ok"
    except Exception as e:
        checks["kms"] = f"failed: {str(e)}"
    
    # Storage connectivity (MinIO)
    try:
        from app.services.storage import get_minio_client
        client = get_minio_client()
        client.list_buckets()
        checks["storage"] = "ok"
    except Exception as e:
        checks["storage"] = f"failed: {str(e)}"
    
    # Vector database
    try:
        from app.services.vector_store import get_chroma_client
        client = get_chroma_client()
        client.heartbeat()
        checks["vector_db"] = "ok"
    except Exception as e:
        checks["vector_db"] = f"failed: {str(e)}"
    
    all_healthy = all(v == "ok" for v in checks.values())
    status_code = status.HTTP_200_OK if all_healthy else status.HTTP_503_SERVICE_UNAVAILABLE
    
    return {
        "status": "ready" if all_healthy else "not_ready",
        "checks": checks,
        "timestamp": datetime.utcnow()
    }

@router.get("/live", tags=["Health"])
async def liveness_check():
    """Liveness probe - is the application stuck?"""
    # Check for deadlocks, resource exhaustion
    import psutil
    
    cpu_percent = psutil.cpu_percent(interval=1)
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage('/')
    
    unhealthy_conditions = []
    
    if cpu_percent > 95:
        unhealthy_conditions.append(f"CPU at {cpu_percent}%")
    if memory.percent > 95:
        unhealthy_conditions.append(f"Memory at {memory.percent}%")
    if disk.percent > 98:
        unhealthy_conditions.append(f"Disk at {disk.percent}%")
    
    if unhealthy_conditions:
        return {
            "status": "unhealthy",
            "reasons": unhealthy_conditions,
            "timestamp": datetime.utcnow()
        }, status.HTTP_503_SERVICE_UNAVAILABLE
    
    return {"status": "alive", "timestamp": datetime.utcnow()}
```

**Kubernetes Integration:**
```yaml
# deployment.yaml
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
  initialDelaySeconds: 30
  periodSeconds: 10
  timeoutSeconds: 5
  failureThreshold: 3
```

---

### 2. **Graceful Shutdown & Signal Handling** ⚠️ MISSING

**Current State:** Application may terminate abruptly, losing in-progress operations.

**Implementation:**
```python
# app/main.py
import signal
import asyncio
from contextlib import asynccontextmanager

shutdown_event = asyncio.Event()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager with graceful shutdown."""
    # Startup
    logger.info("Starting EDMS application...")
    
    # Initialize background services
    from app.services.ransomware_detector import RansomwareDetector
    detector = RansomwareDetector()
    await detector.start_monitoring()
    
    from app.services.backup import BackupScheduler
    scheduler = BackupScheduler()
    await scheduler.start()
    
    yield
    
    # Shutdown
    logger.info("Initiating graceful shutdown...")
    shutdown_event.set()
    
    # Stop accepting new requests
    logger.info("Stopping background services...")
    
    # Wait for in-progress tasks (max 30 seconds)
    try:
        await asyncio.wait_for(detector.stop_monitoring(), timeout=10.0)
        await asyncio.wait_for(scheduler.stop(), timeout=10.0)
    except asyncio.TimeoutError:
        logger.warning("Shutdown timeout - forcing termination")
    
    # Close database connections
    from app.services.database import close_all_sessions
    await close_all_sessions()
    
    logger.info("Shutdown complete")

app = FastAPI(lifespan=lifespan)

# Signal handlers
def handle_signal(signum, frame):
    logger.info(f"Received signal {signum}, initiating shutdown")
    shutdown_event.set()

signal.signal(signal.SIGTERM, handle_signal)
signal.signal(signal.SIGINT, handle_signal)
```

---

### 3. **Database Migration System** ⚠️ CRITICAL

**Current State:** No automated schema migration system.

**Implementation using Alembic:**
```bash
# Install alembic
uv add alembic

# Initialize
alembic init alembic
```

```python
# alembic.ini
[alembic]
script_location = alembic
sqlalchemy.url = postgresql+async://user:pass@localhost/edms

[post_write_hooks]
hooks = black
black.type = console_scripts
black.entrypoint = black
black.options = -q
```

```python
# alembic/env.py
from logging.config import fileConfig
from sqlalchemy import pool
from sqlalchemy.engine import connection_from_env
from alembic import context
from app.models import Base  # Import all models

config = context.config
target_metadata = Base.metadata

def run_migrations_offline():
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online():
    """Run migrations in 'online' mode."""
    connectable = connection_from_env()
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata
        )
        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

**Migration Script Example:**
```python
# alembic/versions/001_add_workflow_stages.py
"""Add workflow stages table

Revision ID: 001
Revises: 
Create Date: 2025-01-29

"""
from alembic import op
import sqlalchemy as sa

revision = '001'
down_revision = None

def upgrade():
    op.create_table('workflow_stages',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('order', sa.Integer(), nullable=False),
        sa.Column('color', sa.String(length=20), nullable=True),
        sa.Column('is_default', sa.Boolean(), default=False),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Insert default stages
    op.bulk_insert(
        sa.table('workflow_stages',
            sa.column('name', sa.String()),
            sa.column('order', sa.Integer()),
            sa.column('color', sa.String()),
        ),
        [
            {'name': 'Draft', 'order': 1, 'color': 'gray'},
            {'name': 'In Review', 'order': 2, 'color': 'yellow'},
            {'name': 'Approved', 'order': 3, 'color': 'green'},
            {'name': 'Published', 'order': 4, 'color': 'blue'},
        ]
    )

def downgrade():
    op.drop_table('workflow_stages')
```

---

### 4. **Comprehensive Logging & Audit Trail** ⚠️ PARTIAL

**Enhancement:** Structured logging with correlation IDs.

```python
# app/core/logging_config.py
import logging
import json
from datetime import datetime
from uuid import uuid4
from contextvars import ContextVar

# Context variable for request correlation
request_id_var = ContextVar('request_id', default=None)

class JSONFormatter(logging.Formatter):
    """JSON formatter for structured logging."""
    
    def format(self, record):
        log_entry = {
            'timestamp': datetime.utcnow().isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'request_id': request_id_var.get(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno,
        }
        
        if record.exc_info:
            log_entry['exception'] = self.formatException(record.exc_info)
        
        if hasattr(record, 'extra_data'):
            log_entry.update(record.extra_data)
        
        return json.dumps(log_entry)

def setup_logging():
    """Configure application logging."""
    handler = logging.StreamHandler()
    handler.setFormatter(JSONFormatter())
    
    root_logger = logging.getLogger()
    root_logger.addHandler(handler)
    root_logger.setLevel(logging.INFO)
    
    # Reduce noise from third-party libraries
    logging.getLogger('uvicorn.access').setLevel(logging.WARNING)
    logging.getLogger('sqlalchemy.engine').setLevel(logging.WARNING)

# Middleware to add correlation IDs
# app/middleware/correlation_id.py
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

class CorrelationIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get('X-Correlation-ID', str(uuid4()))
        request_id_var.set(request_id)
        
        response = await call_next(request)
        response.headers['X-Correlation-ID'] = request_id
        
        return response

# Usage in main.py
app.add_middleware(CorrelationIDMiddleware)
```

**Audit Logging for Sensitive Operations:**
```python
# app/services/audit_logger.py
from app.models.audit import AuditLog
from sqlalchemy.ext.asyncio import AsyncSession

class AuditLogger:
    """Centralized audit logging service."""
    
    ACTION_CREATE = 'CREATE'
    ACTION_UPDATE = 'UPDATE'
    ACTION_DELETE = 'DELETE'
    ACTION_ACCESS = 'ACCESS'
    ACTION_APPROVE = 'APPROVE'
    ACTION_REJECT = 'REJECT'
    ACTION_LOGIN = 'LOGIN'
    ACTION_LOGOUT = 'LOGOUT'
    ACTION_PASSWORD_CHANGE = 'PASSWORD_CHANGE'
    ACTION_ROLE_ASSIGN = 'ROLE_ASSIGN'
    ACTION_STATUS_CHANGE = 'STATUS_CHANGE'
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def log(self, action: str, resource_type: str, resource_id: int,
                  user_id: int, details: dict = None, ip_address: str = None):
        """Record an audit log entry."""
        entry = AuditLog(
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            user_id=user_id,
            details=details or {},
            ip_address=ip_address,
            request_id=request_id_var.get()
        )
        
        self.db.add(entry)
        await self.db.commit()
    
    async def search(self, filters: dict, limit: int = 100, offset: int = 0):
        """Search audit logs with filters."""
        query = select(AuditLog)
        
        if 'user_id' in filters:
            query = query.where(AuditLog.user_id == filters['user_id'])
        if 'action' in filters:
            query = query.where(AuditLog.action == filters['action'])
        if 'resource_type' in filters:
            query = query.where(AuditLog.resource_type == filters['resource_type'])
        if 'date_from' in filters:
            query = query.where(AuditLog.timestamp >= filters['date_from'])
        if 'date_to' in filters:
            query = query.where(AuditLog.timestamp <= filters['date_to'])
        
        query = query.order_by(AuditLog.timestamp.desc())
        query = query.offset(offset).limit(limit)
        
        result = await self.db.execute(query)
        return result.scalars().all()
```

---

## 🎯 Priority 1: High-Impact Enhancements

### 5. **Multi-Factor Authentication (MFA)** 🔐

**Implementation Plan:**
```python
# app/services/mfa.py
import pyotp
import qrcode
from io import BytesIO
import base64

class MFAService:
    """TOTP-based multi-factor authentication."""
    
    def __init__(self, secret_key: str):
        self.secret_key = secret_key
    
    def generate_secret(self) -> str:
        """Generate a new TOTP secret."""
        return pyotp.random_base32()
    
    def get_provisioning_uri(self, username: str, secret: str, issuer: str = "EDMS") -> str:
        """Generate OTPAuth URI for QR code."""
        totp = pyotp.TOTP(secret)
        return totp.provisioning_uri(name=username, issuer_name=issuer)
    
    def generate_qr_code(self, uri: str) -> str:
        """Generate QR code as base64 image."""
        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(uri)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        buffered = BytesIO()
        img.save(buffered, format="PNG")
        
        return base64.b64encode(buffered.getvalue()).decode()
    
    def verify_totp(self, secret: str, token: str, window: int = 1) -> bool:
        """Verify TOTP token with time window."""
        totp = pyotp.TOTP(secret)
        return totp.verify(token, valid_window=window)
    
    def generate_backup_codes(self, count: int = 10) -> list:
        """Generate one-time backup codes."""
        import secrets
        import string
        
        alphabet = string.ascii_uppercase + string.digits
        return [''.join(secrets.choice(alphabet) for _ in range(8)) for _ in range(count)]
```

**Database Schema:**
```python
# app/models/user.py - Add to User model
class User(Base):
    # ... existing fields ...
    
    # MFA fields
    mfa_enabled = Column(Boolean, default=False)
    mfa_secret = Column(String(32))  # Encrypted
    mfa_backup_codes = Column(JSON)  # Encrypted hash of codes
    mfa_verified_at = Column(DateTime)
```

**API Endpoints:**
```python
# app/api/auth.py
@router.post("/mfa/enable")
async def enable_mfa(current_user: User = Depends(get_current_user)):
    """Enable MFA for current user."""
    mfa_service = MFAService(settings.SECRET_KEY)
    
    secret = mfa_service.generate_secret()
    uri = mfa_service.get_provisioning_uri(current_user.username, secret)
    qr_code = mfa_service.generate_qr_code(uri)
    
    # Store secret temporarily (not verified yet)
    current_user.mfa_secret = encrypt(secret)
    await db.commit()
    
    return {
        "secret": secret,
        "qr_code": qr_code,
        "uri": uri
    }

@router.post("/mfa/verify")
async def verify_mfa(
    data: MFAVerifyRequest,
    current_user: User = Depends(get_current_user)
):
    """Verify MFA setup and enable."""
    mfa_service = MFAService(settings.SECRET_KEY)
    secret = decrypt(current_user.mfa_secret)
    
    if not mfa_service.verify_totp(secret, data.token):
        raise HTTPException(status_code=400, detail="Invalid TOTP token")
    
    # Generate backup codes
    backup_codes = mfa_service.generate_backup_codes()
    
    current_user.mfa_enabled = True
    current_user.mfa_verified_at = datetime.utcnow()
    current_user.mfa_backup_codes = encrypt(json.dumps(backup_codes))
    
    await db.commit()
    
    return {
        "message": "MFA enabled successfully",
        "backup_codes": backup_codes  # Show only once!
    }

@router.post("/login")
async def login_with_mfa(credentials: OAuth2PasswordRequestForm):
    """Login with optional MFA."""
    user = await authenticate_user(credentials.username, credentials.password)
    
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    if user.mfa_enabled:
        # Return temporary token requiring MFA
        return {
            "requires_mfa": True,
            "temp_token": create_temp_token(user.id),
            "user_id": user.id
        }
    
    # Normal login flow
    access_token = create_access_token(user.id)
    return {"access_token": access_token, "token_type": "bearer"}
```

---

### 6. **Rate Limiting & DDoS Protection** 🛡️

**Redis-backed Rate Limiting:**
```python
# app/middleware/rate_limiter.py
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

limiter = Limiter(key_func=get_remote_address, storage_uri="redis://localhost:6379")

# In main.py
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Usage in routes
@router.post("/documents/upload")
@limiter.limit("10/minute")  # Max 10 uploads per minute per IP
async def upload_document(...):
    pass

@router.post("/api/kms/unwrap")
@limiter.limit("10/minute")  # KMS operations limited
async def unwrap_key(...):
    pass
```

**Global Rate Limit Configuration:**
```python
# Rate limit profiles
RATE_LIMITS = {
    "api_default": "100/minute",
    "api_upload": "10/minute",
    "api_download": "30/minute",
    "api_search": "60/minute",
    "api_auth_login": "5/minute",
    "api_auth_register": "3/hour",
    "api_kms": "10/minute",
    "api_backup": "5/hour",
    "websocket": "20/minute"
}
```

---

### 7. **Document Version Control & Rollback** 📄

**Enhanced Version Management:**
```python
# app/models/document.py - Enhancement
class DocumentVersion(Base):
    __tablename__ = "document_versions"
    
    id = Column(Integer, primary_key=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False)
    version_number = Column(Integer, nullable=False)
    file_path = Column(String(500), nullable=False)
    file_hash = Column(String(64), nullable=False)  # SHA-256
    file_size = Column(BigInteger, nullable=False)
    mime_type = Column(String(100))
    
    # Metadata
    change_summary = Column(Text)
    created_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Workflow state at this version
    lifecycle_state = Column(String(50))
    workflow_stage_id = Column(Integer, ForeignKey("workflow_stages.id"))
    
    # Encryption
    encryption_key_id = Column(Integer, ForeignKey("encryption_keys.id"))
    
    __table_args__ = (
        UniqueConstraint('document_id', 'version_number'),
        Index('idx_doc_versions_document', 'document_id', 'version_number'),
    )

class Document(Base):
    # ... existing fields ...
    
    current_version_id = Column(Integer, ForeignKey("document_versions.id"))
    version_count = Column(Integer, default=1)
    auto_version = Column(Boolean, default=True)  # Auto-increment on edit
```

**Version Control Service:**
```python
# app/services/version_control.py
class VersionControlService:
    """Manage document versions with rollback capability."""
    
    async def create_version(self, document_id: int, file_path: str, 
                            created_by: int, change_summary: str = None) -> DocumentVersion:
        """Create a new version of a document."""
        async with get_db_session() as db:
            doc = await db.get(Document, document_id)
            
            # Calculate file hash
            file_hash = await calculate_file_hash(file_path)
            file_size = os.path.getsize(file_path)
            
            # Create new version
            new_version = DocumentVersion(
                document_id=document_id,
                version_number=doc.version_count + 1,
                file_path=file_path,
                file_hash=file_hash,
                file_size=file_size,
                mime_type=await detect_mime_type(file_path),
                change_summary=change_summary,
                created_by=created_by,
                lifecycle_state=doc.lifecycle_state,
                workflow_stage_id=doc.workflow_stage_id
            )
            
            db.add(new_version)
            await db.flush()
            
            # Update document
            doc.current_version_id = new_version.id
            doc.version_count += 1
            
            await db.commit()
            return new_version
    
    async def rollback_to_version(self, document_id: int, version_number: int,
                                  user_id: int) -> DocumentVersion:
        """Rollback document to a specific version."""
        async with get_db_session() as db:
            # Find target version
            target = await db.execute(
                select(DocumentVersion).where(
                    DocumentVersion.document_id == document_id,
                    DocumentVersion.version_number == version_number
                )
            )
            target_version = target.scalar_one_or_none()
            
            if not target_version:
                raise ValueError(f"Version {version_number} not found")
            
            # Copy file to new version
            new_file_path = await copy_version_file(target_version.file_path)
            
            # Create rollback version
            rollback_version = await self.create_version(
                document_id=document_id,
                file_path=new_file_path,
                created_by=user_id,
                change_summary=f"Rolled back to version {version_number}"
            )
            
            # Preserve original workflow state
            rollback_version.lifecycle_state = target_version.lifecycle_state
            rollback_version.workflow_stage_id = target_version.workflow_stage_id
            
            await db.commit()
            return rollback_version
    
    async def get_version_history(self, document_id: int) -> list:
        """Get complete version history with diff info."""
        async with get_db_session() as db:
            result = await db.execute(
                select(DocumentVersion)
                .where(DocumentVersion.document_id == document_id)
                .order_by(DocumentVersion.version_number.desc())
            )
            versions = result.scalars().all()
            
            # Enrich with creator info and diffs
            history = []
            for v in versions:
                creator = await db.get(User, v.created_by)
                history.append({
                    "version": v.version_number,
                    "created_at": v.created_at,
                    "created_by": creator.full_name if creator else "Unknown",
                    "file_size": v.file_size,
                    "change_summary": v.change_summary,
                    "lifecycle_state": v.lifecycle_state,
                    "is_current": v.id == (await db.get(Document, document_id)).current_version_id
                })
            
            return history
```

---

### 8. **Advanced Search with Filters & Facets** 🔍

**Elasticsearch Integration (Optional for Large Deployments):**
```python
# app/services/search.py
from elasticsearch import AsyncElasticsearch

class AdvancedSearchService:
    """Full-text search with faceting and filtering."""
    
    def __init__(self):
        self.es = AsyncElasticsearch(hosts=[settings.ELASTICSEARCH_URL])
    
    async def index_document(self, document: Document):
        """Index document for full-text search."""
        doc_body = {
            "title": document.title,
            "description": document.description,
            "content": await extract_text(document.file_path),
            "metadata": {
                "group_id": document.group_id,
                "lifecycle_state": document.lifecycle_state,
                "created_by": document.created_by,
                "created_at": document.created_at,
                "tags": document.tags or []
            }
        }
        
        await self.es.index(
            index="documents",
            id=document.id,
            body=doc_body
        )
    
    async def search(self, query: str, filters: dict = None, 
                     facets: list = None, page: int = 1, size: int = 20):
        """Advanced search with filters and facets."""
        search_body = {
            "query": {
                "bool": {
                    "must": [
                        {"multi_match": {
                            "query": query,
                            "fields": ["title^3", "description^2", "content"]
                        }}
                    ]
                }
            },
            "aggs": {}
        }
        
        # Apply filters
        if filters:
            filter_clauses = []
            
            if 'group_id' in filters:
                filter_clauses.append({"term": {"metadata.group_id": filters['group_id']}})
            
            if 'lifecycle_state' in filters:
                filter_clauses.append({"term": {"metadata.lifecycle_state": filters['lifecycle_state']}})
            
            if 'date_from' in filters:
                filter_clauses.append({"range": {"metadata.created_at": {"gte": filters['date_from']}}})
            
            if 'date_to' in filters:
                filter_clauses.append({"range": {"metadata.created_at": {"lte": filters['date_to']}}})
            
            if filter_clauses:
                search_body["query"]["bool"]["filter"] = filter_clauses
        
        # Add facets/aggregations
        if facets:
            if 'lifecycle_state' in facets:
                search_body["aggs"]["lifecycle_states"] = {
                    "terms": {"field": "metadata.lifecycle_state.keyword"}
                }
            
            if 'groups' in facets:
                search_body["aggs"]["groups"] = {
                    "terms": {"field": "metadata.group_id"}
                }
        
        # Pagination
        search_body["from"] = (page - 1) * size
        search_body["size"] = size
        
        # Execute search
        response = await self.es.search(index="documents", body=search_body)
        
        return {
            "total": response["hits"]["total"]["value"],
            "results": [hit["_source"] for hit in response["hits"]["hits"]],
            "facets": response.get("aggregations", {})
        }
```

---

### 9. **Email Notifications & Alerts** 📧

**Notification Service:**
```python
# app/services/notifications.py
from aiosmtplib import send
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

class NotificationService:
    """Email notification service with templates."""
    
    NOTIFICATION_TYPES = {
        'workflow_assigned': 'Workflow Task Assigned',
        'workflow_approved': 'Document Approved',
        'workflow_rejected': 'Document Rejected',
        'document_shared': 'Document Shared with You',
        'comment_added': 'New Comment on Document',
        'user_status_change': 'User Status Changed',
        'backup_completed': 'Backup Completed',
        'ransomware_alert': '⚠️ Ransomware Detection Alert',
        'security_alert': 'Security Alert',
    }
    
    async def send_email(self, to: str, subject: str, template: str, 
                         context: dict, attachments: list = None):
        """Send email with template."""
        # Render template
        from jinja2 import Environment, FileSystemLoader
        env = Environment(loader=FileSystemLoader('app/templates/emails'))
        template = env.get_template(f"{template}.html")
        html_content = template.render(context)
        
        # Create message
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = settings.SMTP_FROM
        msg["To"] = to
        
        # Attach HTML
        msg.attach(MIMEText(html_content, "html"))
        
        # Attach files if provided
        if attachments:
            for file_path in attachments:
                with open(file_path, "rb") as f:
                    part = MIMEBase('application', 'octet-stream')
                    part.set_payload(f.read())
                    encoders.encode_base64(part)
                    part.add_header(
                        'Content-Disposition',
                        f'attachment; filename={os.path.basename(file_path)}'
                    )
                    msg.attach(part)
        
        # Send
        await send(
            msg,
            hostname=settings.SMTP_HOST,
            port=settings.SMTP_PORT,
            username=settings.SMTP_USER,
            password=settings.SMTP_PASSWORD,
            start_tls=True
        )
    
    async def notify_workflow_assignment(self, user: User, document: Document, stage: str):
        """Notify user of workflow task assignment."""
        await self.send_email(
            to=user.email,
            subject=f"Task Assigned: {document.title}",
            template="workflow_assigned",
            context={
                "user_name": user.full_name,
                "document_title": document.title,
                "stage": stage,
                "due_date": document.due_date,
                "url": f"{settings.BASE_URL}/workflow/kanban"
            }
        )
    
    async def notify_ransomware_alert(self, alert: dict):
        """Send urgent ransomware detection alert."""
        # Send to all admins
        admins = await get_admin_users()
        
        for admin in admins:
            await self.send_email(
                to=admin.email,
                subject="🚨 CRITICAL: Ransomware Detection Alert",
                template="ransomware_alert",
                context={
                    "alert_time": alert['timestamp'],
                    "affected_files": alert['affected_files'],
                    "operations_per_sec": alert['ops_per_sec'],
                    "entropy_score": alert['entropy_score'],
                    "action_taken": alert['action'],
                    "url": f"{settings.BASE_URL}/security/ransomware"
                },
                priority='high'
            )
```

---

### 10. **Performance Monitoring & APM** 📊

**OpenTelemetry Integration:**
```python
# app/core/telemetry.py
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor

def setup_telemetry():
    """Configure OpenTelemetry for distributed tracing."""
    
    # Set up tracer provider
    provider = TracerProvider()
    
    # Add OTLP exporter (for Jaeger/Tempo)
    if settings.OTEL_EXPORTER_URL:
        exporter = OTLPSpanExporter(endpoint=settings.OTEL_EXPORTER_URL)
        processor = BatchSpanProcessor(exporter)
        provider.add_span_processor(processor)
    
    trace.set_tracer_provider(provider)
    
    # Instrument frameworks
    FastAPIInstrumentor.instrument_app(app)
    SQLAlchemyInstrumentor().instrument()
    RedisInstrumentor().instrument()

# Usage in main.py
setup_telemetry()
```

**Custom Metrics with Prometheus:**
```python
# app/core/metrics.py
from prometheus_client import Counter, Histogram, Gauge, generate_latest
from fastapi import Response

# Define metrics
REQUEST_COUNT = Counter(
    'http_requests_total',
    'Total HTTP requests',
    ['method', 'endpoint', 'status']
)

REQUEST_LATENCY = Histogram(
    'http_request_duration_seconds',
    'HTTP request latency',
    ['method', 'endpoint'],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
)

ACTIVE_USERS = Gauge(
    'active_users',
    'Number of currently active users'
)

DOCUMENT_COUNT = Gauge(
    'documents_total',
    'Total number of documents',
    ['lifecycle_state']
)

WORKFLOW_TASKS = Gauge(
    'workflow_tasks_pending',
    'Number of pending workflow tasks',
    ['stage']
)

BACKUP_SIZE = Gauge(
    'backup_size_bytes',
    'Size of latest backup',
    ['type']  # primary, dr
)

RANSOMWARE_ALERTS = Counter(
    'ransomware_alerts_total',
    'Total ransomware detection alerts'
)

# Middleware to record metrics
@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    start_time = time.time()
    
    response = await call_next(request)
    
    duration = time.time() - start_time
    
    REQUEST_COUNT.labels(
        method=request.method,
        endpoint=request.url.path,
        status=response.status_code
    ).inc()
    
    REQUEST_LATENCY.labels(
        method=request.method,
        endpoint=request.url.path
    ).observe(duration)
    
    return response

# Metrics endpoint
@app.get("/metrics")
async def get_metrics():
    return Response(generate_latest(), media_type="text/plain")
```

---

## 🎯 Priority 2: UX & Usability Enhancements

### 11. **Real-time Collaboration Features** 💬

**WebSocket Implementation:**
```python
# app/websockets/collaboration.py
from fastapi import WebSocket, WebSocketDisconnect
from typing import Dict, List
import json

class ConnectionManager:
    """Manage WebSocket connections for real-time features."""
    
    def __init__(self):
        self.active_connections: Dict[int, List[WebSocket]] = {}
        self.document_connections: Dict[int, List[WebSocket]] = {}
    
    async def connect(self, websocket: WebSocket, user_id: int, document_id: int = None):
        await websocket.accept()
        
        # Add to user connections
        if user_id not in self.active_connections:
            self.active_connections[user_id] = []
        self.active_connections[user_id].append(websocket)
        
        # Add to document connections if applicable
        if document_id:
            if document_id not in self.document_connections:
                self.document_connections[document_id] = []
            self.document_connections[document_id].append(websocket)
    
    def disconnect(self, websocket: WebSocket, user_id: int, document_id: int = None):
        if user_id in self.active_connections:
            self.active_connections[user_id].remove(websocket)
        
        if document_id and document_id in self.document_connections:
            self.document_connections[document_id].remove(websocket)
    
    async def broadcast_to_document(self, document_id: int, message: dict):
        """Send message to all users viewing a document."""
        if document_id in self.document_connections:
            message_json = json.dumps(message)
            for connection in self.document_connections[document_id]:
                await connection.send_text(message_json)
    
    async def notify_user(self, user_id: int, message: dict):
        """Send message to specific user."""
        if user_id in self.active_connections:
            message_json = json.dumps(message)
            for connection in self.active_connections[user_id]:
                await connection.send_text(message_json)

manager = ConnectionManager()

# WebSocket endpoint
@app.websocket("/ws/collaboration/{document_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    document_id: int,
    current_user: User = Depends(get_current_user_ws)
):
    await manager.connect(websocket, current_user.id, document_id)
    
    # Notify others that user joined
    await manager.broadcast_to_document(document_id, {
        "type": "user_joined",
        "user_id": current_user.id,
        "user_name": current_user.full_name,
        "timestamp": datetime.utcnow().isoformat()
    })
    
    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            
            # Handle different message types
            if message["type"] == "cursor_update":
                await manager.broadcast_to_document(document_id, {
                    "type": "cursor_move",
                    "user_id": current_user.id,
                    "user_name": current_user.full_name,
                    "position": message["position"]
                })
            
            elif message["type"] == "comment_added":
                await manager.broadcast_to_document(document_id, {
                    "type": "new_comment",
                    "user_name": current_user.full_name,
                    "comment": message["comment"]
                })
    
    except WebSocketDisconnect:
        manager.disconnect(websocket, current_user.id, document_id)
        await manager.broadcast_to_document(document_id, {
            "type": "user_left",
            "user_id": current_user.id,
            "user_name": current_user.full_name
        })
```

---

### 12. **Mobile-Responsive UI Improvements** 📱

**Progressive Web App (PWA) Support:**
```json
// public/manifest.json
{
  "name": "EDMS - Enterprise Document Management",
  "short_name": "EDMS",
  "description": "Secure, airgap-ready document management system",
  "start_url": "/",
  "display": "standalone",
  "background_color": "#ffffff",
  "theme_color": "#2563eb",
  "icons": [
    {
      "src": "/icons/icon-192.png",
      "sizes": "192x192",
      "type": "image/png"
    },
    {
      "src": "/icons/icon-512.png",
      "sizes": "512x512",
      "type": "image/png"
    }
  ]
}
```

```javascript
// public/service-worker.js
const CACHE_NAME = 'edms-v1';
const urlsToCache = [
  '/',
  '/static/css/app.css',
  '/static/js/app.js',
  '/offline.html'
];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => cache.addAll(urlsToCache))
  );
});

self.addEventListener('fetch', event => {
  event.respondWith(
    caches.match(event.request)
      .then(response => {
        if (response) {
          return response;
        }
        return fetch(event.request);
      })
      .catch(() => caches.match('/offline.html'))
  );
});
```

---

## 🎯 Priority 3: Operational Excellence

### 13. **Automated Testing Suite** ✅

**Test Structure:**
```
tests/
├── unit/
│   ├── test_services/
│   │   ├── test_backup.py
│   │   ├── test_kms.py
│   │   ├── test_ransomware_detector.py
│   │   └── test_prompt_guard.py
│   └── test_models/
│       ├── test_user.py
│       └── test_document.py
├── integration/
│   ├── test_api/
│   │   ├── test_documents.py
│   │   ├── test_workflow.py
│   │   └── test_rbac.py
│   └── test_database/
│       └── test_migrations.py
├── e2e/
│   ├── test_user_journeys.py
│   └── test_workflow_scenarios.py
└── conftest.py
```

**Example Test:**
```python
# tests/integration/test_api/test_workflow.py
import pytest
from fastapi.testclient import TestClient

@pytest.mark.asyncio
async def test_workflow_auto_reassignment_on_user_termination(
    client: TestClient,
    test_user: User,
    test_document: Document,
    test_workflow: DocumentWorkflow
):
    """Test that workflow tasks are automatically reassigned when user is terminated."""
    
    # Setup: Assign workflow task to test_user
    await assign_workflow_task(test_workflow.id, test_user.id, "In Review")
    
    # Action: Change user status to terminated
    response = client.put(
        f"/api/users/{test_user.id}/status",
        json={"status": "terminated"},
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert response.status_code == 200
    
    # Verify: Task should be reassigned to position head
    workflow = await get_workflow(test_workflow.id)
    assert workflow.assigned_to != test_user.id
    assert workflow.assigned_to == test_user.position.head_id
    
    # Verify: Audit log entry created
    audit_logs = await search_audit_logs(
        resource_type="workflow",
        resource_id=test_workflow.id,
        action="AUTO_REASSIGN"
    )
    assert len(audit_logs) == 1
```

---

### 14. **Disaster Recovery Drills** 🔄

**Automated DR Testing:**
```python
# app/services/dr_testing.py
class DisasterRecoveryTester:
    """Automated disaster recovery testing."""
    
    async def run_monthly_dr_test(self):
        """Execute monthly DR drill."""
        test_id = f"dr-test-{datetime.utcnow().strftime('%Y%m')}"
        
        results = {
            "test_id": test_id,
            "timestamp": datetime.utcnow(),
            "scenarios": []
        }
        
        # Scenario 1: Database failover
        db_result = await self.test_database_failover()
        results["scenarios"].append(db_result)
        
        # Scenario 2: Storage failover to DR
        storage_result = await self.test_storage_failover()
        results["scenarios"].append(storage_result)
        
        # Scenario 3: KMS failover
        kms_result = await self.test_kms_failover()
        results["scenarios"].append(kms_result)
        
        # Scenario 4: Full restore from backup
        restore_result = await self.test_full_restore()
        results["scenarios"].append(restore_result)
        
        # Generate report
        await self.generate_dr_report(results)
        
        # Alert if any scenario failed
        if any(not s["success"] for s in results["scenarios"]):
            await self.notify_dr_failure(results)
        
        return results
    
    async def test_full_restore(self) -> dict:
        """Test restoring from latest backup."""
        start_time = datetime.utcnow()
        
        try:
            # Get latest backup
            backup_service = BackupService()
            latest_backup = await backup_service.get_latest_snapshot()
            
            # Create isolated test environment
            test_db = await self.create_test_database()
            
            # Restore
            await backup_service.restore(
                snapshot_id=latest_backup.id,
                target_db=test_db
            )
            
            # Verify integrity
            integrity_check = await self.verify_restored_data(test_db)
            
            duration = (datetime.utcnow() - start_time).total_seconds()
            
            return {
                "scenario": "full_restore",
                "success": integrity_check["passed"],
                "duration_seconds": duration,
                "rto_met": duration < settings.RTO_TARGET_SECONDS,
                "details": integrity_check
            }
        
        except Exception as e:
            return {
                "scenario": "full_restore",
                "success": False,
                "error": str(e)
            }
```

---

## 📋 Implementation Checklist

### Phase 1: Foundation (Week 1-2)
- [ ] Health check endpoints
- [ ] Graceful shutdown handling
- [ ] Database migration system (Alembic)
- [ ] Structured logging with correlation IDs
- [ ] Basic rate limiting

### Phase 2: Security (Week 3-4)
- [ ] MFA implementation
- [ ] Enhanced audit logging
- [ ] Session recording improvements
- [ ] Advanced RBAC policies

### Phase 3: Reliability (Week 5-6)
- [ ] Document version control
- [ ] Automated backup verification
- [ ] DR testing automation
- [ ] Monitoring & alerting setup

### Phase 4: Performance (Week 7-8)
- [ ] Advanced search with Elasticsearch
- [ ] Caching layer optimization
- [ ] APM integration
- [ ] Load testing

### Phase 5: UX (Week 9-10)
- [ ] Real-time collaboration
- [ ] Mobile-responsive improvements
- [ ] PWA support
- [ ] Email notifications

### Phase 6: Polish (Week 11-12)
- [ ] Comprehensive test suite
- [ ] Documentation updates
- [ ] Performance tuning
- [ ] Security audit

---

## 🎯 Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Uptime | 99.9% | Monthly availability |
| RTO | < 4 hours | Time to restore from DR |
| RPO | < 1 hour | Data loss tolerance |
| Page Load Time | < 2s | 95th percentile |
| API Latency (p95) | < 500ms | All endpoints |
| Error Rate | < 0.1% | HTTP 5xx errors |
| Backup Success Rate | 100% | Daily backups |
| Security Incidents | 0 | Breaches/vulnerabilities |
| Test Coverage | > 80% | Code coverage |
| Mean Time to Detect | < 5 min | Security anomalies |

---

## 🔗 Related Documentation

- See `ARCHITECTURE.md` for system design
- See `SECURITY.md` for security controls
- See `OPERATIONS_RUNBOOK.md` for operational procedures
- See `TROUBLESHOOTING.md` for common issues
