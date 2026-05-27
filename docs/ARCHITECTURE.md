# Architecture

This document describes the system architecture of EDMS, including the processing pipeline, component relationships, database schema, and integration patterns.

## Three-Layer Pipeline

EDMS processes documents through a three-layer pipeline that transforms raw uploads into searchable, structured knowledge:

```
                         EDMS Pipeline Architecture

  +----------------+     +------------------+     +------------------+
  |  Raw Sources   |     |   Processing     |     |    LLM Wiki      |
  |                |     |   Pipeline       |     |                  |
  |  - PDF         | --> |  - Convert to MD | --> |  - index.md      |
  |  - DOCX        |     |  - Chunk text    |     |  - entities/     |
  |  - Images      |     |  - Generate      |     |  - topics/       |
  |  - Text        |     |    summary       |     |  - summaries/    |
  |                |     |  - Extract       |     |  - log.md        |
  |                |     |    keywords      |     |                  |
  +----------------+     |  - Embed chunks  |     +------------------+
                         |  - Index in      |              |
                         |    vector DB     |              v
                         |  - Wiki ingest   |     +------------------+
                         +------------------+     |    RAG Search    |
                                                  |  & Chat          |
                                                  +------------------+
```

### Layer 1: Raw Sources

Documents are uploaded through the REST API in various formats. Each document belongs to a group (folder) for organizational purposes. Supported formats include PDF, DOCX, images (PNG, JPG, TIFF), and plain text.

### Layer 2: Processing Pipeline

When a document is uploaded, a FastAPI BackgroundTask processes it through these stages:

1. **Conversion** - PDF/DOCX/image to Markdown via PyMuPDF, python-docx, or Tesseract OCR
2. **Summarization** - LLM generates a concise summary of the content
3. **Keyword Extraction** - LLM extracts key terms and concepts
4. **Chunking** - Text is split into overlapping chunks (configurable `CHUNK_SIZE`, default 1000)
5. **Embedding** - Chunks are embedded using OpenAI `text-embedding-3-small`
6. **Vector Indexing** - Embeddings stored in ChromaDB for semantic search
7. **Wiki Ingest** - Extracted knowledge is integrated into the LLM wiki

### Layer 3: LLM Wiki

A persistent, interlinked set of markdown files that grows with each ingested document. See [WIKI.md](WIKI.md) for full details.

## Component Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                           FastAPI Application                         │
│                                                                       │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                        API Layer (app/api/)                    │   │
│  │  auth | documents | groups | bulk | lifecycle | workflow       │   │
│  │  wiki | search | annotations | rbac | org | ldap | security   │   │
│  │  settings_backup | settings_encryption | settings_llm         │   │
│  │  versions | preview | compare | audit | chat | websocket      │   │
│  │  relationships | obsidian | health_dashboard                  │   │
│  └───────────────────────────┬──────────────────────────────────┘   │
│                               │                                       │
│  ┌───────────────────────────▼──────────────────────────────────┐   │
│  │                     Service Layer (app/services/)              │   │
│  │  PipelineService | StorageService | WikiService               │   │
│  │  BulkService | LifecycleService | EmailNotificationService    │   │
│  │  VectorDBService | BackupService | KeyRecoveryManager         │   │
│  │  LdapService | RansomwareDetector                             │   │
│  │  VersioningService | ComparisonService | PreviewService       │   │
│  │  AuditService | ChatService | NotificationManager             │   │
│  │  RelationshipService | ObsidianExportService                  │   │
│  │  HealthMonitorService | SecurityMonitoring                    │   │
│  │  PromptGuard | KMSProvider | BackupKEKManager                 │   │
│  └───────────────────────────┬──────────────────────────────────┘   │
│                               │                                       │
│  ┌───────────────────────────▼──────────────────────────────────┐   │
│  │                      Core Layer (app/core/)                    │   │
│  │  config.py | database.py | security.py | llm.py               │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                       │
└──────────┬──────────┬──────────┬──────────┬──────────┬──────────────┘
           │          │          │          │          │
           ▼          ▼          ▼          ▼          ▼
      ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐
      │SQLite/ │ │ChromaDB│ │OpenAI/ │ │ MinIO  │ │  LDAP  │
      │Postgres│ │(Vector)│ │Ollama  │ │(Backup)│ │ Server │
      └────────┘ └────────┘ └────────┘ └────────┘ └────────┘
