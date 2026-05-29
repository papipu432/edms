# Security

This document covers the security architecture of EDMS, including authentication, authorization, encryption, and best practices.

## Authentication

### JWT Token Authentication

EDMS uses JSON Web Tokens (JWT) for API authentication:

- **Algorithm:** HS256 (HMAC-SHA256)
- **Secret:** Configured via `SECRET_KEY` environment variable
- **Expiration:** `ACCESS_TOKEN_EXPIRE_MINUTES` (default: 30 minutes)
- **Token type:** Bearer token in `Authorization` header

Token flow:
1. User sends credentials to `POST /api/auth/login`
2. Server validates credentials against stored bcrypt hash
3. Server generates JWT with `sub` claim set to username
4. Client includes token in subsequent requests: `Authorization: Bearer <token>`
5. Server validates token signature and expiration on each request

### Session Cookies

For the web UI, EDMS also supports session cookies:
- Cookie name: `access_token`
- HttpOnly: Yes (not accessible via JavaScript)
- SameSite: Lax
- Secure: Set to true when using HTTPS
- Contains the same JWT token as Bearer auth

### Password Hashing

- Algorithm: bcrypt (via passlib)
- Library: bcrypt==4.0.1
- Passwords are never stored in plain text

### LDAP Authentication

When LDAP is configured, users can authenticate against an enterprise directory:
- Connection: LDAP/LDAPS with optional STARTTLS
- Bind authentication for service account
- User search and password verification against LDAP server
- Automatic user creation on first LDAP login
- See [HOWTO.md](HOWTO.md) for LDAP setup instructions

---

## Authorization (RBAC)

### Role-Based Access Control Model

EDMS implements a three-layer RBAC model:

```
Users <--N:M--> Roles <--N:M--> Permissions (resource:action)
```

### System Roles

| Role | Scope | Key Permissions |
|------|-------|-----------------|
| admin | Full system | All permissions (wildcard) |
| manager | Org management | Users, roles, org structure, documents, reports |
| operator | Org operations | Read access + org assignment management |
| viewer | Read-only | Read access to users, org, documents, reports |
| editor | Document editing | Create, read, update documents |
| reviewer | Document review | Read documents |
| annotator | Annotations | Read documents (+ annotation creation) |
| approver | Workflow approval | Read + update documents |

### Folder Assignments

Fine-grained access control at the folder level:

```
User + FolderPath + Role = Scoped Permission
```

Example: User "jane" has "editor" role for folder "/Engineering/Reports"

### Permission Enforcement

Endpoints use FastAPI dependency injection for authorization:

```python
# Any authenticated user
Depends(get_current_user)

# Specific roles
Depends(role_required(["editor", "admin"]))

# Single role
Depends(require_role("admin"))

# Permission-based
Depends(require_permission("documents", "create"))
```

### Workflow Role Restrictions

| Action | Allowed Roles |
|--------|--------------|
| submit_review | editor, admin, annotator |
| approve | approver, admin |
| reject | reviewer, admin |
| request_changes | reviewer, admin |
| sign_off | approver, admin |

---

## Encryption at Rest

### AES-256-GCM Envelope Encryption

EDMS uses envelope encryption for documents stored at rest:

```
┌─────────────────────────────────────────┐
│         Envelope Encryption             │
│                                         │
│  Master Key (KEK)                       │
│    - Generated on initialization        │
│    - Stored encrypted with passphrase   │
│    - Protected by Shamir shares         │
│                                         │
│  Per-Document Key (DEK)                 │
│    - Random AES-256 key per document    │
│    - Encrypted with KEK for storage     │
│    - Used for AES-256-GCM encryption    │
│                                         │
│  Encryption Process:                    │
│    1. Generate random DEK               │
│    2. Encrypt document with DEK (GCM)   │
│    3. Encrypt DEK with KEK              │
│    4. Store encrypted DEK alongside doc  │
└─────────────────────────────────────────┘
```

