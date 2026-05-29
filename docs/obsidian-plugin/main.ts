import { App, Modal, Notice, Plugin, PluginSettingTab, Setting, ItemView, WorkspaceLeaf } from 'obsidian';

// --- Settings ---

interface EDMSPluginSettings {
    serverUrl: string;
    apiToken: string;
    autoSyncOnStartup: boolean;
    syncIntervalMinutes: number;
}

const DEFAULT_SETTINGS: EDMSPluginSettings = {
    serverUrl: 'http://localhost:8000',
    apiToken: '',
    autoSyncOnStartup: false,
    syncIntervalMinutes: 0,
};

// --- Sidebar View ---

const VIEW_TYPE_EDMS_METADATA = 'edms-metadata-view';

class EDMSMetadataView extends ItemView {
    plugin: EDMSPlugin;

    constructor(leaf: WorkspaceLeaf, plugin: EDMSPlugin) {
        super(leaf);
        this.plugin = plugin;
    }

    getViewType(): string {
        return VIEW_TYPE_EDMS_METADATA;
    }

    getDisplayText(): string {
        return 'EDMS Metadata';
    }

    async onOpen(): Promise<void> {
        const container = this.containerEl.children[1];
        container.empty();
        container.createEl('h4', { text: 'EDMS Document Metadata' });
        container.createEl('p', { text: 'Open a wiki page to view its metadata.' });
    }

    async onClose(): Promise<void> {
        // Cleanup
    }

    async displayMetadata(filePath: string): Promise<void> {
        const container = this.containerEl.children[1];
        container.empty();
        container.createEl('h4', { text: 'EDMS Metadata' });

        try {
            const response = await fetch(
                `${this.plugin.settings.serverUrl}/api/wiki/export/obsidian/page/${filePath}`,
                {
                    headers: { 'Authorization': `Bearer ${this.plugin.settings.apiToken}` }
                }
            );
            if (response.ok) {
                const data = await response.json();
                container.createEl('p', { text: `Path: ${data.path}` });
                container.createEl('pre', { text: data.content.substring(0, 500) });
            } else {
                container.createEl('p', { text: 'No metadata available for this page.' });
            }
        } catch (e) {
            container.createEl('p', { text: 'Error loading metadata.' });
        }
    }
}

// --- Search Modal ---

class EDMSSearchModal extends Modal {
    plugin: EDMSPlugin;

    constructor(app: App, plugin: EDMSPlugin) {
        super(app);
        this.plugin = plugin;
    }

    onOpen(): void {
        const { contentEl } = this;
        contentEl.createEl('h2', { text: 'Search EDMS Documents' });

        const inputEl = contentEl.createEl('input', {
            type: 'text',
            placeholder: 'Enter search query...',
        });
        inputEl.style.width = '100%';
        inputEl.style.marginBottom = '10px';

        const resultsEl = contentEl.createEl('div');

        inputEl.addEventListener('keyup', async (e: KeyboardEvent) => {
            if (e.key === 'Enter') {
                const query = inputEl.value;
                await this.search(query, resultsEl);
            }
        });
    }

    async search(query: string, resultsEl: HTMLElement): Promise<void> {
        resultsEl.empty();
        try {
            const response = await fetch(
                `${this.plugin.settings.serverUrl}/api/search?q=${encodeURIComponent(query)}`,
                {
                    headers: { 'Authorization': `Bearer ${this.plugin.settings.apiToken}` }
                }
            );
            if (response.ok) {
                const data = await response.json();
                const results = data.results || [];
                if (results.length === 0) {
                    resultsEl.createEl('p', { text: 'No results found.' });
                } else {
                    for (const result of results) {
                        resultsEl.createEl('p', { text: `${result.title} (ID: ${result.id})` });
                    }
                }
            }
        } catch (e) {
            resultsEl.createEl('p', { text: 'Search failed.' });
        }
    }

    onClose(): void {
        const { contentEl } = this;
        contentEl.empty();
    }
}

// --- Settings Tab ---

class EDMSSettingTab extends PluginSettingTab {
    plugin: EDMSPlugin;

    constructor(app: App, plugin: EDMSPlugin) {
        super(app, plugin);
        this.plugin = plugin;
    }

