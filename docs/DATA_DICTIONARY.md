# Data Dictionary

This document describes all SQLAlchemy models in EDMS, including field types, constraints, relationships, and enum values.

## Enums

### DocumentStatus

Tracks the processing state of a document.

| Value | Description |
|-------|-------------|
| `uploaded` | File received, not yet processed |
| `processing` | Background pipeline is running |
| `processed` | Pipeline completed successfully |
| `failed` | Pipeline encountered an error |

### WorkflowAction

Actions that can be performed in the document workflow.

| Value | Allowed Roles | Description |
|-------|---------------|-------------|
| `submit_review` | editor, admin, annotator | Submit document for review |
| `approve` | approver, admin | Approve the document |
| `reject` | reviewer, admin | Reject the document |
| `request_changes` | reviewer, admin | Request changes from author |
| `sign_off` | approver, admin | Final sign-off on document |

### DocumentLifecycleState

States in the document lifecycle state machine.

| Value | Description |
|-------|-------------|
| `draft` | Initial state, document is being prepared |
| `in_review` | Document is under review |
| `approved` | Document has been approved |
| `up_to_date` | Document is current and active |
| `needs_re_review` | Review interval has passed, re-review needed |
| `expired` | Document has expired |

### LifecycleType

Classification of document lifecycle behavior.

| Value | Description |
|-------|-------------|
| `permanent` | Document never expires |
| `expiring` | Document has a hard expiration date |
| `recurring` | Document requires periodic re-review |

### RoleName (Legacy Enum)

Maintained for backward compatibility.

| Value |
|-------|
| `admin` |
| `reviewer` |
| `editor` |
| `annotator` |
| `approver` |

---

## Document Management Models

### Document

**Table:** `documents`

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | Integer | PK, indexed | Auto-increment primary key |
| `group_id` | Integer | FK -> groups.id, NOT NULL, CASCADE | Parent group/folder |
| `original_filename` | String(500) | NOT NULL | Original uploaded filename |
| `storage_path` | String(1000) | NOT NULL | Path to stored file on disk |
| `encrypted_pdf_path` | String(1000) | nullable | Path to encrypted PDF copy |
| `markdown_path` | String(1000) | nullable | Path to converted markdown |
| `file_type` | String(100) | NOT NULL | MIME type of the file |
| `file_size` | Integer | NOT NULL | File size in bytes |
| `status` | Enum(DocumentStatus) | NOT NULL, default=uploaded | Processing status |
| `summary` | String(5000) | nullable | LLM-generated summary |
| `keywords` | JSON | nullable | LLM-extracted keywords |
| `created_at` | DateTime | NOT NULL, server_default=now() | Creation timestamp |
| `updated_at` | DateTime | NOT NULL, server_default=now(), onupdate=now() | Last update |

**Relationships:**
- `group` -> Group (many-to-one)

### Group

**Table:** `groups`

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | Integer | PK, indexed | Auto-increment primary key |
| `name` | String(255) | NOT NULL | Group/folder name |
| `description` | String(1000) | nullable | Description text |
| `parent_id` | Integer | FK -> groups.id, nullable | Parent group for hierarchy |
| `created_at` | DateTime | NOT NULL, server_default=now() | Creation timestamp |
| `updated_at` | DateTime | NOT NULL, server_default=now(), onupdate=now() | Last update |

**Relationships:**
- `parent` -> Group (self-referential, many-to-one)
- `children` -> list[Group] (one-to-many)
- `documents` -> list[Document] (one-to-many, cascade delete)

### WorkflowEntry

**Table:** `workflow_entries`

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | Integer | PK, indexed | Auto-increment primary key |
| `document_id` | Integer | FK -> documents.id, NOT NULL, CASCADE | Target document |
| `user_id` | String(36) | FK -> users.id, NOT NULL, CASCADE | User who performed action |
| `action` | Enum(WorkflowAction) | NOT NULL | The workflow action taken |
| `comment` | Text | nullable | Optional comment |
| `created_at` | DateTime | server_default=now() | When the action was taken |

### Annotation

**Table:** `annotations`

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | Integer | PK, indexed | Auto-increment primary key |
| `document_id` | Integer | FK -> documents.id, NOT NULL, CASCADE | Target document |
| `user_id` | String(36) | FK -> users.id, NOT NULL, CASCADE | Annotation author |
| `text` | Text | NOT NULL | Annotation content |
| `start_offset` | Integer | nullable | Character start position |
| `end_offset` | Integer | nullable | Character end position |
| `created_at` | DateTime | server_default=now() | Creation timestamp |

---

## Lifecycle Models

### DocumentLifecycle

**Table:** `document_lifecycles`

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | Integer | PK, indexed | Auto-increment primary key |
| `document_id` | Integer | FK -> documents.id, UNIQUE, NOT NULL, CASCADE | One lifecycle per document |
| `lifecycle_type` | Enum(LifecycleType) | NOT NULL | permanent/expiring/recurring |
| `state` | Enum(DocumentLifecycleState) | NOT NULL, default=draft | Current state |
| `expires_at` | DateTime | nullable | Hard expiration date (for expiring type) |
| `review_interval_days` | Integer | nullable | Days between reviews (for recurring type) |
| `next_review_at` | DateTime | nullable | When next review is due |
| `last_reviewed_at` | DateTime | nullable | Last review timestamp |
| `last_approved_at` | DateTime | nullable | Last approval timestamp |
| `assigned_reviewer_id` | String(36) | FK -> users.id, nullable | Designated reviewer |
| `created_at` | DateTime | NOT NULL, server_default=now() | Creation timestamp |
| `updated_at` | DateTime | NOT NULL, server_default=now(), onupdate=now() | Last update |

### LifecycleTransition

**Table:** `lifecycle_transitions`

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | Integer | PK, indexed | Auto-increment primary key |
| `lifecycle_id` | Integer | FK -> document_lifecycles.id, NOT NULL, CASCADE | Parent lifecycle |
| `from_state` | Enum(DocumentLifecycleState) | NOT NULL | State before transition |
| `to_state` | Enum(DocumentLifecycleState) | NOT NULL | State after transition |
| `transitioned_by` | String(36) | FK -> users.id, NOT NULL | User who triggered transition |
| `comment` | Text | nullable | Transition comment |
| `created_at` | DateTime | server_default=now() | When transition occurred |