### Key Hierarchy

- **KEK (Key Encryption Key):** Master key that encrypts/decrypts DEKs
- **DEK (Data Encryption Key):** Per-document key for AES-256-GCM encryption
- **Passphrase:** User-provided passphrase that encrypts the KEK at rest

### Initialization

```bash
POST /api/settings/encryption/init
{
  "threshold": 2,      # Minimum shares needed for recovery
  "num_shares": 3,     # Total shares to generate
  "passphrase": "...", # KEK encryption passphrase
  "share_holders": ["alice", "bob", "charlie"]
}
```

---

## Key Management

### KEK/DEK Model

The two-tier key model provides:
- **Key rotation:** Rotate KEK without re-encrypting all documents
- **Access control:** KEK access is restricted to administrators
- **Recovery:** Multiple recovery paths (passphrase or Shamir shares)

### Key Storage

- KEK is stored encrypted with the passphrase at: `{STORAGE_PATH}/.keys/kek.enc`
- Key metadata is stored in the `encryption_keys` database table
- Share records are stored in the `key_shares` table

---

## Key Recovery (Shamir Secret Sharing)

### Concept

Shamir Secret Sharing splits the KEK into N shares where any K shares (threshold) can reconstruct the secret:
- No single person can access the key alone
- The system tolerates loss of (N - K) shares
- Mathematically proven security

### Recovery Process

1. Collect threshold number of shares from designated holders
2. Submit shares to the recovery endpoint:
   ```bash
   POST /api/settings/encryption/recover
   {
     "shares": [
       {"index": 1, "share_hex": "..."},
       {"index": 3, "share_hex": "..."}
     ]
   }
   ```
3. Server reconstructs KEK and verifies against stored key ID (SHA-256 hash)
4. If verification passes, encryption operations can resume

### Share Distribution Best Practices

- Store shares in physically separate locations
- Use tamper-evident envelopes for physical shares
- Record share holders in the `key_shares` database table
- Never store multiple shares together
- Test recovery procedure annually

---

## PDF Password Encryption

In addition to envelope encryption, PDFs receive password-based encryption:

- **Library:** pikepdf
- **Password:** Configured via `PDF_ENCRYPTION_PASSWORD` environment variable
- **Purpose:** Additional protection for the most common document format
- **Storage:** Encrypted PDF saved to `encrypted_pdf_path` alongside original

This provides defense in depth: even if storage is compromised, PDFs require the password to open.

---

## Ransomware Detection

EDMS includes a file system monitoring service that detects ransomware-like behavior:

### How It Works

1. **File system watcher** monitors the `STORAGE_PATH` directory
2. **Rate detection** tracks file operations per second
3. **Threshold alerts** trigger when operations exceed `threshold_ops_per_sec` within `window_seconds`
4. **Quarantine** isolates suspicious files

### Configuration

```bash
# Get current config
GET /api/security/config

# Update thresholds
POST /api/security/config
{
  "threshold_ops_per_sec": 50,
  "window_seconds": 10,
  "monitored_dir": "/app/storage"
}
```

### Alert Management

```bash
# Start monitoring
POST /api/security/monitor/start

# Stop monitoring
POST /api/security/monitor/stop

# View alerts
GET /api/security/alerts

# Acknowledge alert
POST /api/security/alerts/{alert_id}/acknowledge
```

---

## LDAP Integration Security

### Connection Security

- Support for LDAPS (SSL) and STARTTLS
- Configurable connection timeout
- Service account bind (no anonymous access)

### Credential Handling

- LDAP bind passwords stored in database (consider encryption)
- User passwords never stored locally for LDAP users
- Authentication always delegated to LDAP server

### Sync Security

- Optional: Disable missing users on sync (`sync_disable_missing`)
- Group-to-role mapping for automatic role assignment
- All sync operations logged in `ldap_sync_logs`

---