    display(): void {
        const { containerEl } = this;
        containerEl.empty();
        containerEl.createEl('h2', { text: 'EDMS Plugin Settings' });

        new Setting(containerEl)
            .setName('Server URL')
            .setDesc('EDMS API base URL')
            .addText(text => text
                .setPlaceholder('http://localhost:8000')
                .setValue(this.plugin.settings.serverUrl)
                .onChange(async (value) => {
                    this.plugin.settings.serverUrl = value;
                    await this.plugin.saveSettings();
                }));

        new Setting(containerEl)
            .setName('API Token')
            .setDesc('JWT authentication token')
            .addText(text => text
                .setPlaceholder('your-jwt-token')
                .setValue(this.plugin.settings.apiToken)
                .onChange(async (value) => {
                    this.plugin.settings.apiToken = value;
                    await this.plugin.saveSettings();
                }));

        new Setting(containerEl)
            .setName('Auto-sync on startup')
            .setDesc('Sync vault when Obsidian opens')
            .addToggle(toggle => toggle
                .setValue(this.plugin.settings.autoSyncOnStartup)
                .onChange(async (value) => {
                    this.plugin.settings.autoSyncOnStartup = value;
                    await this.plugin.saveSettings();
                }));

        new Setting(containerEl)
            .setName('Sync interval (minutes)')
            .setDesc('Automatic sync interval (0 = disabled)')
            .addText(text => text
                .setValue(String(this.plugin.settings.syncIntervalMinutes))
                .onChange(async (value) => {
                    this.plugin.settings.syncIntervalMinutes = parseInt(value) || 0;
                    await this.plugin.saveSettings();
                }));
    }
}

// --- Main Plugin ---

export default class EDMSPlugin extends Plugin {
    settings: EDMSPluginSettings;
    syncInterval: number | null = null;

    async onload(): Promise<void> {
        await this.loadSettings();

        // Register sidebar view
        this.registerView(VIEW_TYPE_EDMS_METADATA, (leaf) => new EDMSMetadataView(leaf, this));

        // Register commands
        this.addCommand({
            id: 'edms-sync-vault',
            name: 'EDMS: Sync Vault',
            callback: () => this.syncVault(),
        });

        this.addCommand({
            id: 'edms-search-documents',
            name: 'EDMS: Search Documents',
            callback: () => new EDMSSearchModal(this.app, this).open(),
        });

        this.addCommand({
            id: 'edms-refresh-metadata',
            name: 'EDMS: Refresh Metadata',
            callback: () => this.refreshMetadata(),
        });

        // Add settings tab
        this.addSettingTab(new EDMSSettingTab(this.app, this));

        // Auto-sync on startup if enabled
        if (this.settings.autoSyncOnStartup) {
            this.syncVault();
        }

        // Set up periodic sync
        if (this.settings.syncIntervalMinutes > 0) {
            this.syncInterval = window.setInterval(
                () => this.syncVault(),
                this.settings.syncIntervalMinutes * 60 * 1000
            );
        }
    }

    onunload(): void {
        if (this.syncInterval !== null) {
            window.clearInterval(this.syncInterval);
        }
    }

    async loadSettings(): Promise<void> {
        this.settings = Object.assign({}, DEFAULT_SETTINGS, await this.loadData());
    }

    async saveSettings(): Promise<void> {
        await this.saveData(this.settings);
    }

    async syncVault(): Promise<void> {
        new Notice('EDMS: Starting vault sync...');
        try {
            // Export vault as zip and POST to EDMS sync import endpoint
            const response = await fetch(
                `${this.settings.serverUrl}/api/wiki/sync/import`,
                {
                    method: 'POST',
                    headers: { 'Authorization': `Bearer ${this.settings.apiToken}` },
                    // In a real implementation, this would create a zip of the vault
                    body: new FormData(),
                }
            );
            if (response.ok) {
                const result = await response.json();
                new Notice(
                    `EDMS Sync: ${result.pages_created} created, ` +
                    `${result.pages_updated} updated, ${result.pages_deleted} deleted`
                );
            } else {
                new Notice('EDMS Sync failed: ' + response.statusText);
            }
        } catch (e) {
            new Notice('EDMS Sync error: ' + (e as Error).message);
        }
    }

    async refreshMetadata(): Promise<void> {
        const activeFile = this.app.workspace.getActiveFile();
        if (!activeFile) {
            new Notice('No active file to display metadata for.');
            return;
        }

        const leaves = this.app.workspace.getLeavesOfType(VIEW_TYPE_EDMS_METADATA);
        if (leaves.length > 0) {
            const view = leaves[0].view as EDMSMetadataView;
            await view.displayMetadata(activeFile.path);
        }
    }
}
