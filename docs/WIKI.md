# LLM Wiki System

The EDMS LLM Wiki is an AI-powered knowledge base that incrementally builds structured, interlinked knowledge from ingested documents. Based on Andrej Karpathy's pattern of using LLMs to maintain a growing, self-updating wiki.

## Concept

Traditional document management systems treat documents as isolated artifacts. The LLM Wiki takes a different approach: as each document is ingested, the system extracts structured knowledge and integrates it into a persistent, navigable knowledge base.

Key principles:

1. **Incremental updates** - Each new document adds to existing knowledge rather than replacing it
2. **Entity-centric** - Information is organized around entities (people, organizations, technologies) and topics
3. **Cross-referencing** - Wiki pages link to each other, creating a navigable knowledge graph
4. **LLM-powered merging** - When new information about an existing entity arrives, an LLM intelligently merges it with prior knowledge
5. **Audit trail** - Every operation is logged with timestamps for traceability
6. **Self-healing** - The lint system detects orphaned pages, broken links, and stale references

## How the Wiki Grows

When a document is processed through the pipeline, the final step is wiki ingestion:

```
Document Upload
     │
     ▼
Processing Pipeline
     │
     ├── Convert to Markdown
     ├── Generate Summary
     ├── Extract Keywords
     ├── Create Embeddings
     ├── Index in ChromaDB
     │
     └── Wiki Ingest ◄── This step updates the wiki
          │
          ├── Extract entities (people, orgs, tech, places)
          ├── Extract topics (concepts, themes, subjects)
          ├── Create/update entity pages
          ├── Create/update topic pages
          ├── Create document summary page
          ├── Update index.md
          └── Log operation to log.md
```

### Entity Extraction

The LLM identifies entities mentioned in the document:
- **People** - Named individuals, authors, stakeholders
- **Organizations** - Companies, departments, teams
- **Technologies** - Software, tools, frameworks
- **Places** - Locations, offices, regions

### Topic Extraction

The LLM identifies high-level topics:
- Concepts discussed in the document
- Themes and subject areas
- Domain-specific terminology

### Page Merging

When a new document mentions an existing entity or topic:
1. The existing page content is loaded
2. New information from the document is provided to the LLM
3. The LLM merges the information, avoiding duplication
4. The merged page is saved back
5. Cross-references are updated

---

## Wiki File Structure

The wiki lives in the directory specified by `WIKI_PATH` (default: `wiki/`):

```
wiki/
├── index.md          # Master catalog of all content
├── log.md            # Chronological operation log
├── entities/         # Entity pages
│   ├── openai.md
│   ├── john-smith.md
│   ├── acme-corp.md
│   └── python.md
├── topics/           # Topic pages
│   ├── machine-learning.md
│   ├── document-management.md
│   └── security-best-practices.md
└── summaries/        # Per-document summaries
    ├── doc-1.md
    ├── doc-2.md
    └── doc-3.md
```

### index.md

The index serves as the catalog of all wiki content. It lists:
- All entity pages with brief descriptions
- All topic pages with brief descriptions
- All document summaries
- Cross-reference map

### log.md

A chronological record of all wiki operations:

```markdown
## Operations Log

### 2024-01-15 10:30:00
- Ingested: report.pdf
- Created entity: entities/acme-corp.md
- Updated topic: topics/quarterly-reports.md
- Created summary: summaries/doc-5.md

### 2024-01-15 11:00:00
- Ingested: policy.docx
- Updated entity: entities/acme-corp.md (merged new info)
- Created topic: topics/compliance.md
- Created summary: summaries/doc-6.md
```

### entities/

Each entity gets its own markdown page with:
- Description of the entity
- Key facts extracted from documents
- References to source documents
- Links to related entities and topics
- Last updated timestamp

### topics/

Each topic gets its own markdown page with:
- Overview of the topic
- Key points from across multiple documents
- Related entities
- Source document references
- Cross-links to related topics

### summaries/

One-page summaries for each ingested document:
- Document title and metadata
- Concise summary
- Key entities mentioned
- Key topics covered
- Upload date

---

## Wiki Operations

### Entity Extraction

The LLM is prompted to identify named entities:

