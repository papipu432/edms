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
| Documents | High | AES-256-GCM encryption, PDF passwords |
| User credentials | Critical | bcrypt hashing, JWT tokens |
| KEK | Critical | Passphrase encryption, Shamir shares |
| Database | High | File permissions, backups |
| Wiki content | Medium | File system permissions |
| API tokens | High | Short expiration, HMAC-SHA256 |

### Threat Vectors

| Threat | Mitigation |
|--------|-----------|
| Credential theft | bcrypt hashing, short token expiry, LDAP delegation |
| Unauthorized access | RBAC, folder assignments, role restrictions |
| Data at rest exposure | AES-256-GCM envelope encryption |
| Ransomware | File system monitoring, quarantine, backups |
| SQL injection | SQLAlchemy ORM (parameterized queries) |
| XSS | FastAPI JSON responses, Jinja2 auto-escaping |
| CSRF | SameSite cookies, Bearer token auth for API |
| Key compromise | Shamir Secret Sharing, key rotation |
| Insider threat | Audit logging, role separation, Shamir |

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