---

## User & RBAC Models

### User

**Table:** `users`

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | String(36) | PK, UUID default | UUID primary key |
| `username` | String(64) | UNIQUE, NOT NULL, indexed | Login username |
| `display_name` | String(128) | NOT NULL, default="" | Display name |
| `email` | String(256) | UNIQUE, indexed, nullable | Email address |
| `hashed_password` | String(256) | nullable | bcrypt password hash |
| `is_active` | Boolean | default=True | Account active flag |
| `is_ldap` | Boolean | default=False | LDAP-sourced account |
| `ldap_dn` | String(512) | nullable | LDAP distinguished name |
| `created_at` | DateTime | server_default=now() | Creation timestamp |
| `updated_at` | DateTime | server_default=now(), onupdate=now() | Last update |

**Relationships:**
- `user_roles` -> list[UserRole] (one-to-many, cascade delete)
- `folder_assignments` -> list[FolderAssignment] (one-to-many, cascade delete)
- `org_assignments` -> list[OrgUserAssignment] (one-to-many)
- `personal_grades` -> list[OrgUserGrade] (one-to-many)

**Properties:**
- `roles` -> list[Role] (computed from user_roles)
- `role_codes` -> list[str] (computed role code strings)
- `permissions` -> list[str] (computed "resource:action" strings)

### Role

**Table:** `roles`

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | String(36) | PK, UUID default | UUID primary key |
| `code` | String(64) | UNIQUE, NOT NULL | Role identifier code |
| `name` | String(128) | NOT NULL | Human-readable name |
| `description` | Text | nullable | Role description |
| `is_system` | Boolean | default=False | System role (cannot delete) |
| `is_active` | Boolean | default=True | Role active flag |
| `created_at` | DateTime | server_default=now() | Creation timestamp |

**Relationships:**
- `permissions` -> list[RolePermission] (one-to-many, cascade delete)
- `user_roles` -> list[UserRole] (one-to-many)

**System Roles (seeded at startup):**

| Code | Name | Description |
|------|------|-------------|
| admin | Administrator | Full system access |
| manager | Manager | Manage org structure and users |
| operator | Operator | Operate org assignments |
| viewer | Viewer | Read-only access |
| editor | Editor | Edit documents |
| reviewer | Reviewer | Review documents |
| annotator | Annotator | Annotate documents |
| approver | Approver | Approve workflows |

### Permission

**Table:** `permissions`

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | String(36) | PK, UUID default | UUID primary key |
| `resource` | String(64) | NOT NULL | Resource name (e.g., "documents") |
| `action` | String(32) | NOT NULL | Action name (e.g., "create") |
| `description` | Text | nullable | Permission description |

**Relationships:**
- `role_permissions` -> list[RolePermission] (one-to-many)

**Seeded Permissions:**

| Resource | Actions |
|----------|---------|
| users | create, read, update, delete |
| roles | create, read, update, delete |
| org_units | create, read, update, delete |
| org_positions | create, read, update, delete |
| org_grades | create, read, update, delete |
| org_assignments | create, read, update, delete |
| documents | create, read, update, delete |
| ldap | manage |
| settings | manage |
| security | manage |
| reports | read |
| audit | read |

### RolePermission

**Table:** `role_permissions`

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | String(36) | PK, UUID default | UUID primary key |
| `role_id` | String(36) | FK -> roles.id, NOT NULL, CASCADE | Parent role |
| `permission_id` | String(36) | FK -> permissions.id, NOT NULL, CASCADE | Assigned permission |

**Relationships:**
- `role` -> Role (many-to-one)
- `permission` -> Permission (many-to-one)

### UserRole

**Table:** `user_roles`

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | String(36) | PK, UUID default | UUID primary key |
| `user_id` | String(36) | FK -> users.id, NOT NULL, CASCADE | Target user |
| `role_id` | String(36) | FK -> roles.id, NOT NULL, CASCADE | Assigned role |
| `granted_by` | String(36) | FK -> users.id, nullable | Who granted the role |
| `granted_at` | DateTime | server_default=now() | When role was granted |
| `expires_at` | DateTime | nullable | Optional role expiration |

**Relationships:**
- `user` -> User (many-to-one)
- `role` -> Role (many-to-one)

### FolderAssignment

**Table:** `folder_assignments`

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | Integer | PK, indexed | Auto-increment primary key |
| `user_id` | String(36) | FK -> users.id, NOT NULL, CASCADE | Target user |
| `folder_path` | String(500) | NOT NULL | Folder path scope |
| `role_id` | String(36) | FK -> roles.id, NOT NULL | Role for this folder |
| `granted_at` | DateTime | server_default=now() | Assignment timestamp |

**Relationships:**
- `user` -> User (many-to-one)
- `role` -> Role (many-to-one)

---

## Organization Structure Models

### OrgUnitType

**Table:** `org_unit_types`

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | String(36) | PK, UUID default | UUID primary key |
| `code` | String(32) | UNIQUE, NOT NULL | Type code |
| `name` | String(128) | NOT NULL | Type name |
| `sort_order` | Integer | default=0 | Display order |
| `is_active` | Boolean | default=True | Active flag |

**Seeded Values:** CORP (Corporation, 0), DIV (Division, 1), DEPT (Department, 2), UNIT (Unit, 3), TEAM (Team, 4)

**Relationships:**
- `units` -> list[OrgUnit] (one-to-many)

### OrgUnit