## Threat Model

### Assets

| Asset | Sensitivity | Protection |
|-------|------------|------------|
| Documents | High | AES-256-GCM encryption, PDF passwords, per-version DEKs |
| User credentials | Critical | bcrypt hashing, JWT tokens |
| KEK | Critical | Passphrase encryption, Shamir shares, KMS wrapping |
| Backup KEK | Critical | Isolated key hierarchy, KMS wrapped |
| Database | High | File permissions, backups |
| Wiki content | Medium | File system permissions |
| API tokens | High | Short expiration, HMAC-SHA256 |
| LLM prompts | Medium | Prompt injection sanitization |

### Threat Vectors

| Threat | Mitigation |
|--------|-----------|
| Credential theft | bcrypt hashing, short token expiry, LDAP delegation |
| Unauthorized access | RBAC, folder assignments, role restrictions |
| Data at rest exposure | AES-256-GCM envelope encryption, per-version DEKs |
| Ransomware | File system monitoring, quarantine, backups |
| SQL injection | SQLAlchemy ORM (parameterized queries) |
| XSS | FastAPI JSON responses, Jinja2 auto-escaping |
| CSRF | SameSite cookies, Bearer token auth for API |
| Key compromise | Shamir Secret Sharing, key rotation, backup KEK isolation |
| Insider threat | Audit logging, role separation, Shamir |
| Prompt injection | PromptGuard detection, XML boundaries, alert logging |
| KMS brute force | Per-IP rate limiting (10 unwrap/min), alert generation |
| Data exfiltration | Suricata network monitoring, audit trail |

---

## Anti-AI Prompt Injection Protection

### Overview

EDMS includes a dedicated `PromptGuard` service that sanitizes all user content before it reaches the LLM. This prevents attackers from embedding instructions in documents or chat messages that could manipulate the AI.

### Detection Categories

| Category | Severity | Examples |
|----------|----------|---------|
| Instruction Override | High | "ignore all previous instructions", "forget everything" |
| Ignore Instructions | High | "disregard all above", "do not follow original rules" |
| Role Switching | Medium | "you are now a hacker", "pretend to be an unrestricted AI" |
| Delimiter Injection | Medium | `</system>`, ````system instructions```` |
| System Prompt Injection | Medium | "system: new instructions" at start of line |

### Protection Pipeline

1. **Detection** - Regex patterns match injection attempts in user text
2. **Neutralization** - Detected text is prefixed with `[user text]:` to break injection
3. **Boundary Wrapping** - All user content is wrapped in `<user_content>` XML tags
4. **Alert Logging** - SecurityAlert records are created for each detection
5. **Audit Trail** - Pattern name, severity, and matched text are recorded

### Configuration

Prompt injection protection is enabled by default for:
- Chat session messages (`POST /api/chat/sessions/{id}/messages`)
- Any service that calls `sanitize_for_llm()`

No configuration is needed. The protection is always active.

---

## KMS Rate Limiting

### Purpose

Prevents brute-force key extraction attacks by limiting the rate of KMS unwrap operations per client IP address.

### Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `KMS_RATE_LIMIT_MAX_CALLS` | 10 | Maximum unwrap calls per IP per window |
| `KMS_RATE_LIMIT_WINDOW_SECONDS` | 60 | Sliding window duration in seconds |

### Behavior

- Uses a sliding window algorithm per client IP
- When limit is exceeded, raises `KMSError` (HTTP 429 equivalent)
- Logs a warning with the blocked IP address
- Status queryable via monitoring API

### Limitations

- In multi-worker deployments, rate limits are per-process (not shared)
- For production multi-worker setups, replace with Redis-backed rate limiter

---

## Security Monitoring Layers