```
Given the following document text, extract all named entities
(people, organizations, technologies, places) mentioned.
Return as a JSON list with type and name.
```

### Page Merging

When new information overlaps with existing wiki content:

```
You are maintaining a wiki page about [entity/topic].
Current page content: [existing content]
New information from document: [new content]

Merge the new information into the existing page:
- Do not duplicate information already present
- Add new facts and context
- Maintain consistent formatting
- Update cross-references
```

### Cross-Referencing

After updating pages, the system checks for cross-reference opportunities:
- If entity A mentions entity B, add a link
- If topic X relates to topic Y, add a "Related Topics" section
- Update index.md with any new pages or relationships

---

## Querying the Wiki

### API Endpoint

```
POST /api/wiki/query
{
  "question": "What do we know about the deployment architecture?"
}
```

### How Querying Works

1. The question is analyzed to identify relevant wiki pages
2. Relevant page content is loaded as context
3. The LLM generates an answer synthesizing information from multiple pages
4. Source pages are returned alongside the answer

### Response Format

```json
{
  "answer": "Based on the wiki, the deployment architecture uses...",
  "sources": ["topics/architecture.md", "entities/kubernetes.md"]
}
```

### Tips for Effective Queries

- Ask specific questions ("What is the backup schedule?") rather than vague ones ("Tell me about backups")
- Reference known entities or topics for focused answers
- Check the index first to see what knowledge is available

---

## Wiki Health Checks (Lint)

The lint system detects structural issues in the wiki:

```
POST /api/wiki/lint
```

### Issues Detected

| Issue | Description |
|-------|-------------|
| Orphaned pages | Pages not referenced by index.md |
| Broken links | Internal links pointing to non-existent pages |
| Empty pages | Pages with no meaningful content |
| Stale references | References to deleted documents |
| Missing cross-references | Entities mentioned but not linked |
| Duplicate entities | Same entity with multiple pages |

### Response Format

```json
{
  "issues": [
    "Orphaned page: entities/old-company.md (not in index)",
    "Broken link in topics/overview.md: ../entities/deleted.md",
    "Empty page: topics/placeholder.md"
  ]
}
```

### Resolving Issues

- **Orphaned pages** - Add to index.md or delete if obsolete
- **Broken links** - Update or remove the broken link
- **Empty pages** - Delete or populate with content
- **Stale references** - Update source references

---

## Configuration

### Required Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `WIKI_PATH` | `wiki` | Directory for wiki files |
| `LLM_PROVIDER` | `openai` | LLM provider (openai or ollama) |
| `OPENAI_API_KEY` | (empty) | Required if LLM_PROVIDER=openai |

### OpenAI Configuration

```env
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-your-key-here
```

Uses:
- `gpt-4` for entity extraction, merging, and querying
- `text-embedding-3-small` for semantic search

### Ollama Configuration

```env
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL_SUMMARIZE=llama3
OLLAMA_MODEL_KEYWORDS=llama3
OLLAMA_MODEL_EMBEDDINGS=nomic-embed-text
OLLAMA_MODEL_CHAT=llama3
```

---

## OpenAI vs Ollama Setup

### OpenAI (Cloud)

**Pros:**
- Higher quality outputs (GPT-4)
- No local hardware requirements
- Automatic scaling

**Cons:**
- Requires API key and costs money
- Data leaves your network
- Rate limits apply

**Setup:**
```env
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
```

### Ollama (Local)

**Pros:**
- Data stays on-premise
- No API costs
- No rate limits
- Works offline

**Cons:**
- Requires GPU hardware for good performance
- Lower quality than GPT-4 (depending on model)
- Requires model downloads (several GB each)

**Setup:**
```bash
# Install Ollama
curl -fsSL https://ollama.ai/install.sh | sh

# Pull models
ollama pull llama3          # For text generation
ollama pull nomic-embed-text # For embeddings

# Configure EDMS
cat >> .env << EOF
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL_SUMMARIZE=llama3
OLLAMA_MODEL_KEYWORDS=llama3
OLLAMA_MODEL_EMBEDDINGS=nomic-embed-text
OLLAMA_MODEL_CHAT=llama3
EOF
```

---

## Troubleshooting Wiki Issues

### Wiki Not Growing

**Symptom:** Documents are processed but wiki does not update.

