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

    addMessage(type, content) {
        this.hideWelcome();
        const msg = document.createElement('div');
        msg.className = `message ${type}`;

        const avatarIcon = type === 'user' ? 'fa-user'
            : type === 'system' ? 'fa-info-circle'
                : 'fa-robot';

        const time = new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });

        // Media rendering
        let renderedContent = this.escapeHtml(content);

        msg.innerHTML = `
            <div class="message-avatar"><i class="fas ${avatarIcon}"></i></div>
            <div class="message-body">
                <div class="message-content">${renderedContent}</div>
                <div class="message-time">${time}</div>
            </div>
        `;

        this.container.appendChild(msg);
        this.scrollToBottom();
        return msg;
    }

    addMediaMessage(mediaType, urls) {
        this.hideWelcome();
        const msg = document.createElement('div');
        msg.className = 'message agent';

        const time = new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });

        let mediaHTML = '';
        for (const url of urls) {
            if (mediaType === 'image') {
                mediaHTML += `<div class="media-content"><img src="${this.escapeHtml(url)}" alt="Generated Image" loading="lazy" onerror="this.parentElement.innerHTML='<p>图片加载失败</p>'"></div>`;
            } else if (mediaType === 'video') {
                mediaHTML += `<div class="media-content"><video src="${this.escapeHtml(url)}" controls preload="metadata" onerror="this.parentElement.innerHTML='<p>视频加载失败</p>'"></video></div>`;
            }
        }

        msg.innerHTML = `
            <div class="message-avatar"><i class="fas fa-robot"></i></div>
            <div class="message-body">
                <div class="message-content">${mediaHTML}</div>
                <div class="message-time">${time}</div>
            </div>
        `;

        this.container.appendChild(msg);
        this.scrollToBottom();
        return msg;
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

    // LLM mode dropdown elements
    const modeDropdownTrigger = document.getElementById('modeDropdownTrigger');
    const modeDropdownMenu = document.getElementById('modeDropdownMenu');
    const modeDropdownItems = document.querySelectorAll('.mode-dropdown-item');
    const modeLabel = document.getElementById('modeLabel');
    const modeIcon = document.getElementById('modeIcon');

    // Mode-specific control containers
    const textControls = document.getElementById('textControls');
    const imageControls = document.getElementById('imageControls');
    const videoControls = document.getElementById('videoControls');
    const frameUploadArea = document.getElementById('frameUploadArea');

    // State
    let currentView = 'home';
    let currentLlmMode = 'llm';
    let currentAssetFilter = 'all';
    let isProcessing = false;
    let pendingInput = '';

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
            item.innerHTML = `
                <span class="model-name">${escapeHtml(p.display_name)}</span>
                ${p.description ? `<span class="model-desc">${escapeHtml(p.description)}</span>` : ''}
                <i class="fas fa-check check-icon"></i>
            `;
            menu.appendChild(item);
        });

        // Set default selection
        if (defaultId) {
            selectedProviders[category] = defaultId;
            const defaultProvider = providers.find(p => p.id === defaultId);
            if (defaultProvider) {
                if (label) label.textContent = defaultProvider.display_name;
            }
        } else if (providers.length > 0) {
            selectedProviders[category] = providers[0].id;
            if (label) label.textContent = providers[0].display_name;
            if (modeModelLabel) modeModelLabel.textContent = providers[0].display_name;
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
        modeLabel.textContent = cfg.label;
        modeIcon.className = cfg.icon;
        chatInput.placeholder = cfg.placeholder;

        // Update active state in dropdown items
        modeDropdownItems.forEach(item => {
            item.classList.toggle('active', item.dataset.mode === mode);
        });

        // Show/hide mode-specific controls
        const isText = (mode === 'llm');
        const isImage = (mode === 'image-llm');
        const isVideo = (mode === 'video-llm');

        textControls.classList.toggle('hidden', !isText);
        imageControls.classList.toggle('hidden', !isImage);
        videoControls.classList.toggle('hidden', !isVideo);
        frameUploadArea.classList.toggle('hidden', !isVideo);

        // Close dropdown
        closeAllDropdowns();
        chatInput.focus();
    }

    function toggleDropdown() {
        const isOpen = modeDropdownMenu.classList.contains('open');
        closeAllDropdowns();
        if (!isOpen) {
            modeDropdownMenu.classList.add('open');
            modeDropdownTrigger.classList.add('open');
        }
    }

    function closeDropdown() {
        modeDropdownMenu.classList.remove('open');
        modeDropdownTrigger.classList.remove('open');
    }

    modeDropdownTrigger.addEventListener('click', (e) => {
        e.stopPropagation();
        toggleDropdown();
    });

    modeDropdownItems.forEach(item => {
        item.addEventListener('click', (e) => {
            e.stopPropagation();
            setLlmMode(item.dataset.mode);
        });
    });

    // ── Mini Dropdowns — Generic System ────────────────────────────────
    function setupMiniDropdown(triggerId, menuId, onSelect) {
        const trigger = document.getElementById(triggerId);
        const menu = document.getElementById(menuId);
        if (!trigger || !menu) return;

        trigger.addEventListener('click', (e) => {
            e.stopPropagation();
            const isOpen = menu.classList.contains('open');
            closeAllDropdowns();
            if (!isOpen) {
                menu.classList.add('open');
                trigger.classList.add('open');
            }
        });

        // Use event delegation for dynamically created items
        menu.addEventListener('click', (e) => {
            const item = e.target.closest('.mini-dropdown-item');
            if (!item) return;
            e.stopPropagation();

            // Update active state
            menu.querySelectorAll('.mini-dropdown-item').forEach(i => i.classList.remove('active'));
            item.classList.add('active');
            // Reset check icons
            menu.querySelectorAll('.check-icon').forEach(c => c.style.opacity = '0');
            const checkIcon = item.querySelector('.check-icon');
            if (checkIcon) checkIcon.style.opacity = '1';
            // Callback
            if (onSelect) onSelect(item.dataset.value, item);
            closeAllDropdowns();
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

    // Reference mode selector
    setupMiniDropdown('refModeDropdownTrigger', 'refModeDropdownMenu', (value, item) => {
        const nameEl = item.querySelector('span:not(.model-tag)');
        document.getElementById('refModeLabel').textContent = nameEl ? nameEl.textContent : value;
    });

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
        // Main mode dropdown
        closeDropdown();
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

            case 'complete':
                renderer.removeTypingIndicator();
                if (event.content) renderer.addMessage('agent', event.content);

                // Render text result in chat
                if (event.result) {
                    renderer.addMessage('agent', event.result);
                }

                // Render media inline (images/videos)
                if (event.media_type && event.media_urls && event.media_urls.length > 0) {
                    renderer.addMediaMessage(event.media_type, event.media_urls);
                }

                // Save to session store
                store.add({
                    mode: event.mode || currentLlmMode, // Use event mode if available (from history)
                    input: event.input || pendingInput,
                    output: event.result || event.content || '',
                    mediaType: event.media_type || null,
                    mediaUrl: (event.media_urls && event.media_urls.length > 0) ? event.media_urls[0] : null,
                });

                isProcessing = false;
                updateInputState();

                // If on Generation page, refresh timeline to show the new item
                if (currentView === 'gen') renderGenTimeline();
                if (currentView === 'assets' && event.media_type) renderAssetsTimeline();
                break;

            case 'error':
                renderer.removeTypingIndicator();
                renderer.addMessage('system', event.content);

                // Also save error sessions
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

        // Show user message in chat
        renderer.hideWelcome();
        renderer.addMessage('user', text);
        renderer.addTypingIndicator();

        // Get selected provider ID for current mode
        const providerId = selectedProviders[category] || '';

        // Send to backend with mode-specific type and provider_id
        gateway.send(wsType, JSON.stringify({ text, provider_id: providerId }));
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
                if (session.mediaType === 'image') {
                    mediaHTML = `<div class="timeline-card-media"><img src="${escapeHtml(session.mediaUrl)}" alt="output" onerror="this.outerHTML='<div class=\\'expired-media\\'>图片已过期</div>'"></div>`;
                } else if (session.mediaType === 'video') {
                    mediaHTML = `<div class="timeline-card-media"><video src="${escapeHtml(session.mediaUrl)}" controls onerror="this.outerHTML='<div class=\\'expired-media\\'>视频已过期</div>'"></video></div>`;
                }
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
                    </div>
                    <hr class="timeline-card-divider">
                    <div class="timeline-card-section">
                        <div class="timeline-card-label">输出</div>
                        <div class="timeline-card-text">${escapeHtml(session.output)}</div>
                        ${mediaHTML}
                    </div>
                    <div class="timeline-card-actions">
                        <button class="timeline-action-btn" onclick="navigator.clipboard.writeText('${escapeHtml(session.input).replace(/'/g, "\\''")}')">
                            <i class="fas fa-copy"></i> 复制输入
                        </button>
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

                if (asset.mediaType === 'image') {
                    card.innerHTML = `
                        <img src="${escapeHtml(asset.mediaUrl)}" alt="asset" onerror="this.outerHTML='<div class=\\'expired-media\\'>已失效</div>'">
                        <div class="asset-card-overlay">${escapeHtml(asset.input.substring(0, 40))}</div>
                    `;
                } else if (asset.mediaType === 'video') {
                    card.innerHTML = `
                        <video src="${escapeHtml(asset.mediaUrl)}" muted onerror="this.outerHTML='<div class=\\'expired-media\\'>已失效</div>'"></video>
                        <div class="play-icon"><i class="fas fa-play"></i></div>
                        <div class="asset-card-overlay">${escapeHtml(asset.input.substring(0, 40))}</div>
                    `;
                    card.addEventListener('click', () => {
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

    // ── Initial Setup ──────────────────────────────────────────────────
    // Show text controls by default (llm mode is default)
    setLlmMode('llm');

    // Fetch providers from backend
    fetchProviders();
});