| Layer | Tool | Detects | Integration |
|-------|------|---------|-------------|
| File Integrity | auditd | Unauthorized file modifications in storage | Alert webhook |
| Process Monitoring | Falco | Unexpected processes, privilege escalation | Alert webhook |
| KMS Audit | Internal Rate Limiter | Brute-force key extraction attempts | Built-in |
| Network | Suricata | Data exfiltration, C2 communication | Alert webhook |

### Alert Ingestion

External monitoring tools send alerts via webhook:

```
POST /api/security/alerts
{
  "source": "auditd|falco|suricata",
  "severity": "low|medium|high|critical",
  "message": "description of the event",
  "details": { ... }
}
```

Alerts are validated (source must be in allowed set), stored as `SecurityAlert` records, and appear in the security dashboard.

---

## Key Isolation Principles

### Production vs Backup Key Hierarchies

EDMS maintains two separate key hierarchies to prevent cross-contamination:

```
Production Key Hierarchy          Backup Key Hierarchy
========================          ====================
Production KEK                    Backup KEK
  └── wrapped by KMS               └── wrapped by same KMS
      └── wraps DEKs                    └── wraps backup DEKs
          └── per-document                  └── per-backup-operation
              encryption                        encryption
```

**Rationale:**
- Compromising backup keys does not expose production documents
- Compromising production keys does not expose backup archives
- Each hierarchy can be independently rotated
- Backup KEK can use different Shamir share distribution than production

### KMS Provider Independence

The KMS abstraction ensures:
- Raw key material never leaves the KMS boundary
- Keys are only transmitted in wrapped form
- The wrapping algorithm (AES-256-GCM with scrypt-derived root key for LocalFileKMS) provides authenticated encryption
- Provider can be swapped without re-encrypting existing data (re-wrap operation)

---

## Security Best Practices

1. **Change all default credentials** before deploying to production
2. **Use HTTPS** with TLS 1.2+ (terminate at reverse proxy)
3. **Set strong SECRET_KEY** (64+ random characters)
4. **Disable open registration** (`ALLOW_REGISTRATION=false`)
5. **Configure CORS** with specific origins (not `*`)
6. **Use LDAP** for enterprise authentication
7. **Initialize encryption** and distribute Shamir shares
8. **Enable ransomware monitoring** for storage directories
9. **Configure automated backups** to both primary and DR targets
10. **Review audit logs** (workflow entries, org change history, LDAP sync logs)
11. **Rotate JWT secret** periodically (invalidates all active sessions)
12. **Limit upload sizes** at the reverse proxy level
13. **Run as non-root** in Docker containers
14. **Keep dependencies updated** (`uv sync` with latest versions)

---

## Hardening Checklist

Before going to production, verify each item:

- [ ] `SECRET_KEY` is set to a unique, random value (not the default)
- [ ] `PDF_ENCRYPTION_PASSWORD` is set to a strong password (not "changeme")
- [ ] `BOOTSTRAP_ADMIN_PASSWORD` is changed from default
- [ ] `ALLOW_REGISTRATION` is set to `false`
- [ ] HTTPS is configured (TLS termination at reverse proxy)
- [ ] CORS origins are restricted to known domains
- [ ] Encryption is initialized (`POST /api/settings/encryption/init`)
- [ ] Shamir shares are distributed to separate holders
- [ ] Backup is configured and tested (both primary and DR)
- [ ] LDAP is configured (if enterprise environment)
- [ ] Ransomware monitoring is active
- [ ] File upload size limits are configured at proxy level
- [ ] Application runs as non-root user
- [ ] Database file has restricted permissions (600)
- [ ] Storage directory has restricted permissions (700)
- [ ] Log rotation is configured
- [ ] Firewall rules restrict database port access
- [ ] OpenAI API key has spending limits configured

---

## Geo-Fencing Architecture

### Overview

EDMS implements IP-based and country-based access control through a middleware layer that evaluates rules before requests reach route handlers.

### Rule Evaluation Order

