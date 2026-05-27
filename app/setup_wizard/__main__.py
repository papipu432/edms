"""CLI entry point for the EDMS setup wizard.

Usage:
    python -m app.setup_wizard             # Interactive mode
    python -m app.setup_wizard --help      # Show help
    python -m app.setup_wizard --non-interactive  # Use env vars for automation
"""

import argparse
import os
from pathlib import Path

from app.setup_wizard.core import (
    build_default_config,
    configure_chromadb,
    configure_llm,
    configure_minio,
    configure_security,
    configure_smtp,
    configure_storage,
    generate_env_file,
    generate_kek_with_shares,
)


def _print_banner() -> None:
    """Print the setup wizard banner."""
    print("\n" + "=" * 60)
    print("  EDMS - First-Time Setup Wizard")
    print("=" * 60 + "\n")


def _prompt(label: str, default: str = "", secret: bool = False) -> str:
    """Prompt user for input with optional default value."""
    if default:
        prompt_text = f"  {label} [{default}]: "
    else:
        prompt_text = f"  {label}: "

    if secret:
        import getpass
        value = getpass.getpass(prompt_text)
    else:
        value = input(prompt_text)

    return value.strip() or default


def _prompt_yes_no(label: str, default: bool = True) -> bool:
    """Prompt for a yes/no answer."""
    yn = "Y/n" if default else "y/N"
    value = input(f"  {label} [{yn}]: ").strip().lower()
    if not value:
        return default
    return value in ("y", "yes")


def _run_interactive(env_path: Path) -> None:
    """Run the interactive setup wizard."""
    _print_banner()
    print("This wizard will help you configure EDMS for first use.\n")

    config: dict[str, str] = {}

    # Step 1: Database
    print("\n--- Step 1: Database Configuration ---\n")
    db_url = _prompt(
        "Database URL",
        default="sqlite+aiosqlite:///./edms.db",
    )
    config["DATABASE_URL"] = db_url

    # Step 2: Admin user
    print("\n--- Step 2: Admin User ---\n")
    admin_username = _prompt("Admin username", default="admin")
    admin_password = _prompt("Admin password", default="admin", secret=True)
    admin_email = _prompt("Admin email", default="admin@edms.local")
    config["BOOTSTRAP_ADMIN_USERNAME"] = admin_username
    config["BOOTSTRAP_ADMIN_PASSWORD"] = admin_password
    config["BOOTSTRAP_ADMIN_EMAIL"] = admin_email

    # Step 3: Security
    print("\n--- Step 3: Security Configuration ---\n")
    print("  Generating secure random keys...")
    security_config = configure_security()
    config.update(security_config)
    print("  Done. JWT secret and encryption password generated.\n")

    # Step 4: KEK and Shamir shares
    print("\n--- Step 4: Key Encryption Key (KEK) Generation ---\n")
    threshold = int(_prompt("Shamir threshold (min shares to recover)", default="2"))
    num_shares = int(_prompt("Number of shares to generate", default="3"))

    kek_result = generate_kek_with_shares(threshold=threshold, num_shares=num_shares)

    print("\n" + "!" * 60)
    print("  WARNING: The following shares are shown ONLY ONCE.")
    print("  Write them down and distribute to trusted key holders.")
    print("  These shares are NEVER stored by the system.")
    print("!" * 60 + "\n")
    print(f"  Threshold: {kek_result['threshold']} of {kek_result['num_shares']}\n")

    for share in kek_result["shares"]:
        print(f"  Share {share['index']}: {share['hex']}")

    print("\n" + "!" * 60 + "\n")

    # Step 5: Storage
    print("\n--- Step 5: Storage Configuration ---\n")
    storage_path = _prompt("Storage base path", default=".")
    dirs = configure_storage(base_path=storage_path)
    config["STORAGE_PATH"] = "storage"
    config["WIKI_PATH"] = "wiki"
    config["CHROMA_DB_PATH"] = "./chroma_db"
    print(f"  Created {len(dirs)} directories.\n")

    # Step 6: MinIO (optional)
    print("\n--- Step 6: MinIO Backup Storage (Optional) ---\n")
    if _prompt_yes_no("Configure MinIO?", default=False):
        endpoint = _prompt("MinIO endpoint", default="localhost:9000")
        access_key = _prompt("Access key")
        secret_key = _prompt("Secret key", secret=True)
        bucket = _prompt("Bucket name", default="edms-backup")
        minio_config = configure_minio(endpoint, access_key, secret_key, bucket)
        config.update(minio_config)

    # Step 7: LLM
    print("\n--- Step 7: LLM Provider ---\n")
    provider = _prompt("LLM provider (openai/ollama)", default="openai")
    if provider == "openai":
        api_key = _prompt("OpenAI API key", secret=True)
        llm_config = configure_llm(provider, api_key)
    else:
        ollama_url = _prompt("Ollama base URL", default="http://localhost:11434")
        llm_config = configure_llm(provider, ollama_url)
    config.update(llm_config)

    # Step 8: ChromaDB
    print("\n--- Step 8: ChromaDB Vector Store ---\n")
    chroma_path = _prompt("ChromaDB path or URL", default="./chroma_db")
    chroma_config = configure_chromadb(chroma_path)
    config.update(chroma_config)

    # Step 9: SMTP (optional)
    print("\n--- Step 9: SMTP Email (Optional) ---\n")
    if _prompt_yes_no("Configure SMTP?", default=False):
        smtp_host = _prompt("SMTP host")
        smtp_port = int(_prompt("SMTP port", default="587"))
        smtp_user = _prompt("SMTP user")
        smtp_pass = _prompt("SMTP password", secret=True)
        smtp_from = _prompt("From email", default="edms@example.com")
        smtp_config = configure_smtp(smtp_host, smtp_port, smtp_user, smtp_pass, smtp_from)
        config.update(smtp_config)

    # Step 10: KMS
    config["KMS_PROVIDER"] = "local"

    # Write .env file
    print("\n--- Writing Configuration ---\n")
    generate_env_file(config, env_path)
    print(f"  Configuration written to: {env_path}\n")

    print("\n" + "=" * 60)
    print("  Setup complete! You can now start EDMS.")
    print("  Run: uv run uvicorn app.main:app --reload")
    print("=" * 60 + "\n")


