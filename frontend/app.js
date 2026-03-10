/**
 * Comic Demo — Redesigned SPA Frontend
 * Views: Home (Chat) / Generate (Timeline) / Assets (Gallery)
 *
 * Model dropdowns for all three modes (text, image, video) are dynamically
 * populated from the backend /api/providers endpoint.
 */

// ── Gateway Connection ─────────────────────────────────────────────────────
class GatewayConnection {
    constructor(onEvent, onStatusChange) {
        this.ws = null;
        this.sessionId = null;
        this.onEvent = onEvent;
        this.onStatusChange = onStatusChange;
        this.reconnectAttempts = 0;
        this.maxReconnects = 5;
        this.heartbeatTimer = null;
    }

    connect() {
        const proto = location.protocol === 'https:' ? 'wss' : 'ws';
        const url = `${proto}://${location.host}/ws`;
        console.log(`[Gateway] Connecting to ${url}...`);
        this.onStatusChange('connecting');

        try {
            this.ws = new WebSocket(url);
        } catch (e) {
            console.error('[Gateway] Connection error:', e);
            this.onStatusChange('disconnected');
            this.scheduleReconnect();
            return;
        }

        this.ws.onopen = () => {
            console.log('[Gateway] Opened');
            this.reconnectAttempts = 0;
            this.onStatusChange('connected');
            this.startHeartbeat();
        };

        this.ws.onmessage = (e) => {
            try {
                const event = JSON.parse(e.data);
                if (event.type === 'connected') {
                    this.sessionId = event.session_id;
                    console.log(`[Gateway] Session ID: ${this.sessionId}`);
                }
                if (event.type !== 'pong') {
                    this.onEvent(event);
                }
            } catch (err) {
                console.error('[Gateway] Parse error:', err);
            }
        };

        this.ws.onclose = () => {
            console.log('[Gateway] Closed');
            this.stopHeartbeat();
            this.onStatusChange('disconnected');
            this.scheduleReconnect();
        };

        this.ws.onerror = (err) => {
            console.error('[Gateway] WS Error:', err);
            this.onStatusChange('disconnected');
        };
    }

    send(type, content) {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            console.log(`[Gateway] Sending: ${type}`, content);
            this.ws.send(JSON.stringify({ type, content }));
        } else {
            console.warn('[Gateway] Cannot send, WS not open.');
        }
    }

    startHeartbeat() {
        this.heartbeatTimer = setInterval(() => {
            this.send('ping', '');
        }, 30000);
    }

    stopHeartbeat() {
        if (this.heartbeatTimer) {
            clearInterval(this.heartbeatTimer);
            this.heartbeatTimer = null;
        }
    }

    scheduleReconnect() {
        if (this.reconnectAttempts < this.maxReconnects) {
            this.reconnectAttempts++;
            const delay = Math.min(1000 * Math.pow(2, this.reconnectAttempts), 16000);
            console.log(`[Gateway] Reconnecting in ${delay}ms...`);
            setTimeout(() => this.connect(), delay);
        }
    }

    disconnect() {
        this.stopHeartbeat();
        if (this.ws) this.ws.close();
    }
}

// ── Chat Renderer ──────────────────────────────────────────────────────────
class ChatRenderer {
    constructor(container, welcomeScreen, chatArea) {
        this.container = container;
        this.welcomeScreen = welcomeScreen;
        this.chatArea = chatArea;
    }

    hideWelcome() {
        if (this.welcomeScreen) {
            this.welcomeScreen.style.display = 'none';
        }
        if (this.chatArea) {
            this.chatArea.classList.add('expanded');
        }
    }

    showWelcome() {
        if (this.welcomeScreen) {
            this.welcomeScreen.style.display = '';
        }
        if (this.chatArea) {
            this.chatArea.classList.remove('expanded');
        }
    }

