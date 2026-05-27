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

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
