from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite+aiosqlite:///./edms.db"
    STORAGE_PATH: str = "storage"
    WIKI_PATH: str = "wiki"
    PDF_ENCRYPTION_PASSWORD: str = "changeme"
    OPENAI_API_KEY: str = ""
    CHUNK_SIZE: int = 1000
    CHROMA_DB_PATH: str = "./chroma_db"
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

    # Bootstrap admin
    BOOTSTRAP_ADMIN_USERNAME: str = "admin"
    BOOTSTRAP_ADMIN_PASSWORD: str = "admin"
    BOOTSTRAP_ADMIN_EMAIL: str = "admin@edms.local"

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