    addMessage(type, content, params = null) {
        this.hideWelcome();
        const msg = document.createElement('div');
        msg.className = `message ${type}`;

        const avatarIcon = type === 'user' ? 'fa-user'
            : type === 'system' ? 'fa-info-circle'
                : 'fa-robot';

        const time = new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });

        // Media rendering
        let renderedContent = this.escapeHtml(content);
        const paramsHTML = this.renderParams(params);

        msg.innerHTML = `
            <div class="message-avatar"><i class="fas ${avatarIcon}"></i></div>
            <div class="message-body">
                <div class="message-content">${renderedContent}</div>
                ${paramsHTML}
                <div class="message-time">${time}</div>
            </div>
        `;

        this.container.appendChild(msg);
        this.scrollToBottom();
        return msg;
    }

    /**
     * Add a user message with attached media (uploaded reference images/videos).
     * Shows the media thumbnails above the text prompt in the user's bubble.
     */
    addUserMessageWithMedia(text, attachments = []) {
        this.hideWelcome();
        const msg = document.createElement('div');
        msg.className = 'message user';

        const time = new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });

        // Build attachment preview HTML
        let attachHTML = '';
        if (attachments.length > 0) {
            attachHTML = '<div class="message-attachments">';
            for (const att of attachments) {
                if (att.type === 'video') {
                    attachHTML += `<div class="attachment-thumb"><video src="${this.escapeHtml(att.url)}" muted preload="metadata" style="width:100%;height:100%;object-fit:cover;border-radius:8px;"></video><div class="attachment-label"><i class="fas fa-film"></i> ${this.escapeHtml(att.label)}</div></div>`;
                } else {
                    attachHTML += `<div class="attachment-thumb"><img src="${this.escapeHtml(att.url)}" alt="${this.escapeHtml(att.label)}" loading="lazy"><div class="attachment-label"><i class="fas fa-image"></i> ${this.escapeHtml(att.label)}</div></div>`;
                }
            }
            attachHTML += '</div>';
        }

        msg.innerHTML = `
            <div class="message-avatar"><i class="fas fa-user"></i></div>
            <div class="message-body">
                ${attachHTML}
                <div class="message-content">${this.escapeHtml(text)}</div>
                <div class="message-time">${time}</div>
            </div>
        `;

        this.container.appendChild(msg);
        this.scrollToBottom();
        return msg;
    }

    addMediaMessage(mediaType, urls, params = null) {
        this.hideWelcome();
        const msg = document.createElement('div');
        msg.className = 'message agent';

        const time = new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });

        let mediaHTML = '';
        for (const url of urls) {
            const safeUrl = this.escapeHtml(url);
            const downloadBtn = `<button class="media-download-btn" onclick="event.stopPropagation(); downloadMedia('${safeUrl}')" title="下载"><i class="fas fa-download"></i></button>`;
            if (mediaType === 'image') {
                mediaHTML += `<div class="media-content">${downloadBtn}<img src="${safeUrl}" alt="Generated Image" loading="lazy" onerror="this.parentElement.innerHTML='<p>图片加载失败</p>'"></div>`;
            } else if (mediaType === 'video') {
                mediaHTML += `<div class="media-content">${downloadBtn}<video src="${safeUrl}" controls preload="metadata" onerror="this.parentElement.innerHTML='<p>视频加载失败</p>'"></video></div>`;
            }
        }

        const paramsHTML = this.renderParams(params);

        msg.innerHTML = `
            <div class="message-avatar"><i class="fas fa-robot"></i></div>
            <div class="message-body">
                <div class="message-content">${mediaHTML}</div>
                ${paramsHTML}
                <div class="message-time">${time}</div>
            </div>
        `;

        this.container.appendChild(msg);
        this.scrollToBottom();
        return msg;
    }

    renderParams(params) {
        if (!params || Object.keys(params).length === 0) return '';
        let html = '<div class="message-params">';
        for (const [key, value] of Object.entries(params)) {
            // Friendly labels
            const labels = {
                model: '模型',
                ratio: '比例',
                resolution: '分辨率',
                duration: '时长',
                seed: '种子',
                camera_fixed: '锁定机位'
            };
            const label = labels[key] || key;
            html += `<span class="param-tag">${this.escapeHtml(label)}: ${this.escapeHtml(value)}</span>`;
        }
        html += '</div>';
        return html;
    }

    addNodeProgress(nodeName, status) {
        this.hideWelcome();
        const card = document.createElement('div');
        card.className = 'message agent';
        card.dataset.node = nodeName;

        const statusClass = status === 'running' ? 'running' : 'complete';
        const statusText = status === 'running' ? '运行中...' : '完成';

        card.innerHTML = `
            <div class="message-avatar"><i class="fas fa-robot"></i></div>
            <div class="message-body">
                <div class="node-progress-card">
                    <div class="node-progress-header">
                        <div class="node-icon"><i class="fas fa-cog"></i></div>
                        <div class="node-name">${this.escapeHtml(nodeName)}</div>
                        <div class="node-status ${statusClass}">${statusText}</div>
                    </div>
                    <div class="node-progress-bar">
                        <div class="node-progress-fill" style="width: ${status === 'running' ? '60%' : '100%'}"></div>
                    </div>
                </div>
            </div>
        `;

        this.container.appendChild(card);
        this.scrollToBottom();
        return card;
    }

    addTypingIndicator() {
        this.hideWelcome();
        const el = document.createElement('div');
        el.className = 'message agent';
        el.id = 'typingIndicator';
        el.innerHTML = `
            <div class="message-avatar"><i class="fas fa-robot"></i></div>
            <div class="message-body">
                <div class="typing-indicator">
                    <div class="typing-dot"></div>
                    <div class="typing-dot"></div>
                    <div class="typing-dot"></div>
                </div>
            </div>
        `;
        this.container.appendChild(el);
        this.scrollToBottom();
        return el;
    }

    removeTypingIndicator() {
        const el = document.getElementById('typingIndicator');
        if (el) el.remove();
    }

    clearMessages() {
        const messages = this.container.querySelectorAll('.message');
        messages.forEach(m => m.remove());
        this.showWelcome();
    }

    scrollToBottom() {
        requestAnimationFrame(() => {
            const chatArea = document.getElementById('chatArea');
            if (chatArea) chatArea.scrollTop = chatArea.scrollHeight;
        });
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
}

// ── Session History Store ──────────────────────────────────────────────────
class SessionStore {
    constructor() {
        this.STORAGE_KEY = 'comic_demo_sessions';
        this.sessions = this.load();
    }

    load() {
        try {
            const data = localStorage.getItem(this.STORAGE_KEY);
            if (!data) return [];
            const parsed = JSON.parse(data);
            return parsed.map(s => ({
                ...s,
                timestamp: new Date(s.timestamp)
            }));
        } catch (e) {
            console.error('[SessionStore] Load error:', e);
            return [];
        }
    }

    save() {
        try {
            localStorage.setItem(this.STORAGE_KEY, JSON.stringify(this.sessions));
        } catch (e) {
            console.error('[SessionStore] Save error:', e);
        }
    }

    setSessions(newSessions) {
        // Merge or replace. Here we replace to treat backend as source of truth, 
        // but convert timestamps back to Date objects.
        this.sessions = newSessions.map(s => ({
            ...s,
            timestamp: new Date(s.timestamp)
        }));
        this.save();
    }

    add(entry) {
        this.sessions.push({
            id: Date.now() + '_' + Math.random().toString(36).substring(2, 8),
            timestamp: new Date(),
            mode: entry.mode || 'llm',
            input: entry.input || '',
            output: entry.output || '',
            mediaType: entry.mediaType || null,   // 'image' | 'video' | null
            mediaUrl: entry.mediaUrl || null,
            params: entry.params || null,
            refImages: entry.refImages || null,   // Array of {url} for ref-style sessions
        });
        this.save();
    }

    getAll(sortOrder = 'desc') {
        const sorted = [...this.sessions];
        sorted.sort((a, b) => sortOrder === 'desc'
            ? b.timestamp - a.timestamp
            : a.timestamp - b.timestamp
        );
        return sorted;
    }

    getAssets(filterType = 'all') {
        return this.sessions.filter(s => {
            if (!s.mediaUrl) return false;
            if (filterType === 'all') return true;
            return s.mediaType === filterType;
        });
    }
}