```

## Database Schema Overview

The database contains the following table groups:

### Document Management

| Table | Purpose |
|-------|---------|
| `groups` | Folder hierarchy for organizing documents |
| `documents` | Uploaded document metadata and processing status |
| `document_versions` | Version history with independent encryption per version |
| `document_audit_log` | Immutable append-only audit trail of all operations |
| `document_relationships` | Typed relationships between documents (parent, child, references, etc.) |
| `workflow_entries` | Workflow action history (submit, approve, reject, sign off) |
| `document_lifecycles` | Lifecycle state machine per document |
| `lifecycle_transitions` | Audit trail of lifecycle state changes |
| `annotations` | User annotations on documents |
| `chat_sessions` | Persistent multi-turn chat sessions |
| `chat_messages` | Individual messages within chat sessions |
| `notifications` | Real-time notification records with read/unread tracking |

### User & Access Control

| Table | Purpose |
|-------|---------|
| `users` | User accounts (local + LDAP) |
| `roles` | Role definitions (admin, editor, reviewer, etc.) |
| `permissions` | Permission definitions (resource:action pairs) |
| `role_permissions` | Role-to-permission mappings |
| `user_roles` | User-to-role assignments |
| `folder_assignments` | Per-folder role assignments for users |

### Organization Structure

| Table | Purpose |
|-------|---------|
| `org_unit_types` | Classification of org units (Corp, Div, Dept, Unit, Team) |
| `org_units` | Organizational hierarchy nodes |
| `org_positions` | Job positions within units |
| `org_grades` | Grade/level definitions (G01-G15) |
| `org_user_assignments` | User-to-position assignments |
| `org_user_grades` | User personal grade history |
| `org_change_history` | Audit trail for org structure changes |

### Security & Encryption

| Table | Purpose |
|-------|---------|
| `encryption_keys` | KEK/DEK key metadata |
| `key_shares` | Shamir Secret Sharing share records |
| `security_alerts` | Ransomware detection alerts |
| `monitoring_config` | Security monitoring configuration |

### LDAP & Backup

| Table | Purpose |
|-------|---------|
| `ldap_configs` | LDAP server connection configs |
| `ldap_group_roles` | LDAP group to EDMS role mappings |
| `ldap_sync_logs` | LDAP synchronization audit logs |
| `backup_jobs` | Backup job execution history |
| `backup_schedules` | Cron-based backup schedules |
| `backup_configs` | Key-value backup configuration store |

### Entity Relationships

```
groups (1) ──────── (N) documents
documents (1) ───── (N) workflow_entries
documents (1) ───── (1) document_lifecycles
documents (1) ───── (N) annotations
document_lifecycles (1) ── (N) lifecycle_transitions

users (1) ────────── (N) user_roles
roles (1) ────────── (N) role_permissions
roles (1) ────────── (N) user_roles
permissions (1) ──── (N) role_permissions

users (1) ────────── (N) folder_assignments
users (1) ────────── (N) org_user_assignments
users (1) ────────── (N) org_user_grades

org_units (1) ────── (N) org_positions
org_units (1) ────── (N) org_user_assignments
org_positions (1) ── (N) org_user_assignments
org_grades (1) ───── (N) org_positions
org_grades (1) ───── (N) org_user_grades