def _run_non_interactive(env_path: Path) -> None:
    """Run setup using environment variables (for CI/automation)."""
    _print_banner()
    print("Running in non-interactive mode (using environment variables)...\n")

    # Build config from env vars with defaults
    config = build_default_config(
        db_url=os.environ.get("EDMS_DB_URL", "sqlite+aiosqlite:///./edms.db"),
        admin_username=os.environ.get("EDMS_ADMIN_USERNAME", "admin"),
        admin_password=os.environ.get("EDMS_ADMIN_PASSWORD", "admin"),
        admin_email=os.environ.get("EDMS_ADMIN_EMAIL", "admin@edms.local"),
    )

    # Override with any EDMS_ prefixed env vars
    llm_provider = os.environ.get("EDMS_LLM_PROVIDER", "openai")
    config["LLM_PROVIDER"] = llm_provider
    if llm_provider == "openai":
        config["OPENAI_API_KEY"] = os.environ.get("EDMS_OPENAI_API_KEY", "")

    # Create storage directories
    storage_path = os.environ.get("EDMS_STORAGE_PATH", ".")
    configure_storage(base_path=storage_path)

    # Generate KEK shares
    threshold = int(os.environ.get("EDMS_KEK_THRESHOLD", "2"))
    num_shares = int(os.environ.get("EDMS_KEK_NUM_SHARES", "3"))
    kek_result = generate_kek_with_shares(threshold=threshold, num_shares=num_shares)

    print("\n  WARNING: Shamir shares (shown once, never stored):\n")
    for share in kek_result["shares"]:
        print(f"  Share {share['index']}: {share['hex']}")
    print()

    # Write .env
    generate_env_file(config, env_path)
    print(f"  Configuration written to: {env_path}\n")
    print("  Setup complete!\n")


def main() -> None:
    """Main entry point for the setup wizard CLI."""
    parser = argparse.ArgumentParser(
        prog="python -m app.setup_wizard",
        description="EDMS First-Time Setup Wizard - Configure database, storage, "
        "encryption keys, and service connections.",
    )
    parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="Run without prompts, using environment variables for configuration. "
        "Env vars: EDMS_DB_URL, EDMS_ADMIN_USERNAME, EDMS_ADMIN_PASSWORD, "
        "EDMS_ADMIN_EMAIL, EDMS_LLM_PROVIDER, EDMS_OPENAI_API_KEY, "
        "EDMS_STORAGE_PATH, EDMS_KEK_THRESHOLD, EDMS_KEK_NUM_SHARES.",
    )
    parser.add_argument(
        "--env-file",
        type=str,
        default=".env",
        help="Path to write the .env file (default: .env)",
    )

    args = parser.parse_args()
    env_path = Path(args.env_file)

    if args.non_interactive:
        _run_non_interactive(env_path)
    else:
        _run_interactive(env_path)


if __name__ == "__main__":
    main()
