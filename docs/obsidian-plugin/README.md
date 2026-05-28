# EDMS Obsidian Plugin

Connect your Obsidian vault to an EDMS (Enterprise Document Management System) instance for seamless bi-directional sync, search, and document metadata viewing.

## Features

### Connect to EDMS API
- Configure your EDMS server URL and authentication token in the plugin settings.
- Secure HTTPS connection with JWT-based authentication.

### Sync Vault on Command
- Use the command palette to trigger a full vault sync.
- Bi-directional sync: push local changes to EDMS and pull updates.
- Conflict resolution: user-created pages (entities, topics) use the Obsidian version; auto-generated summaries keep the EDMS version.

### Search EDMS from Obsidian
- Search the EDMS document index directly from Obsidian.
- Results appear in a modal with links to open documents or wiki pages.
- Full-text and keyword search support.

### Show Document Metadata in Sidebar
- A dedicated sidebar view shows metadata for the currently open wiki page.
- Displays: document ID, upload date, keywords, lifecycle state, and related entities.
- Click links to navigate to related pages within the vault.

## Installation

1. Copy the plugin folder to your vault's `.obsidian/plugins/edms-obsidian-plugin/` directory.
2. Enable the plugin in Obsidian Settings > Community Plugins.
3. Configure the EDMS server URL and API token in the plugin settings tab.

## Commands

| Command | Description |
|---------|-------------|
| EDMS: Sync Vault | Sync entire vault with EDMS |
| EDMS: Search Documents | Open search modal for EDMS documents |
| EDMS: Refresh Metadata | Refresh sidebar metadata for current page |

## Settings

| Setting | Description | Default |
|---------|-------------|---------|
| Server URL | EDMS API base URL | `http://localhost:8000` |
| API Token | JWT authentication token | (empty) |
| Auto-sync on startup | Sync vault when Obsidian opens | `false` |
| Sync interval (minutes) | Automatic sync interval (0 = disabled) | `0` |