**Table:** `org_units`

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | String(36) | PK, UUID default | UUID primary key |
| `code` | String(32) | UNIQUE, NOT NULL | Unit code |
| `name` | String(256) | NOT NULL | Full unit name |
| `short_name` | String(64) | nullable | Abbreviated name |
| `type_id` | String(36) | FK -> org_unit_types.id, nullable | Unit type classification |
| `parent_id` | String(36) | FK -> org_units.id, nullable | Parent unit (hierarchy) |
| `head_user_id` | String(36) | FK -> users.id, nullable | Unit head/manager |
| `description` | Text | nullable | Description |
| `sort_order` | Integer | default=0 | Display order |
| `is_active` | Boolean | default=True | Active flag |
| `created_at` | DateTime | server_default=now() | Creation timestamp |
| `updated_at` | DateTime | onupdate=now(), nullable | Last update |

**Relationships:**
- `unit_type` -> OrgUnitType (many-to-one)
- `parent` -> OrgUnit (self-referential, many-to-one)
- `head_user` -> User (many-to-one)
- `positions` -> list[OrgPosition] (one-to-many)
- `assignments` -> list[OrgUserAssignment] (one-to-many)

### OrgGrade

**Table:** `org_grades`

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | String(36) | PK, UUID default | UUID primary key |
| `grade_code` | String(16) | UNIQUE, NOT NULL | Grade code (G01-G15) |
| `grade_name` | String(128) | NOT NULL | Grade description |
| `grade_level` | Integer | NOT NULL | Numeric level (1-15) |
| `grade_category` | String(64) | nullable | Category (Staff/Supervisor/Manager/Director/Executive) |
| `description` | Text | nullable | Additional description |
| `min_salary` | Float | nullable | Minimum salary for grade |
| `max_salary` | Float | nullable | Maximum salary for grade |
| `is_active` | Boolean | default=True | Active flag |
| `created_at` | DateTime | server_default=now() | Creation timestamp |

**Seeded Values:** G01 (Intern, level 1) through G15 (C-Level/President, level 15)

**Relationships:**
- `positions` -> list[OrgPosition] (one-to-many)
- `user_grades` -> list[OrgUserGrade] (one-to-many)

### OrgPosition

**Table:** `org_positions`

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | String(36) | PK, UUID default | UUID primary key |
| `unit_id` | String(36) | FK -> org_units.id, NOT NULL | Parent unit |
| `position_code` | String(32) | NOT NULL | Position code |
| `position_name` | String(256) | NOT NULL | Position title |
| `grade_id` | String(36) | FK -> org_grades.id, nullable | Associated grade |
| `is_head` | Boolean | default=False | Head position flag |
| `max_occupants` | Integer | default=1 | Maximum people in position |
| `current_occupants` | Integer | default=0 | Current count |
| `description` | Text | nullable | Position description |
| `is_active` | Boolean | default=True | Active flag |
| `created_at` | DateTime | server_default=now() | Creation timestamp |

**Relationships:**
- `unit` -> OrgUnit (many-to-one)
- `grade` -> OrgGrade (many-to-one)
- `assignments` -> list[OrgUserAssignment] (one-to-many)

### OrgUserAssignment

**Table:** `org_user_assignments`

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | String(36) | PK, UUID default | UUID primary key |
| `user_id` | String(36) | FK -> users.id, NOT NULL | Assigned user |
| `position_id` | String(36) | FK -> org_positions.id, NOT NULL | Target position |
| `unit_id` | String(36) | FK -> org_units.id, NOT NULL | Target unit |
| `assignment_type` | String(32) | default="primary" | Assignment classification |
| `effective_from` | DateTime | server_default=now() | Start date |
| `effective_to` | DateTime | nullable | End date |
| `is_primary` | Boolean | default=True | Primary assignment flag |
| `is_active` | Boolean | default=True | Active flag |
| `notes` | Text | nullable | Assignment notes |
| `created_by` | String(36) | FK -> users.id, nullable | Who created assignment |
| `created_at` | DateTime | server_default=now() | Creation timestamp |

**Relationships:**
- `user` -> User (many-to-one)
- `position` -> OrgPosition (many-to-one)
- `unit` -> OrgUnit (many-to-one)

### OrgUserGrade

**Table:** `org_user_grades`

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | String(36) | PK, UUID default | UUID primary key |
| `user_id` | String(36) | FK -> users.id, NOT NULL | Target user |
| `grade_id` | String(36) | FK -> org_grades.id, NOT NULL | Assigned grade |
| `effective_from` | DateTime | server_default=now() | Grade start date |
| `effective_to` | DateTime | nullable | Grade end date |
| `is_current` | Boolean | default=True | Current grade flag |
| `reason` | Text | nullable | Reason for grade assignment |
| `approved_by` | String(36) | FK -> users.id, nullable | Approver |
| `created_at` | DateTime | server_default=now() | Creation timestamp |

**Relationships:**
- `user` -> User (many-to-one)
- `grade` -> OrgGrade (many-to-one)

### OrgChangeHistory

**Table:** `org_change_history`

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | String(36) | PK, UUID default | UUID primary key |
| `change_type` | String(32) | NOT NULL | Type of change |
| `target_type` | String(64) | NOT NULL | Entity type that changed |
| `target_id` | String(64) | nullable | ID of changed entity |
| `old_value` | Text | nullable | Previous value (JSON) |
| `new_value` | Text | nullable | New value (JSON) |
| `changed_by` | String(36) | FK -> users.id, nullable | User who made change |
| `changed_at` | DateTime | server_default=now() | Change timestamp |

**Relationships:**
- `changer` -> User (many-to-one)

---

## Security & Encryption Models

### EncryptionKey

**Table:** `encryption_keys`

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | String(36) | PK, UUID default | UUID primary key |
| `key_type` | String(16) | NOT NULL | "kek" or "dek" |
| `key_id_hex` | String(64) | UNIQUE, NOT NULL | SHA-256 hash identifier |
| `is_active` | Boolean | default=True, NOT NULL | Key active flag |
| `metadata_json` | JSON | nullable | Key metadata (threshold, num_shares) |
| `created_at` | DateTime | NOT NULL, server_default=now() | Creation timestamp |

### KeyShare

