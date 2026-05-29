# EDMS - Enterprise Document Management System

An intelligent Enterprise Document Management System (EDMS) powered by LLM technology. EDMS combines traditional document management capabilities with an AI-driven wiki that incrementally builds a structured knowledge base from ingested documents, following Andrej Karpathy's LLM Wiki pattern.

**Production-Ready Features:**
- ✅ Drag-drop organizational chart builder with auto-reassignment on user resignation/termination/MIA
- ✅ Kanban-style workflow board with flow note editor
- ✅ Ransomware early detection with quarantine
- ✅ Airgap-ready with offline package generation
- ✅ Anti-AI-injection protection (PromptGuard)
- ✅ Airtight backup management with dual-key hierarchy
- ✅ RBAC based on organizational structure
- ✅ Scan-to-EDMS support (TWAIN/SANE)

## Key Capabilities

### Document Management
- **Document Upload & Organization** - Upload, organize, version, and retrieve documents (PDF, DOCX, images, text) with group-based folder hierarchy
- **Document Versioning** - Upload new versions with independent encryption per version, compare versions, and revert to prior versions
- **Document Audit Trail** - Immutable append-only log of all operations (upload, view, download, edit, approve, reject, version_create, revert, delete, share, annotate)
- **Document Preview** - Cached preview generation for PDFs (thumbnails), markdown (HTML), and images
- **Document Comparison** - Side-by-side diff of two documents or two versions with unified diff, similarity ratio, and metadata comparison
- **Document Relationships** - Typed relationships (parent, child, related, supersedes, references) with graph traversal and orphan detection
- **Bulk Operations** - Upload, approve, and sign off multiple documents in a single request with auto-folder creation
- **Batch Tagging** - Apply tags to multiple documents at once with color-coded tag management
- **Smart Folders** - Virtual folders with dynamic query-based document filtering
- **Document Templates** - Pre-configured templates with required fields, default lifecycle types, and extraction prompts
- **Offline Mode** - Generate self-contained ZIP packages with HTML viewer for offline document access
- **Import/Export Ecosystem** - Import from ZIP (with manifest.json) or CSV; full system export

### UX & User Interface
- **Drag-and-Drop Dashboard** - Drop files directly on folder cards for quick upload
- **Kanban Board** - Visual lifecycle management with drag-between-columns interface
- **Global Command Palette** - Ctrl+K shortcut for quick navigation and actions
- **Inline PDF Viewer** - Embedded pdf.js viewer for in-browser document viewing
- **Breadcrumb Navigation** - Hierarchical path display for folder traversal
- **Activity Feed/Timeline** - Chronological feed of system events and document changes
- **Onboarding Tour** - Interactive guided tour for new users

### AI & Document Intelligence
- **LLM Wiki** - AI-powered knowledge base that grows automatically as documents are ingested
- **RAG Search** - Semantic search and chat powered by vector embeddings (ChromaDB)
- **Natural Language Queries** - LLM translates plain English into structured search filters
- **Knowledge Graph Visualization** - Interactive vis.js graph showing entities, documents, and relationships
- **Comparative Analysis** - Multi-document LLM comparison with structured findings
- **Form Extraction** - LLM extracts structured key-value pairs from documents using templates
- **Document Expiry Prediction** - Statistical prediction of document expiry based on historical patterns
- **Citation Graph** - Auto-detected document references with visual relationship mapping
- **OCR Confidence Scoring** - Per-word confidence scores with document quality flags
- **Daily Notes** - LLM-powered daily digest summarizing recent document activity

### Collaboration & Workflow
- **Multi-Stage Approval Chains** - Sequential and parallel approval workflows with configurable steps
- **Comments/Discussion Threads** - Per-document threaded discussions with nested replies
- **@Mentions** - Mention users in comments to trigger notifications
- **Document Checkout/Lock** - Advisory locking with automatic expiry to prevent edit conflicts
- **E-Signature** - SHA-256 hash-based signatures with QR code generation and X.509 certificate support
- **Delegation/Proxy** - Delegate approval authority to another user with time-bound and scope-limited rules
- **SLA Tracking** - on_time/at_risk/breached status tracking with automatic escalation
- **Workflow Builder UI** - htmx-based drag-and-drop interface for designing approval workflows
- **Lifecycle Management** - Document lifecycle state machine with expiring/recurring review cycles and email alerts
- **Persistent Chat Sessions** - Multi-turn conversations with windowed history, scoped by document or group

### Obsidian & Knowledge Integration
- **Bi-directional Obsidian Sync** - Import Obsidian vault ZIPs with conflict resolution (Obsidian wins for user content, EDMS wins for summaries)
- **Obsidian Plugin Specification** - Plugin spec with TypeScript manifest, settings, and ribbon actions
- **Wiki Graph View** - vis.js interactive visualization showing all wiki pages as a navigable graph
- **Canvas/Whiteboard** - Spatial document arrangement with drag/resize, connections, and .canvas export
- **Obsidian Vault Export** - Export the wiki as an Obsidian-compatible vault with [[wikilinks]], YAML frontmatter

