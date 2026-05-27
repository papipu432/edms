"""Tests for the setup wizard core logic, CLI, and web interface."""

import os
from pathlib import Path
from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

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
    is_first_launch,
)


class TestGenerateEnvFile:
    """Tests for .env file generation."""

    def test_generates_env_file(self, tmp_path: Path):
        env_path = tmp_path / ".env"
        config = {
            "DATABASE_URL": "sqlite+aiosqlite:///./test.db",
            "SECRET_KEY": "test-secret",
            "STORAGE_PATH": "storage",
        }

        result = generate_env_file(config, env_path)

        assert result == env_path
        assert env_path.exists()
        content = env_path.read_text()
        assert 'DATABASE_URL="sqlite+aiosqlite:///./test.db"' in content
        assert 'SECRET_KEY="test-secret"' in content
        assert 'STORAGE_PATH="storage"' in content

    def test_generates_all_keys(self, tmp_path: Path):
        env_path = tmp_path / ".env"
        config = {
            "KEY1": "value1",
            "KEY2": "value2",
            "KEY3": "value3",
        }

        generate_env_file(config, env_path)
        content = env_path.read_text()

        for key, value in config.items():
            assert f'{key}="{value}"' in content

    def test_escapes_quotes_in_values(self, tmp_path: Path):
        env_path = tmp_path / ".env"
        config = {"KEY": 'value with "quotes"'}

        generate_env_file(config, env_path)
        content = env_path.read_text()

        assert 'KEY="value with \\"quotes\\""' in content

    def test_overwrites_existing_file(self, tmp_path: Path):
        env_path = tmp_path / ".env"
        env_path.write_text("OLD_KEY=old_value\n")

        generate_env_file({"NEW_KEY": "new_value"}, env_path)
        content = env_path.read_text()

        assert "OLD_KEY" not in content
        assert "NEW_KEY" in content


class TestConfigureStorage:
    """Tests for storage directory creation."""

    def test_creates_all_directories(self, tmp_path: Path):
        dirs = configure_storage(base_path=str(tmp_path))

        assert len(dirs) > 0
        for d in dirs:
            assert Path(d).exists()
            assert Path(d).is_dir()

    def test_creates_expected_directories(self, tmp_path: Path):
        configure_storage(base_path=str(tmp_path))

        expected = [
            tmp_path / "data" / "raw",
            tmp_path / "data" / "md",
            tmp_path / "data" / "csv",
            tmp_path / "data" / "images",
            tmp_path / "data" / "vectors",
            tmp_path / "uploads",
            tmp_path / "storage",
            tmp_path / "wiki",
            tmp_path / "chroma_db",
        ]
        for d in expected:
            assert d.exists(), f"Expected directory {d} does not exist"

    def test_idempotent(self, tmp_path: Path):
        configure_storage(base_path=str(tmp_path))
        # Running again should not raise
        dirs = configure_storage(base_path=str(tmp_path))
        assert len(dirs) > 0


class TestGenerateKekWithShares:
    """Tests for KEK generation and Shamir splitting."""

    def test_returns_correct_structure(self):
        result = generate_kek_with_shares(threshold=2, num_shares=3)

        assert "shares" in result
        assert "threshold" in result
        assert "num_shares" in result
        assert result["threshold"] == 2
        assert result["num_shares"] == 3
        assert len(result["shares"]) == 3

    def test_shares_have_correct_format(self):
        result = generate_kek_with_shares(threshold=2, num_shares=3)

        for share in result["shares"]:
            assert "index" in share
            assert "hex" in share
            assert isinstance(share["index"], int)
            assert isinstance(share["hex"], str)
            # Each share should be a valid hex string of 32 bytes (64 hex chars)
            assert len(share["hex"]) == 64
            bytes.fromhex(share["hex"])  # Should not raise

    def test_shares_are_unique(self):
        result = generate_kek_with_shares(threshold=2, num_shares=5)

        hex_values = [s["hex"] for s in result["shares"]]
        assert len(set(hex_values)) == len(hex_values)

    def test_shares_can_reconstruct(self):
        """Verify that generated shares can reconstruct the KEK."""
        from app.services.key_recovery import ShamirSecretSharing

        result = generate_kek_with_shares(threshold=2, num_shares=3)
        shares = [
            (s["index"], bytes.fromhex(s["hex"]))
            for s in result["shares"][:2]  # Use threshold number
        ]

        # Reconstruction should not raise
        recovered = ShamirSecretSharing.reconstruct_secret(shares)
        assert len(recovered) == 32

    def test_different_thresholds(self):
        result = generate_kek_with_shares(threshold=3, num_shares=5)
        assert result["threshold"] == 3
        assert result["num_shares"] == 5
        assert len(result["shares"]) == 5

    def test_raw_kek_not_in_result(self):
        """Verify the assembled KEK is never returned."""
        result = generate_kek_with_shares(threshold=2, num_shares=3)

        # The result should NOT contain a 'kek' key
        assert "kek" not in result
        assert "raw_key" not in result