**Table:** `key_shares`

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | String(36) | PK, UUID default | UUID primary key |
| `key_id` | String(36) | FK -> encryption_keys.id, NOT NULL | Parent key |
| `share_index` | Integer | NOT NULL | Shamir share index |
| `share_holder` | String(255) | NOT NULL | Designated holder name |
| `is_distributed` | Boolean | default=False, NOT NULL | Share distributed flag |
| `created_at` | DateTime | NOT NULL, server_default=now() | Creation timestamp |

### SecurityAlert

**Table:** `security_alerts`

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | String(36) | PK, UUID default | UUID primary key |
| `alert_type` | String(64) | NOT NULL | Alert classification |
| `severity` | String(16) | NOT NULL, default="medium" | low/medium/high/critical |
| `message` | Text | NOT NULL | Alert description |
| `details_json` | JSON | nullable | Structured alert details |
| `source_path` | String(1024) | nullable | File path that triggered alert |
| `detected_at` | DateTime | NOT NULL, server_default=now() | Detection timestamp |
| `acknowledged` | Boolean | default=False, NOT NULL | Acknowledged flag |
| `acknowledged_by` | String(36) | nullable | User who acknowledged |
| `acknowledged_at` | DateTime | nullable | Acknowledgment timestamp |

### MonitoringConfig

**Table:** `monitoring_config`

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | String(36) | PK, UUID default | UUID primary key |
| `config_key` | String(128) | UNIQUE, NOT NULL | Configuration key |
| `config_value` | Text | NOT NULL | Configuration value |
| `updated_at` | DateTime | NOT NULL, server_default=now(), onupdate=now() | Last update |

---

## LDAP Models

### LdapConfig

**Table:** `ldap_configs`

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | String(36) | PK, UUID default | UUID primary key |
| `name` | String(128) | NOT NULL | Configuration name |
| `is_active` | Boolean | default=True | Active flag |
| `is_default` | Boolean | default=False | Default config flag |
| `server_url` | String(256) | NOT NULL | LDAP server URL |
| `server_port` | Integer | default=389 | Server port |
| `use_ssl` | Boolean | default=False | Use SSL |
| `use_tls` | Boolean | default=False | Use STARTTLS |
| `connect_timeout` | Integer | default=10 | Connection timeout (seconds) |
| `bind_dn` | String(512) | nullable | Bind distinguished name |
| `bind_password` | String(512) | nullable | Bind password |
| `base_dn` | String(512) | NOT NULL | Base search DN |
| `user_search_filter` | String(256) | default="(objectClass=person)" | User filter |
| `user_search_base` | String(512) | nullable | User search base |
| `group_search_filter` | String(256) | default="(objectClass=groupOfNames)" | Group filter |
| `group_search_base` | String(512) | nullable | Group search base |
| `attr_username` | String(64) | default="uid" | Username attribute |
| `attr_email` | String(64) | default="mail" | Email attribute |
| `attr_display_name` | String(64) | default="cn" | Display name attribute |
| `attr_first_name` | String(64) | default="givenName" | First name attribute |
| `attr_last_name` | String(64) | default="sn" | Last name attribute |
| `attr_department` | String(64) | default="departmentNumber" | Department attribute |
| `attr_title` | String(64) | default="title" | Title attribute |
| `attr_member_of` | String(64) | default="memberOf" | Group membership attribute |
| `sync_enabled` | Boolean | default=False | Auto-sync enabled |
| `sync_schedule` | String(64) | nullable | Sync cron schedule |
| `sync_create_users` | Boolean | default=True | Create new users on sync |
| `sync_update_users` | Boolean | default=True | Update existing users |
| `sync_disable_missing` | Boolean | default=False | Disable missing users |
| `default_role` | String(64) | default="viewer" | Default role for synced users |
| `created_at` | DateTime | server_default=now() | Creation timestamp |
| `updated_at` | DateTime | onupdate=now(), nullable | Last update |

**Relationships:**
- `group_role_mappings` -> list[LdapGroupRole] (one-to-many, cascade delete)
- `sync_logs` -> list[LdapSyncLog] (one-to-many, cascade delete)

### LdapGroupRole

**Table:** `ldap_group_roles`

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | String(36) | PK, UUID default | UUID primary key |
| `config_id` | String(36) | FK -> ldap_configs.id, NOT NULL, CASCADE | Parent config |
| `ldap_group_dn` | String(512) | NOT NULL | LDAP group DN |
| `role_code` | String(64) | NOT NULL | EDMS role to assign |
| `is_active` | Boolean | default=True | Mapping active flag |

**Relationships:**
- `config` -> LdapConfig (many-to-one)

### LdapSyncLog

**Table:** `ldap_sync_logs`

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | String(36) | PK, UUID default | UUID primary key |
| `config_id` | String(36) | FK -> ldap_configs.id, nullable | Source config |
| `started_at` | DateTime | server_default=now() | Sync start time |
| `finished_at` | DateTime | nullable | Sync end time |
| `status` | String(32) | default="running" | running/completed/failed |
| `users_found` | Integer | default=0 | Users found in LDAP |
| `users_created` | Integer | default=0 | Users created |
| `users_updated` | Integer | default=0 | Users updated |
| `users_disabled` | Integer | default=0 | Users disabled |
| `errors` | Integer | default=0 | Error count |
| `error_detail` | Text | nullable | Error details |

**Relationships:**
- `config` -> LdapConfig (many-to-one)

---

## Backup Models

### BackupJob

**Table:** `backup_jobs`

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | String(36) | PK, UUID default | UUID primary key |
| `job_type` | String(50) | NOT NULL, default="full" | full / incremental |
| `status` | String(50) | NOT NULL, default="pending" | pending/running/completed/failed |
| `started_at` | DateTime | nullable | Job start time |
| `finished_at` | DateTime | nullable | Job end time |
| `size_bytes` | Integer | nullable | Backup size |
| `files_count` | Integer | nullable | Number of files backed up |
| `target` | String(50) | NOT NULL, default="primary" | primary / dr |
| `error_message` | Text | nullable | Error details on failure |
| `created_at` | DateTime | NOT NULL, server_default=now() | Record creation timestamp |

### BackupSchedule