**Causes:**
- LLM provider not configured (no API key)
- Wiki directory not writable
- Background task failing silently

**Solutions:**
1. Check `OPENAI_API_KEY` is set (or Ollama is running)
2. Verify wiki directory permissions: `ls -la wiki/`
3. Check application logs for errors during pipeline processing

### Empty Wiki Queries

**Symptom:** Wiki query returns generic or empty answers.

**Causes:**
- Wiki has no content yet (no documents processed)
- Question does not match any wiki page topics
- LLM provider returning errors

**Solutions:**
1. Check wiki index: `GET /api/wiki/index`
2. Verify wiki files exist: `ls wiki/entities/ wiki/topics/`
3. Process some documents and wait for wiki ingest to complete

### Wiki Lint Shows Many Issues

**Symptom:** Lint returns a long list of problems.

**Solutions:**
1. This is normal for wikis that have been growing over time
2. Address orphaned pages first (remove or re-index)
3. Fix broken links by updating page references
4. Consider re-processing key documents to refresh wiki content

### Duplicate Entity Pages

**Symptom:** Same entity has multiple pages (e.g., "OpenAI" and "openai").

**Causes:**
- Case sensitivity in entity extraction
- LLM inconsistency in naming

**Solutions:**
1. Manually merge duplicate pages
2. Update index.md to reference the canonical page
3. Delete the duplicate

### Large Wiki Performance

**Symptom:** Wiki queries become slow as wiki grows.

**Solutions:**
1. The wiki is file-based, so it scales with disk I/O
2. Consider moving wiki to SSD storage
3. Limit context size in queries (the system already truncates to prevent token overflow)
4. Archive old summary pages that are no longer relevant

---

## Obsidian Vault Export

EDMS can export the entire wiki as an Obsidian-compatible vault, enabling offline browsing and advanced knowledge management.

### Export Features

- **[[Wikilinks]]** - Internal page references are converted to Obsidian's `[[page name]]` link syntax
- **YAML Frontmatter** - Each page includes metadata (tags, creation date, source documents)
- **Dataview Properties** - Compatible with the Obsidian Dataview plugin for advanced queries
- **Folder Structure** - Preserves the wiki's directory layout (entities/, topics/, summaries/)

### Full Export

```
GET /api/wiki/export/obsidian
```

Returns a ZIP file containing the complete vault. Extract into your Obsidian vaults directory.

### Incremental Sync

For ongoing synchronization without re-downloading the full vault:

```
GET /api/wiki/export/obsidian/sync?since=2024-01-14T00:00:00
```

Returns a list of pages modified after the given timestamp. Use this to update only changed files in your local vault.

### Single Page Export

Retrieve a single page in Obsidian format:

```
GET /api/wiki/export/obsidian/page/{page_path}
```

### Recommended Obsidian Plugins

For the best experience with EDMS wiki exports:
- **Dataview** - Query and filter pages by frontmatter properties
- **Graph View** - Visualize page relationships (built into Obsidian)
- **Templates** - Create new pages matching the wiki's structure

---

## Document Relationships in Wiki Context

The document relationship system complements the wiki by providing explicit, typed connections between documents:

### Relationship Types

| Type | Meaning | Wiki Impact |
|------|---------|-------------|
| `parent` | Source is the parent document | Creates hierarchical links in wiki entities |
| `child` | Source is a child of target | Links child summaries to parent pages |
| `related` | General relationship | Adds "Related Documents" section to wiki pages |
| `supersedes` | Source replaces target | Updates wiki pages to reference the newer document |
| `references` | Source cites target | Adds cross-references in both wiki summaries |

### Graph Visualization

The relationship graph endpoint provides visualization-ready data:

```
GET /api/relationships/graph
```

Returns nodes (documents) and edges (relationships) suitable for rendering with graph visualization libraries (D3.js, Cytoscape, etc.).

### Orphan Detection

Detect documents with broken relationships (referencing deleted documents):

```
GET /api/relationships/orphaned
```

This helps maintain wiki integrity by identifying references that need updating.

### Transitive Dependencies

Find all documents that a given document depends on (directly or transitively):

```
GET /api/documents/{id}/dependencies
```

Useful for impact analysis when updating or archiving documents.