class TestFirstLaunchDetection:
    """Tests for first-launch detection logic."""

    def test_no_env_file(self, tmp_path: Path):
        env_path = tmp_path / ".env"
        assert is_first_launch(env_path) is True

    def test_empty_env_file(self, tmp_path: Path):
        env_path = tmp_path / ".env"
        env_path.write_text("")
        assert is_first_launch(env_path) is True

    def test_default_secret_key(self, tmp_path: Path):
        env_path = tmp_path / ".env"
        env_path.write_text('SECRET_KEY="changeme-secret-key-for-jwt"\n')
        assert is_first_launch(env_path) is True

    def test_configured_system(self, tmp_path: Path):
        env_path = tmp_path / ".env"
        env_path.write_text(
            'SECRET_KEY="a-real-secure-key-that-is-not-default"\n'
            'DATABASE_URL="sqlite+aiosqlite:///./edms.db"\n'
        )
        assert is_first_launch(env_path) is False


class TestConfigureSecurity:
    """Tests for security configuration."""

    def test_generates_random_values(self):
        result = configure_security()

        assert "PDF_ENCRYPTION_PASSWORD" in result
        assert "SECRET_KEY" in result
        assert "KMS_LOCAL_PASSPHRASE" in result
        # Should not be default values
        assert result["SECRET_KEY"] != "changeme-secret-key-for-jwt"
        assert result["PDF_ENCRYPTION_PASSWORD"] != "changeme"

    def test_uses_provided_values(self):
        result = configure_security(
            encryption_password="my-enc-pass",
            jwt_secret="my-jwt-secret",
        )

        assert result["PDF_ENCRYPTION_PASSWORD"] == "my-enc-pass"
        assert result["SECRET_KEY"] == "my-jwt-secret"

    def test_values_are_unique_each_call(self):
        r1 = configure_security()
        r2 = configure_security()
        assert r1["SECRET_KEY"] != r2["SECRET_KEY"]


class TestConfigureLLM:
    """Tests for LLM configuration."""

    def test_openai_provider(self):
        result = configure_llm("openai", "sk-test-key")
        assert result["LLM_PROVIDER"] == "openai"
        assert result["OPENAI_API_KEY"] == "sk-test-key"

    def test_ollama_provider(self):
        result = configure_llm("ollama", "http://localhost:11434")
        assert result["LLM_PROVIDER"] == "ollama"
        assert result["OLLAMA_BASE_URL"] == "http://localhost:11434"

    def test_ollama_with_models(self):
        models = {"summarize": "llama2", "chat": "mistral"}
        result = configure_llm("ollama", "http://localhost:11434", models=models)
        assert result["OLLAMA_MODEL_SUMMARIZE"] == "llama2"
        assert result["OLLAMA_MODEL_CHAT"] == "mistral"


class TestConfigureChromaDB:
    """Tests for ChromaDB configuration."""

    def test_local_path(self):
        result = configure_chromadb("./my_chroma")
        assert result["CHROMA_DB_PATH"] == "./my_chroma"

    def test_remote_host(self):
        result = configure_chromadb("http://chroma-server:8000")
        assert result["CHROMA_HOST"] == "http://chroma-server:8000"

    def test_default_path(self):
        result = configure_chromadb("")
        assert result["CHROMA_DB_PATH"] == "./chroma_db"


class TestConfigureMinio:
    """Tests for MinIO configuration."""

    def test_returns_all_settings(self):
        result = configure_minio("localhost:9000", "access", "secret", "mybucket")
        assert result["MINIO_PRIMARY_ENDPOINT"] == "localhost:9000"
        assert result["MINIO_PRIMARY_ACCESS_KEY"] == "access"
        assert result["MINIO_PRIMARY_SECRET_KEY"] == "secret"
        assert result["MINIO_PRIMARY_BUCKET"] == "mybucket"


class TestConfigureSMTP:
    """Tests for SMTP configuration."""

    def test_returns_all_settings(self):
        result = configure_smtp("smtp.test.com", 465, "user", "pass", "from@test.com")
        assert result["SMTP_HOST"] == "smtp.test.com"
        assert result["SMTP_PORT"] == "465"
        assert result["SMTP_USER"] == "user"
        assert result["SMTP_PASSWORD"] == "pass"
        assert result["SMTP_FROM_EMAIL"] == "from@test.com"


