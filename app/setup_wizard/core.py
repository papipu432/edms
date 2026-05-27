"""Core setup wizard logic shared between CLI and web interfaces.

Functions here handle environment configuration, database setup,
admin creation, KEK generation with Shamir shares, storage directory
creation, and service configuration.
"""

import secrets
from pathlib import Path


def generate_env_file(
    config: dict[str, str],
    env_path: Path | None = None,
) -> Path:
    """Generate a .env file from configuration dictionary.

    Args:
        config: Key-value pairs for environment variables.
        env_path: Path to write the .env file. Defaults to .env in cwd.

    Returns:
        The path to the generated .env file.
    """
    if env_path is None:
        env_path = Path(".env")

    lines = []
    for key, value in config.items():
        # Escape any quotes in value
        escaped = str(value).replace('"', '\\"')
        lines.append(f'{key}="{escaped}"')

    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return env_path


async def test_db_connection(url: str) -> bool:
    """Test database connectivity.

    Args:
        url: SQLAlchemy database URL.

    Returns:
        True if connection succeeds, False otherwise.
    """
    try:
        from sqlalchemy.ext.asyncio import create_async_engine

        engine = create_async_engine(url, echo=False)
        async with engine.connect() as conn:
            await conn.execute(
                __import__("sqlalchemy").text("SELECT 1")
            )
        await engine.dispose()
        return True
    except Exception:
        return False


async def run_migrations(url: str) -> bool:
    """Create database schema using SQLAlchemy metadata.

    Args:
        url: SQLAlchemy database URL.

    Returns:
        True if migrations ran successfully.
    """
    try:
        from sqlalchemy.ext.asyncio import create_async_engine

        from app.models.group import Base

        engine = create_async_engine(url, echo=False)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await engine.dispose()
        return True
    except Exception:
        return False


async def create_admin_user(
    username: str,
    password: str,
    email: str,
    db_url: str,
) -> bool:
    """Create the bootstrap admin user in the database.

    Args:
        username: Admin username.
        password: Admin password (will be hashed).
        email: Admin email.
        db_url: SQLAlchemy database URL.

    Returns:
        True if admin was created successfully.
    """
    try:
        from sqlalchemy import select
        from sqlalchemy.ext.asyncio import (
            AsyncSession,
            async_sessionmaker,
            create_async_engine,
        )

        from app.core.security import hash_password
        from app.models.user import Role, User, UserRole

        engine = create_async_engine(db_url, echo=False)
        session_factory = async_sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )

        async with session_factory() as session:
            # Check if user already exists
            result = await session.execute(
                select(User).where(User.username == username)
            )
            if result.scalar_one_or_none() is not None:
                await engine.dispose()
                return True  # Already exists

            admin_user = User(
                username=username,
                display_name="System Administrator",
                email=email,
                hashed_password=hash_password(password),
            )
            session.add(admin_user)
            await session.flush()

            # Assign admin role
            result = await session.execute(
                select(Role).where(Role.code == "admin")
            )
            admin_role = result.scalar_one_or_none()
            if admin_role:
                session.add(UserRole(user_id=admin_user.id, role_id=admin_role.id))

            await session.commit()

        await engine.dispose()
        return True
    except Exception:
        return False


def generate_kek_with_shares(
    threshold: int = 2,
    num_shares: int = 3,
) -> dict:
    """Generate a KEK and split it into Shamir shares.

    The assembled KEK is returned ONLY for immediate display to the admin.
    It must NEVER be stored in assembled form.

    Args:
        threshold: Minimum shares needed for reconstruction.
        num_shares: Total number of shares to generate.

    Returns:
        Dictionary with 'shares' (list of hex-encoded shares) and
        'threshold'. The raw KEK is NOT included in the return value.
    """
    from app.services.key_recovery import KeyRecoveryManager

    manager = KeyRecoveryManager(
        key_store_path=Path("/dev/null"),
        ceremony_required=True,
    )

    kek = manager.generate_kek()
    shares = manager.split_kek(kek, threshold=threshold, num_shares=num_shares)

    # Format shares for display
    share_list = []
    for idx, share_data in shares:
        share_list.append({
            "index": idx,
            "hex": share_data.hex(),
        })

    # Zero out the raw KEK from memory (best effort in Python)
    del kek

    return {
        "shares": share_list,
        "threshold": threshold,
        "num_shares": num_shares,
    }


def configure_storage(base_path: str | None = None) -> list[str]:
    """Create all required data directories for EDMS.

    Args:
        base_path: Base directory for storage. Defaults to current directory.

    Returns:
        List of created directory paths.
    """
    if base_path is None:
        base_path = "."

    base = Path(base_path)
    directories = [
        base / "data" / "raw",
        base / "data" / "md",
        base / "data" / "csv",
        base / "data" / "images",
        base / "data" / "vectors",
        base / "uploads",
        base / "storage",
        base / "wiki",
        base / "chroma_db",
    ]

    created = []
    for d in directories:
        d.mkdir(parents=True, exist_ok=True)
        created.append(str(d))

    return created


