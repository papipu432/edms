# EDMS - Enterprise Document Management System

An intelligent document management system with an LLM-powered wiki that incrementally builds a knowledge base from ingested documents. Based on Andrej Karpathy's LLM Wiki pattern.

## Architecture

The system has three layers: raw document sources, a processing pipeline, and a persistent LLM wiki.

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

Documents are uploaded via the API in various formats (PDF, DOCX, images, text). Each document belongs to a group for organization.

### Layer 2: Processing Pipeline

When a document is uploaded, a background task processes it through:

1. **Conversion** - PDF/DOCX/image to Markdown using PyMuPDF, python-docx, and Tesseract OCR
2. **Summarization** - LLM generates a concise summary
3. **Keyword Extraction** - LLM extracts key terms
4. **Chunking** - Text is split into overlapping chunks for retrieval
5. **Embedding** - Chunks are embedded using OpenAI text-embedding-3-small
6. **Vector Indexing** - Embeddings stored in ChromaDB for semantic search
7. **Wiki Ingest** - Extracted knowledge is integrated into the LLM wiki

### Layer 3: LLM Wiki

Inspired by Karpathy's pattern, the wiki is a persistent, interlinked set of markdown files that grows with each ingested document:

- **index.md** - Catalog of all documents, entities, and topics
- **entities/** - Pages for people, organizations, technologies, places
- **topics/** - Pages for concepts, themes, and subjects
- **summaries/** - One-page summaries per document
- **log.md** - Chronological record of all wiki operations

The wiki uses LLM calls to:
- Extract entities and topics from new documents
- Merge new information into existing pages without duplication
- Answer questions by synthesizing information across pages
- Maintain cross-references between related pages

## Setup

### Prerequisites

- Python 3.11+ (via pyenv)
- [uv](https://docs.astral.sh/uv/) package manager

### Installation

```bash
# Set Python version
pyenv local 3.11.15

# Install dependencies
uv sync
```

### Environment Variables

Create a `.env` file in the project root:

```env
OPENAI_API_KEY=sk-your-api-key-here
PDF_ENCRYPTION_PASSWORD=your-encryption-password
```

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENAI_API_KEY` | Yes (for LLM features) | OpenAI API key for summaries, embeddings, wiki |
| `PDF_ENCRYPTION_PASSWORD` | No | Password for encrypting stored PDFs (default: "changeme") |
| `WIKI_PATH` | No | Directory for wiki files (default: "wiki") |
| `STORAGE_PATH` | No | Directory for uploaded files (default: "storage") |
| `DATABASE_URL` | No | SQLAlchemy database URL (default: SQLite) |
| `CHROMA_DB_PATH` | No | ChromaDB persistence directory (default: "./chroma_db") |

## Running

### Start the server

```bash
uv run uvicorn app.main:app --reload
```

The API will be available at `http://localhost:8000`.

### Run tests

```bash
uv run pytest tests/ -v
```

### Lint

```bash
uv run ruff check app/ tests/
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| **Groups** | | |
| POST | `/api/groups` | Create a new group |
| GET | `/api/groups` | List all groups |
| GET | `/api/groups/{id}` | Get group details |
| PUT | `/api/groups/{id}` | Update a group |
| DELETE | `/api/groups/{id}` | Delete a group |
| **Documents** | | |
| POST | `/api/groups/{id}/documents` | Upload a document |
| GET | `/api/groups/{id}/documents` | List documents in group |
| GET | `/api/documents/{id}/status` | Get document processing status |
| GET | `/api/documents/{id}/markdown` | Get converted markdown content |
| **Search & Chat** | | |
| POST | `/api/search` | Semantic search across documents |
| POST | `/api/chat` | RAG-powered chat with sources |
| **Wiki** | | |
| GET | `/api/wiki/index` | Get wiki index and page list |
| GET | `/api/wiki/pages/{path}` | Get a specific wiki page |
| POST | `/api/wiki/query` | Ask a question against the wiki |
| POST | `/api/wiki/lint` | Run wiki health check |
| GET | `/api/wiki/log` | View recent wiki operations |

## LLM Wiki Concept

The LLM Wiki is based on [Andrej Karpathy's pattern](https://x.com/karpathy) of using LLMs to incrementally build and maintain a structured knowledge base. Instead of treating documents as isolated artifacts, the system extracts structured knowledge and integrates it into a growing wiki.

Key principles:

1. **Incremental updates** - Each new document adds to existing knowledge rather than replacing it
2. **Entity-centric** - Information is organized around entities (people, orgs, technologies) and topics
3. **Cross-referencing** - Wiki pages link to each other, creating a navigable knowledge graph
4. **LLM-powered merging** - When new information about an existing entity arrives, an LLM intelligently merges it with prior knowledge
5. **Audit trail** - Every operation is logged with timestamps for traceability
6. **Self-healing** - The lint system detects orphaned pages, broken links, and stale references