class TestBuildDefaultConfig:
    """Tests for default configuration builder."""

    def test_includes_required_keys(self):
        config = build_default_config()
        required_keys = [
            "DATABASE_URL",
            "STORAGE_PATH",
            "WIKI_PATH",
            "BOOTSTRAP_ADMIN_USERNAME",
            "BOOTSTRAP_ADMIN_PASSWORD",
            "BOOTSTRAP_ADMIN_EMAIL",
            "SECRET_KEY",
            "PDF_ENCRYPTION_PASSWORD",
            "KMS_LOCAL_PASSPHRASE",
            "KMS_PROVIDER",
            "LLM_PROVIDER",
        ]
        for key in required_keys:
            assert key in config, f"Missing key: {key}"

    def test_uses_provided_values(self):
        config = build_default_config(
            db_url="postgresql+asyncpg://localhost/edms",
            admin_username="myadmin",
            admin_password="mypass",
            admin_email="me@example.com",
        )
        assert config["DATABASE_URL"] == "postgresql+asyncpg://localhost/edms"
        assert config["BOOTSTRAP_ADMIN_USERNAME"] == "myadmin"
        assert config["BOOTSTRAP_ADMIN_PASSWORD"] == "mypass"
        assert config["BOOTSTRAP_ADMIN_EMAIL"] == "me@example.com"


class TestWebSetupWizard:
    """Tests for the web-based setup wizard."""

    @pytest_asyncio.fixture
    async def setup_client(self):
        from app.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac

    @pytest.mark.asyncio
    async def test_setup_status_endpoint(self, setup_client: AsyncClient):
        with patch("app.setup_wizard.web.is_first_launch", return_value=True):
            resp = await setup_client.get("/api/setup/status")
        assert resp.status_code == 200
        assert resp.json()["needs_setup"] is True

    @pytest.mark.asyncio
    async def test_setup_status_configured(self, setup_client: AsyncClient):
        with patch("app.setup_wizard.web.is_first_launch", return_value=False):
            resp = await setup_client.get("/api/setup/status")
        assert resp.status_code == 200
        assert resp.json()["needs_setup"] is False

    @pytest.mark.asyncio
    async def test_setup_page_redirects_when_configured(
        self, setup_client: AsyncClient
    ):
        with patch("app.setup_wizard.web.is_first_launch", return_value=False):
            resp = await setup_client.get("/setup", follow_redirects=False)
        assert resp.status_code == 307
        assert "/login" in resp.headers["location"]

    @pytest.mark.asyncio
    async def test_setup_page_shows_when_needed(self, setup_client: AsyncClient):
        with patch("app.setup_wizard.web.is_first_launch", return_value=True):
            resp = await setup_client.get("/setup")
        assert resp.status_code == 200
        assert "Setup Wizard" in resp.text

    @pytest.mark.asyncio
    async def test_configure_endpoint_rejects_when_configured(
        self, setup_client: AsyncClient
    ):
        with patch("app.setup_wizard.web.is_first_launch", return_value=False):
            resp = await setup_client.post(
                "/api/setup/configure",
                json={"database_url": "sqlite+aiosqlite:///./test.db"},
            )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_configure_endpoint_success(
        self, setup_client: AsyncClient, tmp_path: Path
    ):
        env_path = tmp_path / ".env"
        with patch("app.setup_wizard.web.is_first_launch", return_value=True):
            resp = await setup_client.post(
                "/api/setup/configure",
                json={
                    "database_url": "sqlite+aiosqlite:///./test.db",
                    "admin_username": "testadmin",
                    "admin_password": "testpass",
                    "admin_email": "test@test.com",
                    "env_path": str(env_path),
                    "storage_base_path": str(tmp_path),
                },
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert "kek_shares" in data
        assert len(data["kek_shares"]["shares"]) == 3
        assert env_path.exists()


class TestCLI:
    """Tests for the CLI entry point."""

    def test_help_flag(self):
        import subprocess

        result = subprocess.run(
            ["python", "-m", "app.setup_wizard", "--help"],
            capture_output=True,
            text=True,
            cwd="/projects/sandbox/edms",
        )
        assert result.returncode == 0
        assert "EDMS First-Time Setup Wizard" in result.stdout
        assert "--non-interactive" in result.stdout

    def test_non_interactive_mode(self, tmp_path: Path):
        import subprocess

        env_file = tmp_path / ".env"
        env = os.environ.copy()
        env["EDMS_ADMIN_USERNAME"] = "ci-admin"
        env["EDMS_ADMIN_PASSWORD"] = "ci-pass"

        result = subprocess.run(
            [
                "python", "-m", "app.setup_wizard",
                "--non-interactive",
                "--env-file", str(env_file),
            ],
            capture_output=True,
            text=True,
            cwd="/projects/sandbox/edms",
            env=env,
        )
        assert result.returncode == 0
        assert env_file.exists()
        content = env_file.read_text()
        assert "ci-admin" in content
        assert "ci-pass" in content