def configure_minio(
    endpoint: str,
    access_key: str,
    secret_key: str,
    bucket: str,
) -> dict[str, str]:
    """Validate MinIO configuration and return settings dict.

    Does not actually test the connection (service may not be available
    during setup). Returns the configuration for .env generation.

    Args:
        endpoint: MinIO server endpoint.
        access_key: Access key ID.
        secret_key: Secret access key.
        bucket: Bucket name.

    Returns:
        Dictionary of MinIO settings for .env file.
    """
    return {
        "MINIO_PRIMARY_ENDPOINT": endpoint,
        "MINIO_PRIMARY_ACCESS_KEY": access_key,
        "MINIO_PRIMARY_SECRET_KEY": secret_key,
        "MINIO_PRIMARY_BUCKET": bucket,
    }


def configure_llm(
    provider: str,
    api_key_or_url: str = "",
    models: dict[str, str] | None = None,
) -> dict[str, str]:
    """Configure LLM provider settings.

    Args:
        provider: LLM provider ('openai' or 'ollama').
        api_key_or_url: API key for OpenAI or base URL for Ollama.
        models: Optional dict of model names by purpose.

    Returns:
        Dictionary of LLM settings for .env file.
    """
    config: dict[str, str] = {"LLM_PROVIDER": provider}

    if provider == "openai":
        config["OPENAI_API_KEY"] = api_key_or_url
    elif provider == "ollama":
        config["OLLAMA_BASE_URL"] = api_key_or_url or "http://localhost:11434"
        if models:
            config["OLLAMA_MODEL_SUMMARIZE"] = models.get("summarize", "")
            config["OLLAMA_MODEL_KEYWORDS"] = models.get("keywords", "")
            config["OLLAMA_MODEL_EMBEDDINGS"] = models.get("embeddings", "")
            config["OLLAMA_MODEL_CHAT"] = models.get("chat", "")

    return config


def configure_chromadb(path_or_host: str = "") -> dict[str, str]:
    """Configure ChromaDB settings.

    Args:
        path_or_host: Local path or remote host for ChromaDB.

    Returns:
        Dictionary of ChromaDB settings for .env file.
    """
    config: dict[str, str] = {}

    if path_or_host.startswith("http"):
        # Remote ChromaDB
        config["CHROMA_HOST"] = path_or_host
    else:
        # Local file-based
        config["CHROMA_DB_PATH"] = path_or_host or "./chroma_db"

    return config


def configure_smtp(
    host: str,
    port: int,
    user: str,
    password: str,
    from_email: str,
) -> dict[str, str]:
    """Configure SMTP settings for email notifications.

    Args:
        host: SMTP server hostname.
        port: SMTP server port.
        user: SMTP username.
        password: SMTP password.
        from_email: Sender email address.

    Returns:
        Dictionary of SMTP settings for .env file.
    """
    return {
        "SMTP_HOST": host,
        "SMTP_PORT": str(port),
        "SMTP_USER": user,
        "SMTP_PASSWORD": password,
        "SMTP_FROM_EMAIL": from_email,
    }


def configure_security(
    encryption_password: str | None = None,
    jwt_secret: str | None = None,
) -> dict[str, str]:
    """Configure security parameters.

    Generates secure random values if not provided.

    Args:
        encryption_password: PDF encryption password.
        jwt_secret: JWT signing secret.

    Returns:
        Dictionary of security settings for .env file.
    """
    return {
        "PDF_ENCRYPTION_PASSWORD": encryption_password or secrets.token_urlsafe(32),
        "SECRET_KEY": jwt_secret or secrets.token_urlsafe(32),
        "KMS_LOCAL_PASSPHRASE": secrets.token_urlsafe(32),
    }


def is_first_launch(env_path: Path | None = None) -> bool:
    """Detect if this is a first-launch condition.

    First launch is detected when:
    - No .env file exists, OR
    - The .env file has default/placeholder values

    Args:
        env_path: Path to .env file. Defaults to .env in cwd.

    Returns:
        True if setup wizard should be shown.
    """
    if env_path is None:
        env_path = Path(".env")

    if not env_path.exists():
        return True

    # Check if .env has only default values
    content = env_path.read_text(encoding="utf-8")
    if not content.strip():
        return True

    # Check for known default/placeholder values indicating unconfigured state
    default_indicators = [
        "changeme-secret-key-for-jwt",
        'SECRET_KEY="changeme',
    ]
    for indicator in default_indicators:
        if indicator in content:
            return True

    return False


def build_default_config(
    db_url: str = "sqlite+aiosqlite:///./edms.db",
    admin_username: str = "admin",
    admin_password: str = "admin",
    admin_email: str = "admin@edms.local",
) -> dict[str, str]:
    """Build a default configuration dictionary.

    Args:
        db_url: Database URL.
        admin_username: Bootstrap admin username.
        admin_password: Bootstrap admin password.
        admin_email: Bootstrap admin email.

    Returns:
        Complete configuration dictionary suitable for generate_env_file().
    """
    security = configure_security()

    config = {
        "DATABASE_URL": db_url,
        "STORAGE_PATH": "storage",
        "WIKI_PATH": "wiki",
        "CHROMA_DB_PATH": "./chroma_db",
        "BOOTSTRAP_ADMIN_USERNAME": admin_username,
        "BOOTSTRAP_ADMIN_PASSWORD": admin_password,
        "BOOTSTRAP_ADMIN_EMAIL": admin_email,
        "LLM_PROVIDER": "openai",
        "KMS_PROVIDER": "local",
    }
    config.update(security)

    return config