1. Rules are loaded from the `geofence_rules` table
2. More specific scopes (document > group > global) take priority
3. Within a scope, deny rules are evaluated before allow rules
4. If a deny rule matches, the request is blocked with 403
5. If no rules match, the default is to allow access

### IP Range Matching

Uses CIDR notation for IP range matching:
- `192.168.1.0/24` - Matches all IPs in the 192.168.1.x range
- `10.0.0.0/8` - Matches all 10.x.x.x addresses
- `0.0.0.0/0` - Matches all IPv4 addresses

### Country Detection

Country-based filtering requires a GeoIP database (MaxMind GeoLite2 or similar). When configured:
- Client IP is resolved to ISO 3166-1 alpha-2 country code
- Matched against `allowed_countries` or `denied_countries` lists

### Security Considerations

- Geo-fencing is defense-in-depth; it does not replace authentication
- VPN users may appear to be in a different country
- Always maintain emergency access procedures for geo-fence failures
- Log all denied requests for audit purposes

---

## Watermarking Forensics

### How Watermarks Work

EDMS applies forensic watermarks to documents when downloaded or previewed:

1. **Template Expansion**: Variables in `text_template` are replaced:
   - `{user}` - Username of the requesting user
   - `{timestamp}` - Current ISO timestamp
   - `{doc_id}` - Document ID
   
2. **Overlay Application**: 
   - PDF: Text overlay with configurable opacity and position
   - Images: Semi-transparent text burned into the image

3. **Traceability**: If a watermarked document leaks, the embedded user/timestamp identifies the source

### Configuration Per Group

Different groups can have different watermark settings:
- Public docs: No watermark (enabled=false)
- Internal docs: Light watermark (opacity=0.1)
- Confidential: Bold watermark (opacity=0.5, position=diagonal)

### Forensic Investigation

When a leaked document is found:
1. Examine the watermark text to identify the user
2. Cross-reference with session recording to confirm download
3. Review the user's session history for other downloads

---

## E-Signature Verification

### Signature Architecture

EDMS signatures combine multiple verification methods:

1. **SHA-256 Hash**: Document content hash at time of signing
2. **QR Code**: Contains verification URL and signature hash
3. **X.509 Certificate** (optional): Cryptographic binding to signer identity

### Verification Process

To verify a signature:
```bash
curl http://localhost:8000/api/signatures/verify/{signature_hash}
```

The system checks:
1. The signature record exists in the database
2. The stored hash matches the current document content hash
3. If a certificate is present, the signature cryptographically verifies
4. The `is_valid` flag has not been revoked

### Signature Invalidation

A signature becomes invalid when:
- The document content changes after signing (hash mismatch)
- An administrator manually revokes the signature
- The signing certificate is revoked or expired

### Audit Trail

All signature operations are logged:
- Who signed
- When they signed
- The document hash at signing time
- Whether a certificate was used

---

## Access Request Audit

### Audit Trail for Access Requests

Every access request lifecycle is tracked:
- Request creation (who, what resource, why)
- Review decision (who approved/denied, when)
- Access grant/revocation

### Compliance Reporting

Generate access request audit reports:
```bash
curl -X POST http://localhost:8000/api/compliance/reports \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"report_type": "access_log"}'
```

### Review Process

1. User submits access request with reason
2. Admin reviews pending requests
3. Admin approves or denies with audit record
4. If approved, user gains access immediately
5. All decisions are immutable and timestamped

---

## Session Recording Privacy

### What is Recorded

The session recording system tracks:
- Session start/end times
- Client IP address and user agent
- Documents accessed (view, download, edit actions)
- Timestamps for each access

### What is NOT Recorded

- Document content viewed
- Screen captures or keystrokes
- Non-document page views
- Passwords or authentication tokens

### Data Retention

Configure session data retention in production:
- Default: Sessions retained indefinitely
- Recommendation: Implement periodic purging of sessions older than retention period
- Comply with GDPR/privacy requirements for your jurisdiction

### Access to Session Data

