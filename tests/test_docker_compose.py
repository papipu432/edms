"""Tests for docker-compose.chroma.yml and ChromaDB configuration."""

from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).parent.parent


class TestDockerComposeChroma:
    """Test suite for the hardened ChromaDB Docker Compose configuration."""

    def setup_method(self) -> None:
        compose_path = PROJECT_ROOT / "docker-compose.chroma.yml"
        assert compose_path.exists(), "docker-compose.chroma.yml must exist"
        with open(compose_path) as f:
            self.compose = yaml.safe_load(f)

    def test_file_is_valid_yaml(self) -> None:
        """docker-compose.chroma.yml should be valid YAML."""
        assert self.compose is not None
        assert isinstance(self.compose, dict)

    def test_contains_chromadb_service(self) -> None:
        """Should contain a 'chromadb' service."""
        assert "services" in self.compose
        assert "chromadb" in self.compose["services"]

    def test_port_binding_localhost_only(self) -> None:
        """Port binding must be 127.0.0.1:8000:8000 (localhost only)."""
        service = self.compose["services"]["chromadb"]
        assert "ports" in service
        ports = service["ports"]
        assert "127.0.0.1:8000:8000" in ports

    def test_security_opt_no_new_privileges(self) -> None:
        """security_opt must contain no-new-privileges:true."""
        service = self.compose["services"]["chromadb"]
        assert "security_opt" in service
        assert "no-new-privileges:true" in service["security_opt"]

    def test_read_only_filesystem(self) -> None:
        """Container must have read_only: true."""
        service = self.compose["services"]["chromadb"]
        assert service.get("read_only") is True

    def test_tmpfs_configured(self) -> None:
        """tmpfs must be configured for /tmp."""
        service = self.compose["services"]["chromadb"]
        assert "tmpfs" in service
        tmpfs = service["tmpfs"]
        assert any("/tmp" in entry for entry in tmpfs)

    def test_healthcheck_defined(self) -> None:
        """A healthcheck must be defined for the service."""
        service = self.compose["services"]["chromadb"]
        assert "healthcheck" in service
        healthcheck = service["healthcheck"]
        assert "test" in healthcheck
        assert "interval" in healthcheck
        assert "timeout" in healthcheck
        assert "retries" in healthcheck

    def test_environment_has_auth_provider(self) -> None:
        """Environment must configure token authentication provider."""
        service = self.compose["services"]["chromadb"]
        assert "environment" in service
        env = service["environment"]
        auth_configured = any(
            "CHROMA_SERVER_AUTHN_PROVIDER" in entry for entry in env
        )
        assert auth_configured, "Token auth provider must be configured"

    def test_chroma_config_token_exists(self) -> None:
        """chroma_config/token.txt must exist."""
        token_path = PROJECT_ROOT / "chroma_config" / "token.txt"
        assert token_path.exists(), "chroma_config/token.txt must exist"
        content = token_path.read_text().strip()
        assert len(content) > 0, "Token file must not be empty"

    def test_container_name(self) -> None:
        """Container name should be chromadb-dms."""
        service = self.compose["services"]["chromadb"]
        assert service.get("container_name") == "chromadb-dms"

    def test_restart_policy(self) -> None:
        """Restart policy should be unless-stopped."""
        service = self.compose["services"]["chromadb"]
        assert service.get("restart") == "unless-stopped"

    def test_persistence_enabled(self) -> None:
        """CHROMA_IS_PERSISTENT must be TRUE in environment."""
        service = self.compose["services"]["chromadb"]
        env = service["environment"]
        persistent_configured = any("CHROMA_IS_PERSISTENT=TRUE" in entry for entry in env)
        assert persistent_configured, "Persistence must be enabled"


class TestChromaConfig:
    """Test the ChromaDB configuration settings."""

    def test_config_has_chroma_host(self) -> None:
        """Settings must include CHROMA_HOST."""
        from app.core.config import Settings

        s = Settings()
        assert hasattr(s, "CHROMA_HOST")
        assert s.CHROMA_HOST == ""

    def test_config_has_chroma_auth_token(self) -> None:
        """Settings must include CHROMA_AUTH_TOKEN."""
        from app.core.config import Settings

        s = Settings()
        assert hasattr(s, "CHROMA_AUTH_TOKEN")
        assert s.CHROMA_AUTH_TOKEN == ""

    def test_config_has_chroma_port(self) -> None:
        """Settings must include CHROMA_PORT."""
        from app.core.config import Settings

        s = Settings()
        assert hasattr(s, "CHROMA_PORT")
        assert s.CHROMA_PORT == 8000

    def test_embedded_mode_when_host_empty(self) -> None:
        """When CHROMA_HOST is empty, VectorDBService uses embedded mode."""
        import tempfile

        from app.services.vectordb import _create_chroma_client

        with tempfile.TemporaryDirectory() as tmpdir:
            client = _create_chroma_client(persist_directory=tmpdir, host="")
            # PersistentClient does not have _server_url attribute
            assert not hasattr(client, "_server_url") or client._server_url is None  # noqa: SLF001


class TestGitignore:
    """Test that .gitignore has proper entries."""

    def test_chroma_data_in_gitignore(self) -> None:
        """chroma_data/ should be in .gitignore."""
        gitignore_path = PROJECT_ROOT / ".gitignore"
        content = gitignore_path.read_text()
        assert "chroma_data/" in content