**Table:** `backup_schedules`

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | String(36) | PK, UUID default | UUID primary key |
| `cron_expression` | String(100) | NOT NULL, default="0 2 * * *" | Cron schedule |
| `is_active` | Boolean | default=True | Schedule active flag |
| `last_run` | DateTime | nullable | Last execution time |
| `next_run` | DateTime | nullable | Next scheduled time |
| `created_at` | DateTime | NOT NULL, server_default=now() | Creation timestamp |

### BackupConfig

**Table:** `backup_configs`

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | String(36) | PK, UUID default | UUID primary key |
| `config_key` | String(255) | UNIQUE, NOT NULL | Configuration key |
| `config_value` | Text | NOT NULL, default="" | Configuration value |
| `updated_at` | DateTime | NOT NULL, server_default=now(), onupdate=now() | Last update |

---

## Document Versioning Models

### DocumentVersion

**Table:** `document_versions`

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | String(36) | PK, UUID default | UUID primary key |
| `document_id` | Integer | FK -> documents.id, NOT NULL, CASCADE, indexed | Parent document |
| `version_number` | Integer | NOT NULL, UNIQUE(document_id, version_number) | Sequential version number |
| `storage_path` | String(1000) | NOT NULL | Path to version file on disk |
| `encrypted_path` | String(1000) | nullable | Path to encrypted version file |
| `file_size` | Integer | NOT NULL | File size in bytes |
| `file_type` | String(100) | NOT NULL | MIME type of the versioned file |
| `uploader_id` | String(36) | FK -> users.id, nullable | User who uploaded version |
| `changelog` | Text | nullable | Description of changes in this version |
| `wrapped_dek` | Text | nullable | KMS-wrapped DEK (hex) for version encryption |
| `created_at` | DateTime | NOT NULL, server_default=now() | Version creation timestamp |

**Relationships:**
- `document` -> Document (many-to-one)

**Constraints:**
- Unique constraint on (`document_id`, `version_number`)

---

## Audit Models

### DocumentAuditLog

**Table:** `document_audit_log`

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | String(36) | PK, UUID default | UUID primary key |
| `document_id` | Integer | FK -> documents.id (SET NULL on delete), indexed, nullable | Target document |
| `action` | String(64) | NOT NULL | Action type (upload, view, download, edit, approve, reject, version_create, revert, delete, share, annotate) |
| `actor_id` | String(36) | FK -> users.id, nullable | User who performed the action |
| `actor_username` | String(256) | nullable | Username snapshot at time of action |
| `ip_address` | String(45) | nullable | Client IP address |
| `user_agent` | String(512) | nullable | Client user agent string |
| `timestamp` | DateTime | server_default=now() | When the action occurred |
| `details_json` | JSON | nullable | Additional structured details about the action |

**Indexes:**
- Composite index on (`document_id`, `timestamp`)

**Design Notes:**
- Immutable append-only log; entries are never modified or deleted
- `document_id` uses SET NULL on delete so audit trail survives document deletion
- `actor_username` is denormalized for performance in audit report queries

---

## Chat Models

### ChatSession

**Table:** `chat_sessions`

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | String(36) | PK, UUID default | UUID primary key |
| `user_id` | String(36) | FK -> users.id, NOT NULL, CASCADE | Session owner |
| `title` | String(255) | NOT NULL | Session display title |
| `scope_type` | String(20) | NOT NULL, default="global" | Scope: global, document, or group |
| `scope_id` | Integer | nullable | ID of scoped document or group |
| `created_at` | DateTime | server_default=now() | Session creation timestamp |
| `updated_at` | DateTime | server_default=now(), onupdate=now(), nullable | Last activity |

**Relationships:**
- `messages` -> list[ChatMessage] (one-to-many, cascade delete, ordered by created_at)

### ChatMessage

**Table:** `chat_messages`

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | String(36) | PK, UUID default | UUID primary key |
| `session_id` | String(36) | FK -> chat_sessions.id, NOT NULL, CASCADE | Parent session |
| `role` | String(20) | NOT NULL | Message role: "user" or "assistant" |
| `content` | Text | NOT NULL | Message text content |
| `sources_json` | JSON | nullable | Source document references for assistant messages |
| `created_at` | DateTime | server_default=now() | Message timestamp |

**Relationships:**
- `session` -> ChatSession (many-to-one)

**Design Notes:**
- Sessions use windowed history (last 20 messages) for LLM context
- Scope allows chat sessions tied to specific documents or groups

---

## Notification Models

### Notification

**Table:** `notifications`

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | String(36) | PK, UUID default | UUID primary key |
| `user_id` | String(36) | nullable | Target user (NULL for broadcast notifications) |
| `notification_type` | String(64) | NOT NULL | Type: document_status, lifecycle_alert, ransomware_alert, backup_status |
| `title` | String(256) | NOT NULL | Notification title |
| `message` | Text | NOT NULL | Notification body text |
| `data_json` | JSON | nullable | Structured payload data |
| `is_read` | Boolean | NOT NULL, default=False | Read/unread tracking |
| `created_at` | DateTime | NOT NULL, server_default=now() | Creation timestamp |

---

## Relationship Models

### DocumentRelationship

**Table:** `document_relationships`

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | Integer | PK, indexed | Auto-increment primary key |
| `source_document_id` | Integer | FK -> documents.id, NOT NULL, CASCADE | Source document |
| `target_document_id` | Integer | FK -> documents.id, NOT NULL, CASCADE | Target document |
| `relationship_type` | Enum(RelationshipType) | NOT NULL | Type of relationship |
| `description` | Text | nullable | Optional description of the relationship |
| `created_by` | Integer | FK -> users.id (SET NULL on delete), nullable | User who created the relationship |
| `created_at` | DateTime | NOT NULL, server_default=now() | Creation timestamp |

**Constraints:**
- Unique constraint on (`source_document_id`, `target_document_id`, `relationship_type`)

### RelationshipType Enum

| Value | Description |
|-------|-------------|
| `parent` | Source is a parent of target |
| `child` | Source is a child of target |
| `related` | General relationship |
| `supersedes` | Source supersedes/replaces target |
| `references` | Source references target |

---

