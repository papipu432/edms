from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite+aiosqlite:///./edms.db"
    STORAGE_PATH: str = "storage"
    WIKI_PATH: str = "wiki"
    PDF_ENCRYPTION_PASSWORD: str = "changeme"
    OPENAI_API_KEY: str = ""
    CHUNK_SIZE: int = 1000
    CHROMA_DB_PATH: str = "./chroma_db"
    CHROMA_HOST: str = ""
    CHROMA_PORT: int = 8000
    CHROMA_AUTH_TOKEN: str = ""
    SECRET_KEY: str = "changeme-secret-key-for-jwt"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    ALGORITHM: str = "HS256"

    # LDAP settings
    LDAP_ENABLED: bool = False
    LDAP_SERVER: str = "ldap://localhost"
    LDAP_PORT: int = 389
    LDAP_BASE_DN: str = "dc=example,dc=com"
    LDAP_BIND_DN: str = ""
    LDAP_BIND_PASSWORD: str = ""

    # LLM settings
    LLM_PROVIDER: str = "openai"  # "openai" or "ollama"
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL_SUMMARIZE: str = ""
    OLLAMA_MODEL_KEYWORDS: str = ""
    OLLAMA_MODEL_EMBEDDINGS: str = ""
    OLLAMA_MODEL_CHAT: str = ""

    # Backup settings - MinIO Primary
    MINIO_PRIMARY_ENDPOINT: str = ""
    MINIO_PRIMARY_ACCESS_KEY: str = ""
    MINIO_PRIMARY_SECRET_KEY: str = ""
    MINIO_PRIMARY_BUCKET: str = "edms-backup"

    # Backup settings - MinIO DR
    MINIO_DR_ENDPOINT: str = ""
    MINIO_DR_ACCESS_KEY: str = ""
    MINIO_DR_SECRET_KEY: str = ""
    MINIO_DR_BUCKET: str = "edms-backup-dr"

    # Backup settings - Restic
    RESTIC_REPOSITORY: str = ""
    RESTIC_PASSWORD: str = ""
    BACKUP_SCHEDULE: str = "0 2 * * *"
    BACKUP_RETENTION_DAYS: int = 30

    # KMS settings
    KMS_PROVIDER: str = "local"  # "local", "vault", or "cosmian"
    KMS_LOCAL_PASSPHRASE: str = "changeme-kms-passphrase"
    KMS_VAULT_URL: str = ""
    KMS_VAULT_TOKEN: str = ""

    # Bootstrap admin
    BOOTSTRAP_ADMIN_USERNAME: str = "admin"
    BOOTSTRAP_ADMIN_PASSWORD: str = "admin"
    BOOTSTRAP_ADMIN_EMAIL: str = "admin@edms.local"

    # SMTP / Email notifications
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM_EMAIL: str = "edms@example.com"
    ALERT_DAYS_BEFORE_EXPIRY: int = 30
    ALERT_DAYS_BEFORE_REVIEW: int = 14

    # Registration control
    ALLOW_REGISTRATION: bool = True

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