groups (parent) ──── (N) groups (children)
org_units (parent) ─ (N) org_units (children)
```

## Service Layer Design

Each service encapsulates a domain of business logic:

| Service | Responsibility |
|---------|---------------|
| `PipelineService` | Document processing: conversion, summarization, embedding, wiki ingest |
| `StorageService` | File system operations: save, encrypt PDF, delete |
| `WikiService` | Wiki CRUD, querying, linting, log management |
| `BulkService` | Multi-document upload and workflow actions |
| `LifecycleService` | State machine transitions, expiry/review alerting |
| `EmailNotificationService` | SMTP-based lifecycle alert emails |
| `VectorDBService` | ChromaDB indexing and semantic search |
| `BackupService` | MinIO/Restic backup orchestration |
| `KeyRecoveryManager` | KEK generation, Shamir splitting, reconstruction |
| `RansomwareDetector` | File system monitoring for suspicious activity |
| `LdapService` | LDAP connection testing and user synchronization |
| `VersioningService` | Document version management with independent DEK encryption |
| `ComparisonService` | Document and version content diffing with similarity analysis |
| `PreviewService` | Cached preview generation (PDF thumbnails, markdown HTML, images) |
| `AuditService` | Immutable document operation logging and history queries |
| `ChatService` | Multi-turn persistent chat sessions with windowed history |
| `NotificationManager` | WebSocket real-time notification delivery and persistence |
| `RelationshipService` | Document relationship graph management and traversal |
| `ObsidianExportService` | Wiki export to Obsidian vault format with wikilinks |
| `HealthMonitorService` | System health detection (expired lifecycles, broken reviewers, stale docs) |
| `PromptGuard` | Prompt injection detection and sanitization for LLM inputs |
| `KMSProvider` | Pluggable key management (LocalFileKMS, VaultKMS, CosmianKMS) |
| `BackupKEKManager` | Isolated backup key hierarchy management |
| `SecurityMonitoring` | KMS rate limiting, external alert processing, monitoring status |

## API Layer Structure

Routes are organized into focused routers registered via `app/api/router.py`:

```python
api_router.include_router(auth_router)        # /api/auth/*
api_router.include_router(users_router)       # /api/users/*
api_router.include_router(groups_router)      # /api/groups/*
api_router.include_router(compare_router)     # /api/documents/compare, /api/documents/{id}/versions/diff
api_router.include_router(documents_router)   # /api/documents/*, /api/groups/{id}/documents
api_router.include_router(search_router)      # /api/search, /api/chat
api_router.include_router(wiki_router)        # /api/wiki/*
api_router.include_router(annotations_router) # /api/documents/{id}/annotations
api_router.include_router(workflow_router)    # /api/documents/{id}/workflow/*
api_router.include_router(bulk_router)        # /api/bulk/*
api_router.include_router(lifecycle_router)   # /api/documents/{id}/lifecycle, /api/lifecycle/*
api_router.include_router(relationships_router) # /api/documents/{id}/relationships, /api/relationships/*
api_router.include_router(health_dashboard_router) # /api/health/*, /settings/health
api_router.include_router(obsidian_router)    # /api/wiki/export/obsidian/*
api_router.include_router(chat_router)        # /api/chat/sessions/*
api_router.include_router(audit_router)       # /api/documents/{id}/history, /api/audit/recent
api_router.include_router(versions_router)    # /api/documents/{id}/versions/*
api_router.include_router(preview_router)     # /api/documents/{id}/preview
api_router.include_router(notifications_router) # /ws/notifications, /api/notifications/*
api_router.include_router(org_router)         # /org/api/*
api_router.include_router(rbac_router)        # /rbac/api/*
api_router.include_router(ldap_router)        # /ldap/api/*
api_router.include_router(security_router)    # /api/security/*
api_router.include_router(settings_backup_router)     # /api/settings/backup/*
api_router.include_router(settings_encryption_router) # /api/settings/encryption/*
api_router.include_router(settings_llm_router)        # /api/settings/llm/*
```

All routes use FastAPI dependency injection for database sessions (`get_db`) and authentication (`get_current_user`, `role_required`, `require_role`, `require_permission`).

## Background Task Processing

EDMS uses FastAPI's `BackgroundTasks` for asynchronous processing:

1. **Document Pipeline** - After upload, a background task converts, summarizes, embeds, and indexes the document
2. **Backup Jobs** - Backup operations run in background tasks
3. **LDAP Sync** - User synchronization can be triggered asynchronously

Background tasks create their own database sessions to avoid conflicts with the request session:

```python
async def _run_pipeline(doc_id: int, db_url: str, storage_svc: StorageService):
    engine = create_async_engine(db_url, echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession)
    async with session_factory() as session:
        svc = PipelineService(storage_service=storage_svc)
        await svc.process_document(doc_id, session)
    await engine.dispose()