// ── App Initialization ─────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    // DOM refs
    const chatArea = document.getElementById('chatArea');
    const chatContainer = document.getElementById('chatContainer');
    const welcomeScreen = document.getElementById('welcomeScreen');
    const chatInput = document.getElementById('chatInput');
    const sendBtn = document.getElementById('sendBtn');

    // Views & Nav
    const views = {
        home: document.getElementById('home-view'),
        gen: document.getElementById('gen-view'),
        assets: document.getElementById('assets-view'),
    };
    const navItems = document.querySelectorAll('.nav-item');

    // Generate page refs
    const genTimeline = document.getElementById('genTimeline');
    const genEmptyState = document.getElementById('genEmptyState');
    const genSearchInput = document.getElementById('genSearchInput');
    const genSortSelect = document.getElementById('genSortSelect');

    // Assets page refs
    const assetsTimeline = document.getElementById('assetsTimeline');
    const assetsEmptyState = document.getElementById('assetsEmptyState');
    const filterTabs = document.querySelectorAll('.filter-tab');

    // Main Mode selectors
    const modeLabel = document.getElementById('modeLabel');
    const modeIcon = document.getElementById('modeIcon');

    // Mode-specific control containers
    const textControls = document.getElementById('textControls');
    const imageControls = document.getElementById('imageControls');
    const videoControls = document.getElementById('videoControls');
    const frameUploadArea = document.getElementById('frameUploadArea');

    // Upload cards
    const firstFrameCard = document.getElementById('firstFrameCard');
    const lastFrameCard = document.getElementById('lastFrameCard');
    const frameDivider = document.getElementById('frameDivider');
    const refImagesContainer = document.getElementById('refImagesContainer');
    const refImagesTimeline = document.getElementById('refImagesTimeline');
    const sampleVideoCard = document.getElementById('sampleVideoCard');

    // State
    let currentView = 'home';
    let currentLlmMode = 'llm';
    let currentAssetFilter = 'all';
    let isProcessing = false;
    let pendingInput = '';
    let currentVideoRefMode = 'text-only'; // text-only | first-frame | first-last-frame | ref-style | sample-video

    // Uploaded file URLs (set after upload to /api/upload_frame)
    let uploadedFirstFrame = null;
    let uploadedLastFrame = null;
    let uploadedRefImages = []; // Array of {url, description} for ref-style mode (up to 4)
    let uploadedSampleVideo = null;

    // Provider state: { llm: {...}, image_llm: {...}, video_llm: {...} }
    let providersData = null;
    // Currently selected provider IDs for each mode
    let selectedProviders = {
        'llm': '',
        'image_llm': '',
        'video_llm': '',
    };

    const renderer = new ChatRenderer(chatContainer, welcomeScreen, chatArea);
    const store = new SessionStore();

    // ── Mode config ───────────────────────────────────────────────────────
    const modeConfig = {
        'llm': {
            placeholder: '输入文本对话内容...',
            wsType: 'test_llm',
            label: '文本输入',
            icon: 'fas fa-comment-dots',
            category: 'llm',
        },
        'image-llm': {
            placeholder: '描述你想生成的图片...',
            wsType: 'test_image_llm',
            label: '图片生成',
            icon: 'fas fa-image',
            category: 'image_llm',
        },
        'video-llm': {
            placeholder: '描述你想生成的视频...',
            wsType: 'test_video_llm',
            label: '视频生成',
            icon: 'fas fa-video',
            category: 'video_llm',
        },
    };

    // ── Category → Mode mapping for convenience ───────────────────────────
    const categoryToMode = {
        'llm': 'llm',
        'image_llm': 'image-llm',
        'video_llm': 'video-llm',
    };

    // ── Fetch Providers from Backend ─────────────────────────────────────
    async function fetchProviders() {
        try {
            const resp = await fetch('/api/providers');
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
            providersData = await resp.json();
            console.log('[App] Providers loaded:', providersData);

            // Populate dropdowns
            populateModelDropdown('llm', 'textModelDropdownMenu', 'textModelLabel');
            populateModelDropdown('image_llm', 'imageModelDropdownMenu', 'imageModelLabel');
            populateModelDropdown('video_llm', 'modelDropdownMenu', 'modelLabel');
        } catch (e) {
            console.error('[App] Failed to fetch providers:', e);
        }
    }

    function populateModelDropdown(category, menuId, labelId) {
        const menu = document.getElementById(menuId);
        const label = document.getElementById(labelId);
        if (!menu || !providersData || !providersData[category]) return;

        const catData = providersData[category];
        const defaultId = catData.default;
        const providers = catData.providers || [];

        // Remove existing dynamic items (keep the header)
        const header = menu.querySelector('.mini-dropdown-header');
        menu.innerHTML = '';
        if (header) menu.appendChild(header);

        providers.forEach(p => {
            const item = document.createElement('div');
            item.className = 'mini-dropdown-item' + (p.id === defaultId ? ' active' : '');
            item.dataset.value = p.id;

            // Store supported modes as a dataset attribute for video models
            if (p.supported_modes && p.supported_modes.length > 0) {
                item.dataset.supportedModes = p.supported_modes.join(',');
            }

            item.innerHTML = `
                <span class="model-name">${escapeHtml(p.display_name)}</span>
                ${p.description ? `<span class="model-desc">${escapeHtml(p.description)}</span>` : ''}
                <i class="fas fa-check check-icon"></i>
            `;
            menu.appendChild(item);
        });

        // Set default selection
        let initialModelId = null;
        if (defaultId) {
            selectedProviders[category] = defaultId;
            initialModelId = defaultId;
            const defaultProvider = providers.find(p => p.id === defaultId);
            if (defaultProvider) {
                if (label) label.textContent = defaultProvider.display_name;
            }
        } else if (providers.length > 0) {
            selectedProviders[category] = providers[0].id;
            initialModelId = providers[0].id;
            if (label) label.textContent = providers[0].display_name;
            if (modeModelLabel) modeModelLabel.textContent = providers[0].display_name;
        }

        // If this is the video model dropdown, trigger mode availability check
        if (category === 'video_llm' && initialModelId) {
            updateModeAvailability(initialModelId);
        }
    }

    function updateModeAvailability(videoModelId) {
        const menu = document.getElementById('modelDropdownMenu');
        if (!menu) return;

        const selectedItem = menu.querySelector(`[data-value="${videoModelId}"]`);
        if (!selectedItem || !selectedItem.dataset.supportedModes) return;

        const supportedModes = selectedItem.dataset.supportedModes.split(',');
        const refModeMenu = document.getElementById('refModeDropdownMenu');
        if (!refModeMenu) return;

        let activeModeStillSupported = false;

        refModeMenu.querySelectorAll('.mini-dropdown-item:not(.mini-dropdown-header)').forEach(item => {
            const mode = item.dataset.value;
            const isSupported = supportedModes.includes(mode);

            if (isSupported) {
                item.classList.remove('disabled');
            } else {
                item.classList.add('disabled');
            }

            if (item.classList.contains('active') && isSupported) {
                activeModeStillSupported = true;
            }
        });

        // If the current video generation mode is no longer supported by the new model, fallback to text-only
        if (!activeModeStillSupported) {
            const textOnlyItem = refModeMenu.querySelector('[data-value="text-only"]');
            if (textOnlyItem) {
                // Simulate a click on the text-only option to trigger all UI updates
                textOnlyItem.click();
            }
        }
    }

    // ── SPA Routing ───────────────────────────────────────────────────
    function switchView(viewName) {
        currentView = viewName;
        Object.entries(views).forEach(([key, el]) => {
            el.classList.toggle('hidden', key !== viewName);
        });
        navItems.forEach(item => {
            item.classList.toggle('active', item.dataset.view === viewName);
        });

        // Refresh data when switching to gen/assets
        if (viewName === 'gen') renderGenTimeline();
        if (viewName === 'assets') renderAssetsTimeline();
    }

    navItems.forEach(item => {
        item.addEventListener('click', () => {
            switchView(item.dataset.view);
        });
    });

    // ── LLM Mode Dropdown ─────────────────────────────────────────────

    function setLlmMode(mode) {
        currentLlmMode = mode;
        const cfg = modeConfig[mode];
        if (modeLabel) modeLabel.textContent = cfg.label;
        if (modeIcon) modeIcon.className = cfg.icon;
        chatInput.placeholder = cfg.placeholder;

        // Update active state in mode dropdown menu
        const modeMenu = document.getElementById('modeDropdownMenu');
        if (modeMenu) {
            modeMenu.querySelectorAll('.mini-dropdown-item').forEach(item => {
                const isActive = item.dataset.mode === mode;
                item.classList.toggle('active', isActive);
                const checkIcon = item.querySelector('.check-icon');
                if (checkIcon) checkIcon.style.opacity = isActive ? '1' : '0';
            });
        }

        // Show/hide mode-specific controls
        const isText = (mode === 'llm');
        const isImage = (mode === 'image-llm');
        const isVideo = (mode === 'video-llm');

        textControls.classList.toggle('hidden', !isText);
        imageControls.classList.toggle('hidden', !isImage);
        videoControls.classList.toggle('hidden', !isVideo);

        // Ensure proper reference mode UI is applied when switching to video mode
        if (isVideo) {
            updateVideoRefModeUI(currentVideoRefMode);
        } else {
            frameUploadArea.classList.add('hidden');
        }

        // Close dropdown
        closeAllDropdowns();
        chatInput.focus();
    }

    // ── Mini Dropdowns — Generic System ────────────────────────────────
    setupMiniDropdown('modeDropdownTrigger', 'modeDropdownMenu', (value, item) => {
        setLlmMode(item.dataset.mode);
    });

    function setupMiniDropdown(triggerId, menuId, onSelect) {
        const trigger = document.getElementById(triggerId);
        const menu = document.getElementById(menuId);
        if (!trigger || !menu) return;

        trigger.addEventListener('click', (e) => {
            e.stopPropagation();

            // Close all other mini dropdowns
            document.querySelectorAll('.mini-dropdown-menu.open').forEach(m => {
                if (m !== menu) {
                    m.classList.remove('open');
                    const relatedTrigger = document.querySelector(`[aria-controls="${m.id}"]`) || m.previousElementSibling;
                    if (relatedTrigger) relatedTrigger.classList.remove('open');
                }
            });

            menu.classList.toggle('open');
            trigger.classList.toggle('open');
        });

        menu.addEventListener('click', (e) => {
            const item = e.target.closest('.mini-dropdown-item');
            if (!item || item.classList.contains('disabled')) return; // Ignore clicks if item is disabled

            menu.querySelectorAll('.mini-dropdown-item').forEach(el => el.classList.remove('active'));
            item.classList.add('active');

            menu.classList.remove('open');
            trigger.classList.remove('open');

            const value = item.dataset.value;
            // Update check icons
            menu.querySelectorAll('.check-icon').forEach(icon => {
                icon.style.opacity = icon.closest('.mini-dropdown-item') === item ? '1' : '0';
            });

            if (onSelect) onSelect(value, item);

            // If the user selected a new video model, recalculate supported modes
            if (menuId === 'modelDropdownMenu') {
                updateModeAvailability(value);
            }
        });
    }

    // Text model selector
    setupMiniDropdown('textModelDropdownTrigger', 'textModelDropdownMenu', (value, item) => {
        const nameEl = item.querySelector('.model-name');
        const label = document.getElementById('textModelLabel');
        if (label && nameEl) label.textContent = nameEl.textContent;
        selectedProviders['llm'] = value;
    });

    // Image model selector
    setupMiniDropdown('imageModelDropdownTrigger', 'imageModelDropdownMenu', (value, item) => {
        const nameEl = item.querySelector('.model-name');
        const label = document.getElementById('imageModelLabel');
        if (label && nameEl) label.textContent = nameEl.textContent;
        selectedProviders['image_llm'] = value;
    });

    // Video model selector
    setupMiniDropdown('modelDropdownTrigger', 'modelDropdownMenu', (value, item) => {
        const nameEl = item.querySelector('.model-name');
        const label = document.getElementById('modelLabel');
        if (label && nameEl) label.textContent = nameEl.textContent;
        selectedProviders['video_llm'] = value;
    });

    // Function to update the UI based on selected video reference mode
    function updateVideoRefModeUI(value) {
        currentVideoRefMode = value;

        // Reset uploaded files when switching modes (if called from dropdown)
        uploadedFirstFrame = null;
        uploadedLastFrame = null;
        uploadedRefImages = [];
        uploadedSampleVideo = null;
        resetUploadCards();
        resetRefImagesTimeline();

        // Show/hide upload area based on mode
        const showUpload = (value !== 'text-only');
        frameUploadArea.classList.toggle('hidden', !showUpload);

        // Show/hide individual cards
        firstFrameCard.classList.toggle('hidden', !['first-frame', 'first-last-frame'].includes(value));
        frameDivider.classList.toggle('hidden', value !== 'first-last-frame');
        lastFrameCard.classList.toggle('hidden', value !== 'first-last-frame');
        refImagesContainer.classList.toggle('hidden', value !== 'ref-style');
        sampleVideoCard.classList.toggle('hidden', value !== 'sample-video');
    }

    // Reference mode selector — switch upload UI based on selected mode
    setupMiniDropdown('refModeDropdownTrigger', 'refModeDropdownMenu', (value, item) => {
        const nameEl = item.querySelector('span:not(.model-tag)');
        document.getElementById('refModeLabel').textContent = nameEl ? nameEl.textContent : value;
        updateVideoRefModeUI(value);
    });

    function resetUploadCards() {
        [firstFrameCard, lastFrameCard, sampleVideoCard].forEach(card => {
            if (!card) return;
            const icon = card.querySelector('i');
            const span = card.querySelector('span');
            const img = card.querySelector('img');
            const video = card.querySelector('video');
            if (img) img.remove();
            if (video) video.remove();
            if (icon) icon.style.display = '';
            if (span) span.style.display = '';
            card.classList.remove('uploaded');
        });
    }

    // ── Multi-image reference timeline management ──
    function resetRefImagesTimeline() {
        uploadedRefImages = [];
        if (!refImagesTimeline) return;
        refImagesTimeline.innerHTML = '';
        addRefImageSlot(0);
    }

    function addRefImageSlot(index) {
        if (index >= 4 || !refImagesTimeline) return;

        // Description card between images (after the first image)
        if (index > 0) {
            const descCard = document.createElement('div');
            descCard.className = 'ref-desc-card';
            descCard.dataset.index = index;
            descCard.innerHTML = `
                <i class="fas fa-pen-to-square"></i>
                <input type="text" class="ref-desc-input" placeholder="描述..." data-index="${index}">
            `;
            // Stop click from propagating when typing
            descCard.querySelector('input').addEventListener('click', e => e.stopPropagation());
            refImagesTimeline.appendChild(descCard);
        }

        // Image upload card
        const card = document.createElement('div');
        card.className = 'frame-upload-card ref-upload-card';
        if (index > 0) card.classList.add('ref-optional'); // Optional slots get lighter style
        card.dataset.index = index;
        card.innerHTML = `<i class="fas fa-plus"></i><span>${index === 0 ? '图1' : '第' + (index + 1) + '帧'}</span><input type="file" accept="image/*" style="display:none">`;
        refImagesTimeline.appendChild(card);

        // Wire up upload
        const inputEl = card.querySelector('input[type="file"]');
        card.addEventListener('click', () => inputEl.click());
        inputEl.addEventListener('change', async (e) => {
            const file = e.target.files[0];
            if (!file) return;
            const icon = card.querySelector('i');
            const span = card.querySelector('span');
            if (icon) icon.className = 'fas fa-spinner fa-spin';
            if (span) span.textContent = '上传中...';

            const url = await uploadFileToServer(file);
            if (url) {
                if (icon) icon.style.display = 'none';
                if (span) span.style.display = 'none';
                const img = document.createElement('img');
                img.src = url;
                img.style.cssText = 'width:100%;height:100%;object-fit:cover;border-radius:6px;';
                card.appendChild(img);
                card.classList.add('uploaded');
                card.classList.remove('ref-optional');
                // Store ref image
                uploadedRefImages[index] = { url, description: '' };
                // Add next slot if under limit
                if (uploadedRefImages.filter(Boolean).length < 4) {
                    addRefImageSlot(uploadedRefImages.filter(Boolean).length);
                }
            } else {
                if (icon) icon.className = 'fas fa-plus';
                if (span) span.textContent = index === 0 ? '第1帧' : `第${index + 1}帧`;
            }
            inputEl.value = '';
        });
    }

    // Duration selector
    setupMiniDropdown('durationDropdownTrigger', 'durationDropdownMenu', (value, item) => {
        document.getElementById('durationLabel').textContent = value + 's';
    });

    // Ratio selector (grid-based, not mini-dropdown-item)
    const ratioTrigger = document.getElementById('ratioDropdownTrigger');
    const ratioMenu = document.getElementById('ratioDropdownMenu');
    if (ratioTrigger && ratioMenu) {
        ratioTrigger.addEventListener('click', (e) => {
            e.stopPropagation();
            const isOpen = ratioMenu.classList.contains('open');
            closeAllDropdowns();
            if (!isOpen) {
                ratioMenu.classList.add('open');
                ratioTrigger.classList.add('open');
            }
        });

        // Ratio options
        ratioMenu.querySelectorAll('.ratio-option').forEach(opt => {
            opt.addEventListener('click', (e) => {
                e.stopPropagation();
                ratioMenu.querySelectorAll('.ratio-option').forEach(o => o.classList.remove('active'));
                opt.classList.add('active');
                document.getElementById('ratioLabel').textContent = opt.dataset.ratio;
            });
        });

        // Resolution options
        ratioMenu.querySelectorAll('.resolution-option').forEach(opt => {
            opt.addEventListener('click', (e) => {
                e.stopPropagation();
                ratioMenu.querySelectorAll('.resolution-option').forEach(o => o.classList.remove('active'));
                opt.classList.add('active');
                document.getElementById('resolutionLabel').textContent = opt.dataset.res;
            });
        });
    }

    // Close ALL dropdowns when clicking outside
    function closeAllDropdowns() {
        // All mini-dropdowns
        document.querySelectorAll('.mini-dropdown-menu').forEach(m => m.classList.remove('open'));
        document.querySelectorAll('.mini-dropdown-trigger').forEach(t => t.classList.remove('open'));
    }

    document.addEventListener('click', () => {
        closeAllDropdowns();
    });

    // ── Gateway Events ────────────────────────────────────────────────
    function handleEvent(event) {
        console.log('[App] Event:', event);

        switch (event.type) {
            case 'connected':
                break;

            case 'history':
                if (event.content && Array.isArray(event.content)) {
                    store.setSessions(event.content);
                    // Refresh current view if we are on gen/assets
                    if (currentView === 'gen') renderGenTimeline();
                    if (currentView === 'assets') renderAssetsTimeline();
                }
                break;

            case 'user_message':
                renderer.removeTypingIndicator();
                renderer.addMessage('user', event.content);
                renderer.addTypingIndicator();
                break;

            case 'system':
                renderer.removeTypingIndicator();
                renderer.addMessage('system', event.content);
                renderer.addTypingIndicator();
                break;

            case 'node_start':
                renderer.removeTypingIndicator();
                renderer.addNodeProgress(event.node, 'running');
                if (event.content) renderer.addMessage('agent', event.content);
                renderer.addTypingIndicator();
                break;

            case 'node_complete':
                renderer.removeTypingIndicator();
                renderer.addNodeProgress(event.node, 'complete');
                if (event.content) renderer.addMessage('agent', event.content);
                renderer.addTypingIndicator();
                break;

            case 'pipeline_info':
                renderer.removeTypingIndicator();
                renderer.addMessage('agent', event.content);
                renderer.addTypingIndicator();
                break;

            case 'video_progress':
                renderer.removeTypingIndicator();
                renderer.addMessage('system', event.content);
                renderer.addTypingIndicator();
                break;

            case 'complete':
                renderer.removeTypingIndicator();
                if (event.content) renderer.addMessage('agent', event.content, event.params);

                // Render text result in chat
                if (event.result) {
                    renderer.addMessage('agent', event.result, event.params);
                }

                // Render media inline (images/videos)
                if (event.media_type && event.media_urls && event.media_urls.length > 0) {
                    renderer.addMediaMessage(event.media_type, event.media_urls, event.params);
                }

                // Save to session store
                const refImagesForStore = (currentVideoRefMode === 'ref-style' && uploadedRefImages.filter(Boolean).length > 0)
                    ? uploadedRefImages.filter(Boolean).map(ri => ({ url: ri.url, description: ri.description || '' }))
                    : null;
                store.add({
                    mode: event.mode || currentLlmMode,
                    input: event.input || pendingInput,
                    output: event.result || event.content || '',
                    mediaType: event.media_type || null,
                    mediaUrl: (event.media_urls && event.media_urls.length > 0) ? event.media_urls[0] : null,
                    params: event.params || null,
                    refImages: refImagesForStore,
                });

                isProcessing = false;
                updateInputState();

                if (currentView === 'gen') renderGenTimeline();
                if (currentView === 'assets' && event.media_type) renderAssetsTimeline();
                break;

            case 'error':
                renderer.removeTypingIndicator();
                renderer.addMessage('system', event.content);

                store.add({
                    mode: currentLlmMode,
                    input: pendingInput,
                    output: event.content,
                });

                isProcessing = false;
                updateInputState();
                break;
        }
    }

    function updateStatus(status) {
        // No separate badge in new UI — log only
        console.log('[App] Connection status:', status);
    }

    // ── Gateway Connection ─────────────────────────────────────────────
    const gateway = new GatewayConnection(handleEvent, updateStatus);
    gateway.connect();

    // ── Input Handling ─────────────────────────────────────────────────
    function updateInputState() {
        const hasText = chatInput.value.trim().length > 0;
        sendBtn.disabled = !hasText || isProcessing;
    }

    function sendMessage() {
        const text = chatInput.value.trim();
        if (!text || isProcessing) return;

        pendingInput = text;
        isProcessing = true;
        chatInput.value = '';
        chatInput.style.height = 'auto';
        updateInputState();

        const cfg = modeConfig[currentLlmMode];
        const wsType = cfg.wsType;
        const category = cfg.category;

        // Show user message in chat — include uploaded media if applicable
        renderer.hideWelcome();

        // Collect attachments for display
        const attachments = [];
        if (currentLlmMode === 'video-llm') {
            if (currentVideoRefMode === 'first-frame' && uploadedFirstFrame) {
                attachments.push({ url: uploadedFirstFrame, label: '首帧', type: 'image' });
            } else if (currentVideoRefMode === 'first-last-frame') {
                if (uploadedFirstFrame) attachments.push({ url: uploadedFirstFrame, label: '首帧', type: 'image' });
                if (uploadedLastFrame) attachments.push({ url: uploadedLastFrame, label: '尾帧', type: 'image' });
            } else if (currentVideoRefMode === 'ref-style' && uploadedRefImages.length > 0) {
                // Collect descriptions from text inputs
                refImagesTimeline?.querySelectorAll('.ref-desc-input').forEach(input => {
                    const idx = parseInt(input.dataset.index);
                    if (uploadedRefImages[idx]) uploadedRefImages[idx].description = input.value.trim();
                });
                uploadedRefImages.filter(Boolean).forEach((ri, i) => {
                    const desc = ri.description ? `: ${ri.description}` : '';
                    attachments.push({ url: ri.url, label: `参考图${i + 1}${desc}`, type: 'image' });
                });
            } else if (currentVideoRefMode === 'sample-video' && uploadedSampleVideo) {
                attachments.push({ url: uploadedSampleVideo, label: '样片', type: 'video' });
            }
        }

        if (attachments.length > 0) {
            renderer.addUserMessageWithMedia(text, attachments);
        } else {
            renderer.addMessage('user', text);
        }
        renderer.addTypingIndicator();

        // Get selected provider ID for current mode
        const providerId = selectedProviders[category] || '';

        // Build payload — for video mode, include all parameters
        const payload = { text, provider_id: providerId };

        if (currentLlmMode === 'video-llm') {
            payload.ratio = document.getElementById('ratioLabel')?.textContent || '16:9';
            payload.resolution = document.getElementById('resolutionLabel')?.textContent?.toLowerCase() || '720p';
            payload.duration = parseInt(document.getElementById('durationLabel')?.textContent) || 5;
            payload.seed = parseInt(document.getElementById('seedInput')?.value) || -1;
            payload.camera_fixed = document.getElementById('cameraFixedToggle')?.checked || false;
            payload.watermark = document.getElementById('watermarkToggle')?.checked ?? true;

            // Attach uploaded media URLs based on reference mode
            if (currentVideoRefMode === 'first-frame' && uploadedFirstFrame) {
                payload.first_frame_image = uploadedFirstFrame;
            } else if (currentVideoRefMode === 'first-last-frame') {
                if (uploadedFirstFrame) payload.first_frame_image = uploadedFirstFrame;
                if (uploadedLastFrame) payload.last_frame_image = uploadedLastFrame;
            } else if (currentVideoRefMode === 'ref-style' && uploadedRefImages.filter(Boolean).length > 0) {
                payload.ref_style_images = uploadedRefImages.filter(Boolean).map(ri => ({
                    url: ri.url,
                    description: ri.description || ''
                }));
            } else if (currentVideoRefMode === 'sample-video' && uploadedSampleVideo) {
                payload.sample_video = uploadedSampleVideo;
            }
        }

        // Send to backend with mode-specific type
        gateway.send(wsType, JSON.stringify(payload));

        // Reset uploaded media state after sending
        if (currentLlmMode === 'video-llm' && attachments.length > 0) {
            uploadedFirstFrame = null;
            uploadedLastFrame = null;
            uploadedRefImages = [];
            uploadedSampleVideo = null;
            resetUploadCards();
            resetRefImagesTimeline();
        }
    }

    chatInput.addEventListener('input', () => {
        updateInputState();
        chatInput.style.height = 'auto';
        chatInput.style.height = Math.min(chatInput.scrollHeight, 120) + 'px';
    });

    chatInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });

    sendBtn.addEventListener('click', sendMessage);

    // ── Generate Page: Timeline Rendering ──────────────────────────────
    function renderGenTimeline() {
        const sortOrder = genSortSelect?.value || 'desc';
        const searchQuery = genSearchInput?.value.trim().toLowerCase() || '';
        let sessions = store.getAll(sortOrder);

        if (searchQuery) {
            sessions = sessions.filter(s =>
                s.input.toLowerCase().includes(searchQuery) ||
                s.output.toLowerCase().includes(searchQuery)
            );
        }

        genTimeline.innerHTML = '';

        if (sessions.length === 0) {
            genEmptyState.classList.remove('hidden-state');
            return;
        }
        genEmptyState.classList.add('hidden-state');

        sessions.forEach(session => {
            const item = document.createElement('div');
            item.className = 'timeline-item';

            const timeStr = session.timestamp.toLocaleString('zh-CN', {
                month: 'numeric',
                day: 'numeric',
                hour: '2-digit',
                minute: '2-digit',
            });

            const modeLabelText = modeConfig[session.mode]?.label || session.mode;

            // Build media HTML if available
            let mediaHTML = '';
            if (session.mediaUrl) {
                const safeMediaUrl = escapeHtml(session.mediaUrl);
                if (session.mediaType === 'image') {
                    mediaHTML = `<div class="timeline-card-media"><img src="${safeMediaUrl}" alt="output" onerror="this.outerHTML='<div class=\\'expired-media\\'>图片已过期</div>'"></div>`;
                } else if (session.mediaType === 'video') {
                    mediaHTML = `<div class="timeline-card-media"><video src="${safeMediaUrl}" controls onerror="this.outerHTML='<div class=\\'expired-media\\'>视频已过期</div>'"></video></div>`;
                }
            }

            // Build reference images thumbnail row for Generate page
            let refImagesHTML = '';
            if (session.refImages && session.refImages.length > 0) {
                refImagesHTML = '<div class="timeline-ref-images">';
                session.refImages.forEach((ri, i) => {
                    const url = typeof ri === 'string' ? ri : ri.url;
                    const desc = (typeof ri === 'object' && ri.description) ? ri.description : '';
                    refImagesHTML += `<div class="timeline-ref-item"><img src="${escapeHtml(url)}" alt="参考图${i + 1}" class="timeline-ref-thumb">`;
                    if (desc) refImagesHTML += `<span class="timeline-ref-desc">${escapeHtml(desc)}</span>`;
                    refImagesHTML += `</div>`;
                });
                refImagesHTML += '</div>';
            }

            // Build params HTML
            let paramsHTML = '';
            if (session.params && Object.keys(session.params).length > 0) {
                paramsHTML = '<div class="timeline-card-params">';
                for (const [key, val] of Object.entries(session.params)) {
                    const labels = {
                        model: '模型',
                        ratio: '比例',
                        resolution: '分辨率',
                        duration: '时长',
                        seed: '种子',
                        camera_fixed: '锁定机位'
                    };
                    const label = labels[key] || key;
                    paramsHTML += `<span class="param-tag">${label}: ${val}</span>`;
                }
                paramsHTML += '</div>';
            }

            item.innerHTML = `
                <div class="timeline-time">
                    ${timeStr}
                    <span class="mode-badge">${modeLabelText}</span>
                </div>
                <div class="timeline-card">
                    <div class="timeline-card-section">
                        <div class="timeline-card-label">输入</div>
                        <div class="timeline-card-text">${escapeHtml(session.input)}</div>
                        ${refImagesHTML}
                    </div>
                    ${paramsHTML}
                    <div class="timeline-card-section">
                        <div class="timeline-card-label">输出</div>
                        <div class="timeline-card-text">${escapeHtml(session.output)}</div>
                        ${mediaHTML}
                    </div>
                    <div class="timeline-card-actions">
                        <button class="timeline-action-btn" onclick="navigator.clipboard.writeText('${escapeHtml(session.input).replace(/'/g, "\\''")}')">
                            <i class="fas fa-copy"></i> 复制输入
                        </button>
                        ${session.mediaUrl ? `<button class="timeline-action-btn" onclick="downloadMedia('${escapeHtml(session.mediaUrl)}')"><i class="fas fa-download"></i> 下载${session.mediaType === 'video' ? '视频' : '图片'}</button>` : ''}
                    </div>
                </div>
            `;

            genTimeline.appendChild(item);
        });
    }

    // Listeners for gen page
    if (genSearchInput) genSearchInput.addEventListener('input', renderGenTimeline);
    if (genSortSelect) genSortSelect.addEventListener('change', renderGenTimeline);

    // ── Assets Page: Grid Rendering ───────────────────────────────────
    function renderAssetsTimeline() {
        const assets = store.getAssets(currentAssetFilter);

        assetsTimeline.innerHTML = '';

        if (assets.length === 0) {
            assetsEmptyState.classList.remove('hidden-state');
            return;
        }
        assetsEmptyState.classList.add('hidden-state');

        // Group by date
        const groups = {};
        assets.forEach(a => {
            const dateKey = a.timestamp.toLocaleDateString('zh-CN', {
                month: 'long',
                day: 'numeric',
            });
            if (!groups[dateKey]) groups[dateKey] = [];
            groups[dateKey].push(a);
        });

        // Render groups (newest first)
        const sortedKeys = Object.keys(groups).reverse();
        sortedKeys.forEach(dateKey => {
            const group = document.createElement('div');
            group.className = 'asset-date-group';
            group.innerHTML = `<h3>${dateKey}</h3>`;

            const grid = document.createElement('div');
            grid.className = 'asset-grid';

            groups[dateKey].forEach(asset => {
                const card = document.createElement('div');
                card.className = 'asset-card';

                const safeAssetUrl = escapeHtml(asset.mediaUrl);
                if (asset.mediaType === 'image') {
                    card.innerHTML = `
                        <img src="${safeAssetUrl}" alt="asset" onerror="this.outerHTML='<div class=\\'expired-media\\'>已失效</div>'">
                        <div class="asset-card-overlay">
                            <span>${escapeHtml(asset.input.substring(0, 40))}</span>
                            <button class="asset-download-btn" onclick="event.stopPropagation(); downloadMedia('${safeAssetUrl}')" title="下载图片"><i class="fas fa-download"></i></button>
                        </div>
                    `;
                } else if (asset.mediaType === 'video') {
                    card.innerHTML = `
                        <video src="${safeAssetUrl}" muted onerror="this.outerHTML='<div class=\\'expired-media\\'>已失效</div>'"></video>
                        <div class="play-icon"><i class="fas fa-play"></i></div>
                        <div class="asset-card-overlay">
                            <span>${escapeHtml(asset.input.substring(0, 40))}</span>
                            <button class="asset-download-btn" onclick="event.stopPropagation(); downloadMedia('${safeAssetUrl}')" title="下载视频"><i class="fas fa-download"></i></button>
                        </div>
                    `;
                    card.addEventListener('click', (e) => {
                        if (e.target.closest('.asset-download-btn')) return;
                        const video = card.querySelector('video');
                        if (video.paused) video.play(); else video.pause();
                    });
                }

                grid.appendChild(card);
            });

            group.appendChild(grid);
            assetsTimeline.appendChild(group);
        });
    }

    // Filter tabs
    filterTabs.forEach(tab => {
        tab.addEventListener('click', () => {
            filterTabs.forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
            currentAssetFilter = tab.dataset.filter;
            renderAssetsTimeline();
        });
    });

    // ── Utility ────────────────────────────────────────────────────────
    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    // ── Download Media ────────────────────────────────────────────────
    // Exposed globally so inline onclick handlers can call it
    window.downloadMedia = async function(url) {
        try {
            const resp = await fetch(url);
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
            const blob = await resp.blob();
            const a = document.createElement('a');
            a.href = URL.createObjectURL(blob);
            // Extract filename from URL path
            a.download = url.split('/').pop() || 'download';
            document.body.appendChild(a);
            a.click();
            setTimeout(() => {
                URL.revokeObjectURL(a.href);
                a.remove();
            }, 100);
        } catch (e) {
            console.error('[Download] Error:', e);
            alert('下载失败: ' + e.message);
        }
    };

    // ── File Upload Handling ─────────────────────────────────────────────
    async function uploadFileToServer(file) {
        const formData = new FormData();
        formData.append('file', file);
        try {
            const resp = await fetch('/api/upload_frame', { method: 'POST', body: formData });
            if (!resp.ok) throw new Error(`Upload failed: HTTP ${resp.status}`);
            const data = await resp.json();
            return data.url; // e.g. "/outputs/uploads/upload_xxx.png"
        } catch (e) {
            console.error('[Upload] Error:', e);
            renderer.addMessage('system', `文件上传失败: ${e.message}`);
            return null;
        }
    }

    function setupCardUpload(card, inputEl, isVideo, onSuccess) {
        if (!card || !inputEl) return;
        card.addEventListener('click', () => inputEl.click());
        inputEl.addEventListener('change', async (e) => {
            const file = e.target.files[0];
            if (!file) return;

            // Show loading state
            const icon = card.querySelector('i');
            const span = card.querySelector('span');
            if (icon) icon.className = 'fas fa-spinner fa-spin';
            if (span) span.textContent = '上传中...';

            const url = await uploadFileToServer(file);
            if (url) {
                // Show preview
                if (icon) icon.style.display = 'none';
                if (span) span.style.display = 'none';

                if (isVideo) {
                    const vid = document.createElement('video');
                    vid.src = url;
                    vid.muted = true;
                    vid.style.cssText = 'width:100%;height:100%;object-fit:cover;border-radius:6px;';
                    card.appendChild(vid);
                } else {
                    const img = document.createElement('img');
                    img.src = url;
                    img.style.cssText = 'width:100%;height:100%;object-fit:cover;border-radius:6px;';
                    card.appendChild(img);
                }
                card.classList.add('uploaded');
                onSuccess(url);
            } else {
                // Reset on failure
                if (icon) icon.className = 'fas fa-plus';
                if (span) span.textContent = isVideo ? '样片视频' : card.id.includes('last') ? '尾帧' : card.id.includes('ref') ? '参考图' : '首帧';
            }
            inputEl.value = ''; // allow re-upload
        });
    }

    setupCardUpload(firstFrameCard, document.getElementById('firstFrameInput'), false, (url) => { uploadedFirstFrame = url; });
    setupCardUpload(lastFrameCard, document.getElementById('lastFrameInput'), false, (url) => { uploadedLastFrame = url; });
    setupCardUpload(sampleVideoCard, document.getElementById('sampleVideoInput'), true, (url) => { uploadedSampleVideo = url; });

    // Initialize ref images timeline
    resetRefImagesTimeline();

    // ── Lightbox Logic ───────────────────────────────────────────────
    const lightboxModal = document.getElementById('lightboxModal');
    const lightboxImg = document.getElementById('lightboxImg');
    const lightboxClose = lightboxModal?.querySelector('.lightbox-close');

    document.addEventListener('click', (e) => {
        let target = e.target;

        // Find if we clicked an image or a container that has an image
        const imgContainer = target.closest('.message-content, .timeline-card-media, .asset-card');
        if (!imgContainer) return;

        const img = imgContainer.querySelector('img');
        if (img && lightboxModal && lightboxImg) {
            lightboxImg.src = img.src;
            lightboxModal.classList.add('open');
        }
    });

    const closeLightbox = () => {
        if (lightboxModal) {
            lightboxModal.classList.remove('open');
            setTimeout(() => {
                if (lightboxImg) lightboxImg.src = '';
            }, 400); // match transition duration
        }
    };

    lightboxClose?.addEventListener('click', closeLightbox);
    lightboxModal?.addEventListener('click', (e) => {
        if (e.target === lightboxModal) closeLightbox();
    });

    // ── Initial Setup ──────────────────────────────────────────────────
    // Show text controls by default (llm mode is default)
    setLlmMode('llm');

    // Fetch providers from backend
    fetchProviders();
});