## Updated Document Model Fields

The Document model has been extended with:

| Field | Type | Description |
|-------|------|-------------|
| `current_version` | Integer | Current active version number (updated by versioning) |

**New Relationships on Document:**
- `versions` -> list[DocumentVersion] (one-to-many)

---

## Tag & Smart Folder Models

### Tag

**Table:** `tags`

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | Integer | PK, indexed | Auto-increment primary key |
| `name` | String(100) | UNIQUE, NOT NULL | Tag name |
| `color` | String(7) | nullable | Hex color code (e.g., "#ff5733") |
| `created_at` | DateTime | NOT NULL, server_default=now() | Creation timestamp |

### DocumentTag

**Table:** `document_tags`

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | Integer | PK, indexed | Auto-increment primary key |
| `document_id` | Integer | FK -> documents.id, CASCADE, NOT NULL | Target document |
| `tag_id` | Integer | FK -> tags.id, CASCADE, NOT NULL | Applied tag |
| `created_at` | DateTime | NOT NULL, server_default=now() | When tag was applied |

**Constraints:**
- Unique constraint on (`document_id`, `tag_id`)

### SmartFolder

**Table:** `smart_folders`

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | Integer | PK, indexed | Auto-increment primary key |
| `name` | String(255) | NOT NULL | Smart folder display name |
| `description` | Text | nullable | Description of the filter criteria |
| `query_json` | JSON | nullable | Dynamic query filter definition |
| `owner_id` | String(36) | FK -> users.id, CASCADE, NOT NULL | Owner user |
| `created_at` | DateTime | NOT NULL, server_default=now() | Creation timestamp |
| `updated_at` | DateTime | NOT NULL, server_default=now(), onupdate=now() | Last update |

---

## Document Template Model

### DocumentTemplate

**Table:** `document_templates`

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | Integer | PK, indexed | Auto-increment primary key |
| `name` | String(255) | NOT NULL | Template name |
| `description` | Text | nullable | Template description |
| `required_fields` | JSON | nullable | List of required metadata fields |
| `default_folder_id` | Integer | FK -> groups.id, nullable | Default upload folder |
| `default_lifecycle_type` | String(50) | nullable | Default lifecycle type to assign |
| `extraction_prompt` | Text | nullable | LLM prompt for form extraction |
| `created_at` | DateTime | NOT NULL, server_default=now() | Creation timestamp |
| `updated_at` | DateTime | NOT NULL, server_default=now(), onupdate=now() | Last update |

---

## Approval Chain Models

### ApprovalChain

**Table:** `approval_chains`

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | Integer | PK, indexed | Auto-increment primary key |
| `name` | String(255) | NOT NULL | Chain name |
| `folder_id` | Integer | FK -> groups.id (SET NULL), nullable | Associated folder |
| `template_id` | Integer | FK -> document_templates.id (SET NULL), nullable | Associated template |
| `is_active` | Boolean | default=True | Active flag |
| `created_at` | DateTime | server_default=now() | Creation timestamp |

### ApprovalStep

**Table:** `approval_steps`

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | Integer | PK, indexed | Auto-increment primary key |
| `chain_id` | Integer | FK -> approval_chains.id, CASCADE, NOT NULL | Parent chain |
| `step_order` | Integer | NOT NULL | Order within chain (1-based) |
| `approval_type` | Enum(ApprovalType) | NOT NULL | sequential or parallel |
| `role_code` | String(64) | nullable | Required role for approval |
| `user_id` | String(36) | FK -> users.id (SET NULL), nullable | Specific user required |
| `timeout_hours` | Integer | nullable | Hours before auto-escalation |
| `created_at` | DateTime | server_default=now() | Creation timestamp |

### ApprovalType Enum

| Value | Description |
|-------|-------------|
| `sequential` | Steps processed one at a time in order |
| `parallel` | All approvers at this step must approve |

### ApprovalRequest

**Table:** `approval_requests`

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | Integer | PK, indexed | Auto-increment primary key |
| `document_id` | Integer | FK -> documents.id, CASCADE, NOT NULL | Document being approved |
| `chain_id` | Integer | FK -> approval_chains.id, CASCADE, NOT NULL | Chain being executed |
| `status` | Enum(ApprovalStatus) | default=pending, NOT NULL | Overall status |
| `current_step_order` | Integer | default=1 | Current step being processed |
| `submitted_by` | String(36) | FK -> users.id, CASCADE, NOT NULL | User who submitted |
| `submitted_at` | DateTime | server_default=now() | Submission timestamp |
| `completed_at` | DateTime | nullable | Completion timestamp |

### ApprovalStatus Enum

| Value | Description |
|-------|-------------|
| `pending` | Awaiting decisions |
| `approved` | All steps passed |
| `rejected` | A step was rejected |

### ApprovalDecision

**Table:** `approval_decisions`

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | Integer | PK, indexed | Auto-increment primary key |
| `request_id` | Integer | FK -> approval_requests.id, CASCADE, NOT NULL | Parent request |
| `step_id` | Integer | FK -> approval_steps.id, CASCADE, NOT NULL | Step being decided |
| `user_id` | String(36) | FK -> users.id, CASCADE, NOT NULL | User who decided |
| `decision` | Enum(ApprovalDecisionValue) | NOT NULL | approved or rejected |
| `comment` | Text | nullable | Decision comment |
| `decided_at` | DateTime | server_default=now() | Decision timestamp |

---

## Comment Model

### Comment

**Table:** `comments`

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | Integer | PK, indexed | Auto-increment primary key |
| `document_id` | Integer | FK -> documents.id, CASCADE, NOT NULL | Target document |
| `user_id` | String(36) | FK -> users.id, CASCADE, NOT NULL | Comment author |
| `content` | Text | NOT NULL | Comment text (supports @mentions) |
| `parent_id` | Integer | FK -> comments.id, CASCADE, nullable | Parent comment for threading |
| `created_at` | DateTime | server_default=now() | Creation timestamp |
| `updated_at` | DateTime | nullable | Last edit timestamp |

---

## Document Lock Model

### DocumentLock