```

## LLM Integration

EDMS supports two LLM providers via the `LLM_PROVIDER` setting:

- **OpenAI** (default) - Uses `gpt-4` for generation and `text-embedding-3-small` for embeddings
- **Ollama** (local) - Uses locally-hosted models via the Ollama API

The `app/core/llm.py` module provides unified interfaces:
- `chat_completion(messages, context)` - Generate text responses
- `generate_embeddings(texts)` - Generate vector embeddings

## Vector Database (ChromaDB)

ChromaDB stores document chunk embeddings for semantic search:

- **Local mode** - Persistent storage at `CHROMA_DB_PATH` (default: `./chroma_db`)
- **Server mode** - Connect to a remote ChromaDB instance via `CHROMA_HOST`/`CHROMA_PORT`

Collections are organized by group ID, allowing scoped searches within document groups.

## Encryption Architecture

EDMS implements envelope encryption for documents at rest:

```
┌─────────────────────────────────────────────┐
│           Encryption Architecture            │
│                                              │
│  KEK (Key Encryption Key)                    │
│    ├── Stored encrypted with passphrase      │
│    ├── Split via Shamir Secret Sharing       │
│    │   (threshold-of-N reconstruction)       │
│    └── Used to encrypt/decrypt DEKs          │
│                                              │
│  DEK (Data Encryption Key)                   │
│    ├── Per-document or per-session key        │
│    ├── Encrypted with KEK for storage        │
│    └── Used for AES-256-GCM encryption       │
│                                              │
│  PDF Password Encryption                     │
│    └── pikepdf encrypts PDFs with password   │
│        (PDF_ENCRYPTION_PASSWORD setting)     │
└─────────────────────────────────────────────┘
```

See [SECURITY.md](SECURITY.md) for full encryption details.

## RBAC Architecture

The RBAC system uses a three-level model:

```
Users ──(N:M)── Roles ──(N:M)── Permissions
                                  (resource:action)
```

Additionally, `FolderAssignment` provides per-folder role scoping:

```
Users ──(1:N)── FolderAssignments ──(N:1)── Roles
                     │
                     └── folder_path (scope)
```

System roles seeded at startup: `admin`, `manager`, `operator`, `viewer`, `editor`, `reviewer`, `annotator`, `approver`.

## Bulk Operations Architecture

Bulk operations allow batch processing of documents:

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  Bulk Upload │     │Bulk Workflow  │     │ Bulk Approve │
│              │     │              │     │ Bulk Signoff │
│  - N files   │     │  - N doc IDs │     │  - N doc IDs │
│  - group_id  │     │  - action    │     │  - comment   │
│  - folder_   │     │  - comment   │     │              │
│    path      │     │              │     │              │
└──────┬───────┘     └──────┬───────┘     └──────┬───────┘
       │                     │                     │
       ▼                     ▼                     ▼
┌──────────────────────────────────────────────────────────┐
│                     BulkService                           │
│  - Auto-creates groups from folder_path                  │
│  - Processes each item, collecting results               │
│  - Returns per-item success/failure with error details   │
└──────────────────────────────────────────────────────────┘
```

## Lifecycle State Machine

Documents can be assigned a lifecycle with defined state transitions:

```
                    ┌─────────┐
                    │  draft  │
                    └────┬────┘
                         │ submit for review
                         ▼
                    ┌───────────┐
              ┌─────│ in_review │─────┐
              │     └───────────┘     │
              │ reject                │ approve
              ▼                       ▼
         ┌─────────┐           ┌──────────┐
         │  draft  │           │ approved │
         └─────────┘           └────┬─────┘
                                    │ mark up to date
                                    ▼
                              ┌────────────┐
                    ┌─────────│ up_to_date │──────────┐
                    │         └────────────┘          │
                    │ needs re-review                 │ expire
                    ▼                                 ▼
           ┌────────────────┐                  ┌─────────┐
           │needs_re_review │──────────────────│ expired │
           └───────┬────────┘  expire          └─────────┘
                   │
                   │ submit for review
                   ▼
              ┌───────────┐
              │ in_review │
              └───────────┘
```

Lifecycle types:
- **permanent** - Document never expires
- **expiring** - Document has a hard expiration date (`expires_at`)
- **recurring** - Document requires periodic re-review (`review_interval_days`)

See [DATA_DICTIONARY.md](DATA_DICTIONARY.md) for the complete model reference.

## KMS Abstraction Layer

EDMS uses a pluggable Key Management Service for all key wrapping operations:

```
┌─────────────────────────────────────────────────────────────────┐
│                     KMS Abstraction Layer                         │
│                                                                   │
│  KMSProvider (abstract)                                           │
│    ├── wrap_key(plaintext) -> wrapped_blob                        │
│    ├── unwrap_key(wrapped_blob) -> plaintext                      │
│    └── generate_key() -> wrapped_blob                             │
│                                                                   │
│  Implementations:                                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐       │
│  │ LocalFileKMS │  │   VaultKMS   │  │   CosmianKMS     │       │
│  │  (scrypt +   │  │  (HashiCorp  │  │  (Cosmian KMS    │       │
│  │   AES-GCM)   │  │   Transit)   │  │   provider)      │       │
│  └──────────────┘  └──────────────┘  └──────────────────┘       │
│                                                                   │
│  Configuration: KMS_PROVIDER = local | vault | cosmian            │
└─────────────────────────────────────────────────────────────────┘
```

The KMS never stores or transmits raw keys. All key material is wrapped before persistence. The `rate_limited_unwrap` function enforces per-IP rate limits (default: 10 unwrap calls per minute) to prevent key extraction attacks.

## Security Monitoring Layers

EDMS integrates with multiple security monitoring tools:

```
┌─────────────────────────────────────────────────────────┐
│              Security Monitoring Architecture             │
│                                                           │
│  Layer 1: File Integrity Monitoring                       │
│    Tool: auditd                                           │
│    Detects: unauthorized file modifications               │
│                                                           │
│  Layer 2: Process/Container Monitoring                    │
│    Tool: Falco                                            │
│    Detects: unexpected processes, privilege escalation     │
│                                                           │
│  Layer 3: KMS Audit                                       │
│    Tool: KMS Rate Limiter (internal)                      │
│    Detects: brute-force key extraction attempts           │
│    Rate: 10 unwrap calls/min per IP (sliding window)      │
│                                                           │
│  Layer 4: Network Monitoring                              │
│    Tool: Suricata                                         │
│    Detects: data exfiltration, C2 communication           │
│                                                           │
│  Alert Ingestion:                                         │
│    External tools -> POST /api/security/alerts webhook    │
│    -> Validated (source, severity, message)               │
│    -> Stored as SecurityAlert record                      │
│    -> Available in security dashboard                     │
└─────────────────────────────────────────────────────────┘
```

## Prompt Injection Protection

All user content sent to the LLM passes through the PromptGuard service:

