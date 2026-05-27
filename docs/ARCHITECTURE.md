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
│  └───────────────────────────┬──────────────────────────────────┘   │
│                               │                                       │
│  ┌───────────────────────────▼──────────────────────────────────┐   │
│  │                     Service Layer (app/services/)              │   │
│  │  PipelineService | StorageService | WikiService               │   │
│  │  BulkService | LifecycleService | EmailNotificationService    │   │
│  │  VectorDBService | BackupService | KeyRecoveryManager         │   │
│  │  LdapService | RansomwareDetector                             │   │
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
| `workflow_entries` | Workflow action history (submit, approve, reject, sign off) |
| `document_lifecycles` | Lifecycle state machine per document |
| `lifecycle_transitions` | Audit trail of lifecycle state changes |
| `annotations` | User annotations on documents |

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

## API Layer Structure

Routes are organized into focused routers registered via `app/api/router.py`:

```python
api_router.include_router(auth_router)        # /api/auth/*
api_router.include_router(users_router)       # /api/users/*
api_router.include_router(groups_router)      # /api/groups/*
api_router.include_router(documents_router)   # /api/documents/*, /api/groups/{id}/documents
api_router.include_router(search_router)      # /api/search, /api/chat
api_router.include_router(wiki_router)        # /api/wiki/*
api_router.include_router(annotations_router) # /api/documents/{id}/annotations
api_router.include_router(workflow_router)    # /api/documents/{id}/workflow/*
api_router.include_router(bulk_router)        # /api/bulk/*
api_router.include_router(lifecycle_router)   # /api/documents/{id}/lifecycle, /api/lifecycle/*
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