**Table:** `document_locks`

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | Integer | PK, indexed | Auto-increment primary key |
| `document_id` | Integer | FK -> documents.id, CASCADE, UNIQUE, NOT NULL | Locked document |
| `user_id` | String(36) | FK -> users.id, CASCADE, NOT NULL | User who holds lock |
| `locked_at` | DateTime | server_default=now() | When lock was acquired |
| `expires_at` | DateTime | NOT NULL | Lock expiration time |
| `reason` | Text | nullable | Reason for locking |

---

## Document Signature Model

### DocumentSignature

**Table:** `document_signatures`

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | Integer | PK, indexed | Auto-increment primary key |
| `document_id` | Integer | FK -> documents.id, CASCADE, NOT NULL | Signed document |
| `signer_id` | String(36) | FK -> users.id, CASCADE, NOT NULL | User who signed |
| `signature_hash` | String(64) | UNIQUE, indexed, NOT NULL | SHA-256 hash of document content |
| `qr_code_path` | String(1000) | nullable | Path to generated QR code image |
| `signed_at` | DateTime | server_default=now() | Signing timestamp |
| `certificate_data` | Text | nullable | X.509 certificate PEM data |
| `verification_url` | String(500) | nullable | URL for external verification |
| `is_valid` | Boolean | default=True | Signature validity flag |

---

## Delegation Model

### Delegation

**Table:** `delegations`

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | Integer | PK, indexed | Auto-increment primary key |
| `delegator_id` | String(36) | FK -> users.id, CASCADE, NOT NULL | User delegating authority |
| `delegate_id` | String(36) | FK -> users.id, CASCADE, NOT NULL | User receiving authority |
| `start_date` | DateTime | NOT NULL | Delegation start time |
| `end_date` | DateTime | NOT NULL | Delegation end time |
| `scope_type` | Enum(DelegationScopeType) | default=all, NOT NULL | all or folder |
| `scope_folder_id` | Integer | FK -> groups.id (SET NULL), nullable | Folder scope (if folder type) |
| `is_active` | Boolean | default=True | Active flag |
| `created_at` | DateTime | server_default=now() | Creation timestamp |

### DelegationScopeType Enum

| Value | Description |
|-------|-------------|
| `all` | Delegation covers all folders/documents |
| `folder` | Delegation limited to specific folder |

---

## SLA Models

### SLAPolicy

**Table:** `sla_policies`

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | Integer | PK, indexed | Auto-increment primary key |
| `folder_id` | Integer | FK -> groups.id (SET NULL), nullable | Folder this policy applies to |
| `template_id` | Integer | FK -> document_templates.id (SET NULL), nullable | Template this policy applies to |
| `action` | String(64) | default="approval", NOT NULL | Action being tracked (e.g., approval) |
| `max_duration_hours` | Integer | NOT NULL | Maximum allowed hours |
| `escalation_role` | String(64) | nullable | Role to notify on breach |
| `is_active` | Boolean | default=True | Policy active flag |
| `created_at` | DateTime | server_default=now() | Creation timestamp |

### DocumentSLA

**Table:** `document_slas`

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | Integer | PK, indexed | Auto-increment primary key |
| `document_id` | Integer | FK -> documents.id, CASCADE, NOT NULL | Tracked document |
| `policy_id` | Integer | FK -> sla_policies.id, CASCADE, NOT NULL | Governing policy |
| `started_at` | DateTime | NOT NULL | When SLA clock started |
| `deadline_at` | DateTime | NOT NULL | SLA deadline |
| `status` | Enum(SLAStatus) | default=on_time, NOT NULL | Current SLA status |
| `completed_at` | DateTime | nullable | When action was completed |
| `escalated` | Boolean | default=False | Whether escalation was triggered |

### SLAStatus Enum

| Value | Description |
|-------|-------------|
| `on_time` | Within acceptable time range |
| `at_risk` | Approaching deadline (< 25% remaining) |
| `breached` | Past deadline |
| `completed` | Action completed within deadline |

---

## Geo-Fence Model

### GeoFenceRule

**Table:** `geofence_rules`

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | Integer | PK, indexed | Auto-increment primary key |
| `scope` | String(32) | NOT NULL, default="global" | Rule scope: global, group, document |
| `scope_id` | Integer | nullable | ID of scoped resource |
| `allowed_ip_ranges` | JSON | nullable | List of allowed CIDR ranges |
| `denied_ip_ranges` | JSON | nullable | List of blocked CIDR ranges |
| `allowed_countries` | JSON | nullable | List of allowed ISO country codes |
| `denied_countries` | JSON | nullable | List of blocked ISO country codes |
| `action` | String(16) | NOT NULL, default="allow" | Default action: allow or deny |
| `enabled` | Boolean | default=True, NOT NULL | Rule enabled flag |
| `created_at` | DateTime | NOT NULL, server_default=now() | Creation timestamp |
| `updated_at` | DateTime | NOT NULL, server_default=now(), onupdate=now() | Last update |

---

## Watermark Model

### WatermarkConfig

**Table:** `watermark_configs`

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | Integer | PK, indexed | Auto-increment primary key |
| `group_id` | Integer | FK -> groups.id, nullable | Group this config applies to (null=global) |
| `text_template` | String(500) | NOT NULL, default pattern | Template with {user}, {timestamp}, {doc_id} |
| `opacity` | Float | default=0.3, NOT NULL | Watermark opacity (0.0-1.0) |
| `position` | String(32) | default="diagonal", NOT NULL | Position: diagonal, center, footer |
| `enabled` | Boolean | default=True, NOT NULL | Config enabled flag |
| `created_at` | DateTime | NOT NULL, server_default=now() | Creation timestamp |

---

## Access Request Model

### AccessRequest