```
┌───────────────────────────────────────────────────────────────┐
│                Anti-AI Prompt Injection Pipeline               │
│                                                               │
│  User Input                                                   │
│       │                                                       │
│       ▼                                                       │
│  PromptGuard.sanitize(text)                                   │
│       │                                                       │
│       ├── Pattern matching (5 categories):                    │
│       │   1. Instruction override (high severity)             │
│       │   2. Role switching (medium severity)                 │
│       │   3. Delimiter injection (medium severity)            │
│       │   4. System prompt injection (medium severity)        │
│       │   5. Ignore-instructions commands (high severity)     │
│       │                                                       │
│       ├── If detected:                                        │
│       │   - Prefix text with "[user text]:" neutralization    │
│       │   - Log SecurityAlert to database                     │
│       │   - Record matched pattern and severity               │
│       │                                                       │
│       ▼                                                       │
│  PromptGuard.wrap_user_content(text)                          │
│       │                                                       │
│       ├── Wrap in XML boundary markers:                       │
│       │   <user_content>...</user_content>                    │
│       │                                                       │
│       ▼                                                       │
│  Safe text passed to LLM                                      │
└───────────────────────────────────────────────────────────────┘
```

## Comprehensive Error Handling

EDMS uses a structured error taxonomy for consistent error responses:

```
EDMSBaseError (base)
  ├── ValidationError     (VALIDATION_ERROR)
  ├── AuthenticationError (AUTHENTICATION_ERROR)
  ├── PermissionError     (PERMISSION_ERROR)
  ├── NotFoundError       (NOT_FOUND)
  ├── ConflictError       (CONFLICT)
  ├── ProcessingError     (PROCESSING_ERROR)
  ├── StorageError        (STORAGE_ERROR)
  ├── EncryptionError     (ENCRYPTION_ERROR)
  └── KMSError            (KMS_ERROR)
```

Error responses include:
- `error_code` - Machine-readable error classification
- `message` - Human-readable description
- `request_id` - X-Request-ID for tracing
- `timestamp` - When the error occurred

The KMS rate limiter returns HTTP 429 when clients exceed the configured unwrap rate.

## WebSocket Real-time Architecture

```
┌────────────┐       ws://host/ws/notifications?token=JWT
│   Client   │ ◄──────────────────────────────────────────────┐
└─────┬──────┘                                                 │
      │ connect                                                │
      ▼                                                        │
┌─────────────────┐          ┌────────────────────┐           │
│ JWT Verification │ ─valid─▶ │NotificationManager │ ──push──┘
│  (_verify_ws_   │          │                    │
│   token)        │          │  - connect()       │
└─────────────────┘          │  - disconnect()    │
                             │  - broadcast()     │
                             │  - send_to_user()  │
                             └────────────────────┘
                                      ▲
                                      │ create_notification()
                             ┌────────┴─────────┐
                             │  Service Layer    │
                             │  (any service can │
                             │   emit notifs)    │
                             └──────────────────┘
```

Notification types:
- `document_status` - Processing state changes
- `lifecycle_alert` - Expiry/review approaching
- `ransomware_alert` - Security threat detected (broadcast)
- `backup_status` - Backup job completed/failed

## Document Versioning Storage

Each version is independently encrypted with its own DEK via the KMS provider:

```
storage/
└── versions/
    └── {document_id}/
        ├── v1_original.pdf.enc    (encrypted with DEK_1)
        ├── v2_revised.pdf.enc     (encrypted with DEK_2)
        └── v3_final.pdf.enc       (encrypted with DEK_3)

Database (document_versions):
  - wrapped_dek: KMS-wrapped DEK for each version
  - version_number: monotonically increasing
  - changelog: description of changes
```

Reverting to a version updates the document's `current_version`, `storage_path`, and `file_size` fields to point at the target version.

## Setup Wizard

EDMS includes a first-launch setup wizard available as both CLI and web interface:

- **CLI**: `python -m app.setup_wizard`
- **Web**: Automatically displayed at `/setup` on first launch when no `.env` exists

The wizard handles:
1. Database URL configuration
2. Storage path setup
3. Security (SECRET_KEY, KEK generation with Shamir shares)
4. MinIO backup configuration
5. LLM provider selection (OpenAI/Ollama)
6. SMTP email configuration
7. `.env` file generation