Only administrators can query session data:
```bash
curl http://localhost:8000/api/sessions -H "Authorization: Bearer $TOKEN"
```

Users cannot view their own session recordings through the standard API.

---

## Webhook Secret Rotation

### Why Rotate Secrets

Webhook secrets should be rotated:
- Periodically (every 90 days recommended)
- When personnel with access leave the organization
- After any suspected compromise
- When the receiving system is migrated

### Rotation Procedure

1. **Generate new secret** on the receiver side
2. **Update EDMS webhook config**:
   ```bash
   curl -X PUT http://localhost:8000/api/webhooks/1 \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"secret": "new-rotated-secret"}'
   ```
3. **Verify delivery** with a test event:
   ```bash
   curl -X POST http://localhost:8000/api/webhooks/1/test \
     -H "Authorization: Bearer $TOKEN"
   ```
4. **Remove old secret** from the receiver once verified

### HMAC Signature Format

Webhooks use HMAC-SHA256:
```
X-Webhook-Signature: <hex-encoded HMAC-SHA256(secret, raw_body)>
```

---

## Multi-Tenant Isolation Guarantees

### Data Isolation

- **Database**: All queries include tenant_id filter; cross-tenant access is architecturally prevented
- **Storage**: Separate file system paths per tenant
- **Search**: ChromaDB collections are tenant-scoped
- **Wiki**: Each tenant has an independent wiki directory

### Configuration Isolation

- Tenant settings (JSON column) control per-tenant behavior
- Feature flags can enable/disable features per tenant
- Storage quotas are enforced per tenant

### Security Boundaries

- Authentication tokens are tenant-scoped
- Admin of one tenant cannot access another tenant's data
- System administrators (super-admins) can manage all tenants
- Tenant deactivation immediately blocks all access

### Testing Isolation

Regularly verify isolation with automated tests:
1. Create data in Tenant A
2. Switch to Tenant B context
3. Verify Tenant A's data is not accessible
4. Test all endpoints with cross-tenant scenarios

---

## Auto-Reassignment Security

### User Status Management

The system tracks user employment status for automatic task reassignment:

| Status | Description | Auto-Reassignment Triggered |
|--------|-------------|----------------------------|
| `active` | Normal employment | No |
| `resigned` | Voluntary resignation | Yes - immediate |
| `terminated` | Involuntary termination | Yes - immediate |
| `mia` | Missing/unreachable > 7 days | Yes - after grace period |
| `on_leave` | Temporary leave (vacation, medical) | Optional - based on duration |

### Escalation Hierarchy

When auto-reassignment triggers, tasks escalate through:
1. **Same position** - Other users in the same org position
2. **Position head** - User marked as head of the position
3. **Unit head** - Head of the organizational unit
4. **Parent unit head** - Escalate up the org tree
5. **System admin** - Final fallback

### Audit Trail

All auto-reassignments are logged:
- Original assignee and their status
- New assignee and escalation path taken
- Timestamp and triggering event
- Affected workflow tasks/documents

### Prevention of Abuse

- Only users with `manager` or `admin` role can change user status
- Status changes require reason field
- All status changes logged in audit trail
- MIA detection requires multiple failed contact attempts

---

## Airgap Deployment Security

### Offline Package Generation

For airgap environments, EDMS supports offline package generation:
- Self-contained ZIP archives with embedded HTML viewer
- Documents encrypted with recipient-specific keys
- No external network calls required
- Packages can be transferred via secure media

### Ransomware Early Detection in Airgap

Even in airgap deployments:
- Filesystem monitoring runs locally
- Entropy analysis detects encryption patterns
- Quarantine isolates suspicious files
- Alerts logged for admin review

### Backup Key Isolation

Airgap backup strategy:
- Production KEK never leaves primary environment
- Backup KEK stored separately
- Encrypted backups can be transferred to DR site
- Key recovery requires Shamir share holders from both sites
