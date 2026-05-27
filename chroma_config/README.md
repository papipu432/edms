# ChromaDB Authentication Configuration

This directory contains the authentication configuration for the ChromaDB Docker service.

## Setup

1. Replace the contents of `token.txt` with a secure random token:

   ```bash
   openssl rand -hex 32 > chroma_config/token.txt
   ```

2. Set the same token in your application's `.env` file:

   ```
   CHROMA_AUTH_TOKEN=<contents of token.txt>
   CHROMA_HOST=localhost
   CHROMA_PORT=8000
   ```

3. Start ChromaDB with Docker Compose:

   ```bash
   docker compose -f docker-compose.chroma.yml up -d
   ```

## Security Notes

- Never commit the actual token to version control.
- The `token.txt` file should contain only the token string (no newlines or extra whitespace).
- Rotate the token periodically by updating both `token.txt` and the `CHROMA_AUTH_TOKEN` environment variable.
- The Docker service binds only to 127.0.0.1 (localhost), preventing external network access.
- The container runs with a read-only filesystem and no-new-privileges security options.