**Table:** `access_requests`

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | Integer | PK, indexed | Auto-increment primary key |
| `requester_id` | String(36) | FK -> users.id, NOT NULL | User requesting access |
| `resource_type` | String(32) | NOT NULL | Type: "document" or "group" |
| `resource_id` | Integer | NOT NULL | ID of the resource |
| `reason` | Text | nullable | Reason for request |
| `status` | String(16) | NOT NULL, default="pending" | pending, approved, denied |
| `reviewed_by` | String(36) | FK -> users.id, nullable | Admin who reviewed |
| `reviewed_at` | DateTime | nullable | Review timestamp |
| `created_at` | DateTime | NOT NULL, server_default=now() | Creation timestamp |
| `updated_at` | DateTime | NOT NULL, server_default=now(), onupdate=now() | Last update |

---

## Session Recording Models

### UserSession

**Table:** `user_sessions`

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | String(36) | PK, UUID default | UUID primary key |
| `user_id` | String(36) | FK -> users.id, NOT NULL | Session owner |
| `started_at` | DateTime | NOT NULL, server_default=now() | Session start |
| `ended_at` | DateTime | nullable | Session end |
| `ip_address` | String(45) | nullable | Client IP address |
| `user_agent` | String(512) | nullable | Browser user agent |

**Relationships:**
- `documents` -> list[SessionDocument] (one-to-many, selectin loading)

### SessionDocument

**Table:** `session_documents`

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | Integer | PK, indexed | Auto-increment primary key |
| `session_id` | String(36) | FK -> user_sessions.id, NOT NULL | Parent session |
| `document_id` | Integer | FK -> documents.id, NOT NULL | Accessed document |
| `action` | String(16) | NOT NULL | Action: view, download, edit |
| `accessed_at` | DateTime | NOT NULL, server_default=now() | Access timestamp |

**Relationships:**
- `session` -> UserSession (many-to-one)

---

## Canvas Models

### Canvas

**Table:** `canvases`

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | Integer | PK, indexed | Auto-increment primary key |
| `name` | String(255) | NOT NULL | Canvas name |
| `owner_id` | String | FK -> users.id, CASCADE, NOT NULL | Canvas owner |
| `created_at` | DateTime | NOT NULL, server_default=now() | Creation timestamp |

**Relationships:**
- `items` -> list[CanvasItem] (one-to-many, cascade delete)
- `connections` -> list[CanvasConnection] (one-to-many, cascade delete)

### CanvasItem

**Table:** `canvas_items`

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | Integer | PK, indexed | Auto-increment primary key |
| `canvas_id` | Integer | FK -> canvases.id, CASCADE, NOT NULL | Parent canvas |
| `document_id` | Integer | FK -> documents.id, nullable | Linked document (optional) |
| `note_text` | Text | nullable | Text content for note items |
| `x_position` | Float | NOT NULL, default=0.0 | X coordinate |
| `y_position` | Float | NOT NULL, default=0.0 | Y coordinate |
| `width` | Float | NOT NULL, default=200.0 | Item width |
| `height` | Float | NOT NULL, default=100.0 | Item height |
| `color` | String(50) | nullable | Optional color (hex) |

**Relationships:**
- `canvas` -> Canvas (many-to-one)

### CanvasConnection

**Table:** `canvas_connections`

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | Integer | PK, indexed | Auto-increment primary key |
| `canvas_id` | Integer | FK -> canvases.id, CASCADE, NOT NULL | Parent canvas |
| `from_item_id` | Integer | FK -> canvas_items.id, CASCADE, NOT NULL | Source item |
| `to_item_id` | Integer | FK -> canvas_items.id, CASCADE, NOT NULL | Target item |
| `label` | String(255) | nullable | Edge label |

**Relationships:**
- `canvas` -> Canvas (many-to-one)

---

## Tenant Model

### Tenant

**Table:** `tenants`

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | Integer | PK, indexed | Auto-increment primary key |
| `name` | String(255) | NOT NULL | Tenant display name |
| `slug` | String(100) | UNIQUE, NOT NULL | URL-safe tenant identifier |
| `settings` | JSON | nullable | Per-tenant configuration |
| `is_active` | Boolean | default=True | Tenant active flag |
| `created_at` | DateTime | NOT NULL, server_default=now() | Creation timestamp |

---

## Scheduled Report Model

### ScheduledReport

**Table:** `scheduled_reports`

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | Integer | PK, indexed | Auto-increment primary key |
| `name` | String(255) | NOT NULL | Report name |
| `schedule` | String(100) | NOT NULL | Cron expression for scheduling |
| `report_type` | String(64) | NOT NULL | Type of report to generate |
| `recipients` | JSON | NOT NULL | List of email addresses |
| `filters` | JSON | nullable | Optional filter criteria |
| `is_active` | Boolean | default=True | Schedule active flag |
| `created_at` | DateTime | NOT NULL, server_default=now() | Creation timestamp |
| `updated_at` | DateTime | server_default=now(), onupdate=now(), nullable | Last update |

---

## Health Score Model

### HealthScoreRecord

**Table:** `health_score_records`

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | Integer | PK, indexed | Auto-increment primary key |
| `date` | Date | NOT NULL | Score date |
| `composite_score` | Float | NOT NULL | Overall 0-100 score |
| `orphan_score` | Float | NOT NULL | Orphan document component |
| `lifecycle_score` | Float | NOT NULL | Lifecycle health component |
| `backup_score` | Float | NOT NULL | Backup recency component |
| `security_score` | Float | NOT NULL | Security posture component |
| `storage_score` | Float | NOT NULL | Storage utilization component |
| `sla_score` | Float | NOT NULL | SLA compliance component |
| `created_at` | DateTime | NOT NULL, server_default=now() | Record timestamp |

---

## Webhook Model

### WebhookConfig

**Table:** `webhook_configs`

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | Integer | PK, indexed | Auto-increment primary key |
| `url` | String(1000) | NOT NULL | Destination URL |
| `secret` | String(256) | NOT NULL | HMAC signing secret |
| `events` | JSON | NOT NULL | List of event types to subscribe |
| `is_active` | Boolean | default=True | Webhook enabled flag |
| `headers` | JSON | nullable | Custom headers to include |
| `created_at` | DateTime | NOT NULL, server_default=now() | Creation timestamp |
| `updated_at` | DateTime | server_default=now(), onupdate=now(), nullable | Last update |