### Security & Compliance
- **RBAC** - Role-Based Access Control with fine-grained permissions, folder assignments, and organizational hierarchy
- **Encryption** - AES-256-GCM envelope encryption for documents at rest with Shamir Secret Sharing for key recovery
- **KMS Abstraction** - Pluggable Key Management Service with LocalFileKMS, VaultKMS, and CosmianKMS providers
- **Geo-Fencing** - IP range and country-based access rules with allow/deny actions per scope
- **Watermarking** - PDF/image overlay with configurable text templates, opacity, and position per group
- **Access Request Workflow** - Users can request access to restricted resources; admins approve or deny
- **Session Recording** - Track all documents accessed per user session with timestamps and actions
- **Compliance Reporting** - Generate reports for access logs, encryption status, retention compliance, and permission audits
- **Anti-AI Prompt Injection** - PromptGuard service detecting 5 categories of injection patterns
- **Security Monitoring** - Ransomware detection, auditd/falco/suricata config generation, KMS rate limiting
- **Backup KEK Isolation** - Separate backup key hierarchy from production for defense in depth

### Operations & Reliability
- **Health Score Dashboard** - Composite 0-100 score with component breakdown (orphan, lifecycle, backup, security, storage, SLA)
- **Scheduled Reports** - Cron-configurable email reports with customizable filters and recipient lists
- **Multi-Tenant Support** - Tenant isolation with slug-based routing and per-tenant settings
- **Webhook Integrations** - HMAC-signed outbound webhooks for document events, lifecycle changes, and system alerts
- **WebSocket Notifications** - Real-time push notifications for document status, lifecycle alerts, ransomware, and backup events
- **Health Monitoring** - Orphaned lifecycle detection, broken reviewers, empty groups, stale documents
- **LDAP Integration** - Synchronize users and roles from enterprise LDAP/Active Directory
- **Backup & DR** - Automated backups to MinIO (primary/DR) and Restic with configurable schedules
- **Comprehensive Error Handling** - Structured error responses with error codes, X-Request-ID tracking, rate limiting, and circuit breaker
- **Setup Wizard** - CLI and web-based first-launch wizard for .env generation, DB setup, KEK/Shamir, MinIO, LLM, and SMTP configuration

## Technology Stack

| Component | Technology |
|-----------|------------|
| Web Framework | FastAPI (async) |
| Language | Python 3.11+ |
| Database | SQLAlchemy 2.0 (async) with SQLite/PostgreSQL |
| Vector DB | ChromaDB |
| LLM Integration | OpenAI API / Ollama (local) |
| AI Framework | LangChain |
| PDF Processing | PyMuPDF, pikepdf |
| OCR | Tesseract (pytesseract) |
| Auth | JWT (python-jose), bcrypt |
| Package Manager | uv |
| Linting | Ruff |
| Testing | pytest + pytest-asyncio + httpx |

## Quick Start

```bash
# Prerequisites: Python 3.11+ via pyenv, uv package manager

# Set Python version
pyenv local 3.11.15

# Install dependencies
uv sync

# Create .env file
cat > .env << EOF
OPENAI_API_KEY=sk-your-api-key-here
SECRET_KEY=your-secure-secret-key
PDF_ENCRYPTION_PASSWORD=your-pdf-password
EOF

# Start the server
uv run uvicorn app.main:app --reload

# Run tests
uv run pytest tests/ -v

# Lint
uv run ruff check app/ tests/
```

The API is available at `http://localhost:8000`. Interactive docs at `http://localhost:8000/docs`.

Default admin credentials: `admin` / `admin` (change immediately in production).

## Documentation

| Document | Description |
|----------|-------------|
| [ARCHITECTURE.md](ARCHITECTURE.md) | System architecture, component diagrams, database schema |
| [DATA_DICTIONARY.md](DATA_DICTIONARY.md) | Complete model reference with all fields and relationships |
| [DEVELOPER_GUIDE.md](DEVELOPER_GUIDE.md) | Setup, coding conventions, how to extend the system |
| [API_COOKBOOK.md](API_COOKBOOK.md) | Copy-pasteable curl examples for every endpoint |
| [HOWTO.md](HOWTO.md) | Step-by-step guides for common tasks |
| [OPERATIONS_RUNBOOK.md](OPERATIONS_RUNBOOK.md) | Deployment, monitoring, backup, incident response |
| [PRODUCTION_READINESS.md](PRODUCTION_READINESS.md) | **NEW** Production deployment checklist, security hardening, HA setup, monitoring, DR procedures |
| [SECURITY.md](SECURITY.md) | Authentication, encryption, RBAC, threat model |
| [TROUBLESHOOTING.md](TROUBLESHOOTING.md) | Common issues with symptoms, causes, and solutions |
| [USER_GUIDE.md](USER_GUIDE.md) | End-user guide for document management |
| [WIKI.md](WIKI.md) | LLM Wiki system documentation |

## Project Structure

```
edms/
├── app/
│   ├── api/           # FastAPI route handlers
│   ├── core/          # Config, database, security, LLM utilities
│   ├── models/        # SQLAlchemy ORM models
│   ├── schemas/       # Pydantic request/response schemas
│   ├── services/      # Business logic services
│   └── templates/     # Jinja2 HTML templates
├── tests/             # pytest test suite
├── data/              # Runtime file storage
├── wiki/              # LLM wiki markdown files
├── chroma_db/         # ChromaDB vector database
├── docs/              # This documentation
└── pyproject.toml     # Project configuration
```

## License

Enterprise proprietary software. All rights reserved.
