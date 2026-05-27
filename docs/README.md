# EDMS - Enterprise Document Management System

An intelligent Enterprise Document Management System (EDMS) powered by LLM technology. EDMS combines traditional document management capabilities with an AI-driven wiki that incrementally builds a structured knowledge base from ingested documents, following Andrej Karpathy's LLM Wiki pattern.

## Key Capabilities

- **Document Management** - Upload, organize, version, and retrieve documents (PDF, DOCX, images, text) with group-based folder hierarchy
- **LLM Wiki** - AI-powered knowledge base that grows automatically as documents are ingested, extracting entities, topics, and summaries
- **RAG Search** - Semantic search and chat powered by vector embeddings (ChromaDB) for intelligent document retrieval
- **RBAC** - Role-Based Access Control with fine-grained permissions, folder assignments, and organizational hierarchy
- **Encryption** - AES-256-GCM envelope encryption for documents at rest with Shamir Secret Sharing for key recovery
- **Bulk Operations** - Upload, approve, and sign off multiple documents in a single request with auto-folder creation
- **Lifecycle Management** - Document lifecycle state machine with expiring/recurring review cycles and email alerts
- **Workflow** - Multi-step approval workflows (submit review, approve, reject, request changes, sign off)
- **LDAP Integration** - Synchronize users and roles from enterprise LDAP/Active Directory
- **Backup & DR** - Automated backups to MinIO (primary/DR) and Restic with configurable schedules
- **Security Monitoring** - Ransomware detection with file system monitoring and alert management

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
