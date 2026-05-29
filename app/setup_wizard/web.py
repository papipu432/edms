"""Web-based setup wizard for EDMS.

Provides a FastAPI router that serves the setup wizard HTML page
for first-time configuration via the browser.
"""

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.setup_wizard.core import (
    configure_chromadb,
    configure_llm,
    configure_minio,
    configure_security,
    configure_smtp,
    configure_storage,
    generate_env_file,
    generate_kek_with_shares,
    is_first_launch,
)

router = APIRouter(tags=["setup"])
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


@router.get("/setup")
async def setup_wizard_page(request: Request):
    """Serve the setup wizard HTML page."""
    if not is_first_launch():
        return RedirectResponse(url="/login")
    return templates.TemplateResponse(request, "setup_wizard.html")


@router.post("/api/setup/configure")
async def configure_system(request: Request):
    """Handle the setup wizard form submission.

    Accepts a JSON body with all configuration values,
    generates the .env file, creates storage directories,
    and returns KEK shares for display.
    """
    if not is_first_launch():
        return JSONResponse(
            status_code=400,
            content={"detail": "System is already configured"},
        )

    data = await request.json()

    config: dict[str, str] = {}

    # Database
    config["DATABASE_URL"] = data.get(
        "database_url", "sqlite+aiosqlite:///./edms.db"
    )

    # Admin
    config["BOOTSTRAP_ADMIN_USERNAME"] = data.get("admin_username", "admin")
    config["BOOTSTRAP_ADMIN_PASSWORD"] = data.get("admin_password", "admin")
    config["BOOTSTRAP_ADMIN_EMAIL"] = data.get("admin_email", "admin@edms.local")

    # Security
    security_config = configure_security(
        encryption_password=data.get("encryption_password"),
        jwt_secret=data.get("jwt_secret"),
    )
    config.update(security_config)

    # LLM
    llm_config = configure_llm(
        provider=data.get("llm_provider", "openai"),
        api_key_or_url=data.get("llm_api_key", ""),
        models=data.get("llm_models"),
    )
    config.update(llm_config)

    # ChromaDB
    chroma_config = configure_chromadb(data.get("chromadb_path", "./chroma_db"))
    config.update(chroma_config)

    # MinIO (optional)
    if data.get("minio_endpoint"):
        minio_config = configure_minio(
            endpoint=data["minio_endpoint"],
            access_key=data.get("minio_access_key", ""),
            secret_key=data.get("minio_secret_key", ""),
            bucket=data.get("minio_bucket", "edms-backup"),
        )
        config.update(minio_config)

    # SMTP (optional)
    if data.get("smtp_host"):
        smtp_config = configure_smtp(
            host=data["smtp_host"],
            port=int(data.get("smtp_port", 587)),
            user=data.get("smtp_user", ""),
            password=data.get("smtp_password", ""),
            from_email=data.get("smtp_from_email", "edms@example.com"),
        )
        config.update(smtp_config)

    # Storage
    config["STORAGE_PATH"] = "storage"
    config["WIKI_PATH"] = "wiki"
    config["CHROMA_DB_PATH"] = config.get("CHROMA_DB_PATH", "./chroma_db")
    config["KMS_PROVIDER"] = "local"

    # Create directories
    storage_path = data.get("storage_base_path", ".")
    configure_storage(base_path=storage_path)

    # Generate .env file
    env_path = Path(data.get("env_path", ".env"))
    generate_env_file(config, env_path)

    # Generate KEK shares
    threshold = int(data.get("kek_threshold", 2))
    num_shares = int(data.get("kek_num_shares", 3))
    kek_result = generate_kek_with_shares(threshold=threshold, num_shares=num_shares)

    return JSONResponse(content={
        "status": "success",
        "message": "System configured successfully",
        "kek_shares": kek_result,
    })


@router.get("/api/setup/status")
async def setup_status():
    """Check if the system needs initial setup."""
    return JSONResponse(content={
        "needs_setup": is_first_launch(),
    })
