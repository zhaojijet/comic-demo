/**
 * Comic Demo — Chat UI (WebSocket Client)
 * Inspired by openclaw's Gateway WebSocket pattern.
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
        this.onStatusChange('connecting');

        try {
            this.ws = new WebSocket(url);
        } catch (e) {
            this.onStatusChange('disconnected');
            this.scheduleReconnect();
            return;
        }

        this.ws.onopen = () => {
            this.reconnectAttempts = 0;
            this.onStatusChange('connected');
            this.startHeartbeat();
        };

        this.ws.onmessage = (e) => {
            try {
                const event = JSON.parse(e.data);
                if (event.type === 'connected') {
                    this.sessionId = event.session_id;
                }
                if (event.type !== 'pong') {
                    this.onEvent(event);
                }
            } catch (err) {
                console.error('[Gateway] Parse error:', err);
            }
        };

        this.ws.onclose = () => {
            this.stopHeartbeat();
            this.onStatusChange('disconnected');
            this.scheduleReconnect();
        };

        this.ws.onerror = () => {
            this.onStatusChange('disconnected');
        };
    }

    send(type, content) {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify({ type, content }));
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
    constructor(container, welcomeScreen) {
        this.container = container;
        this.welcomeScreen = welcomeScreen;
    }

    hideWelcome() {
        if (this.welcomeScreen) {
            this.welcomeScreen.style.display = 'none';
        }
    }

    addMessage(type, content, extra) {
        this.hideWelcome();
        const msg = document.createElement('div');
        msg.className = `message ${type}`;

        const avatarIcon = type === 'user' ? 'fa-user'
            : type === 'system' ? 'fa-info-circle'
                : 'fa-robot';

        const time = new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });

        msg.innerHTML = `
            <div class="message-avatar"><i class="fas ${avatarIcon}"></i></div>
            <div class="message-body">
                <div class="message-content">${this.escapeHtml(content)}</div>
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
        if (this.welcomeScreen) {
            this.welcomeScreen.style.display = '';
        }
    }

    scrollToBottom() {
        requestAnimationFrame(() => {
            this.container.scrollTop = this.container.scrollHeight;
        });
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
}

// ── App Initialization ─────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    const chatContainer = document.getElementById('chatContainer');
    const welcomeScreen = document.getElementById('welcomeScreen');
    const chatInput = document.getElementById('chatInput');
    const sendBtn = document.getElementById('sendBtn');
    const connectionBadge = document.getElementById('connectionBadge');
    const newChatBtn = document.getElementById('newChatBtn');

    const renderer = new ChatRenderer(chatContainer, welcomeScreen);
    let isProcessing = false;

    // ── Status Badge ───────────────────────────────────────────────────
    function updateStatus(status) {
        const dot = connectionBadge.querySelector('.status-dot');
        const text = connectionBadge.querySelector('.status-text');
        connectionBadge.classList.remove('connected');

        if (status === 'connected') {
            connectionBadge.classList.add('connected');
            text.textContent = '已连接';
        } else if (status === 'connecting') {
            text.textContent = '连接中...';
        } else {
            text.textContent = '未连接';
        }
    }

    // ── Event Handler ──────────────────────────────────────────────────
    function handleEvent(event) {
        switch (event.type) {
            case 'connected':
                console.log("[Gateway] connected: ", event.content);
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
                if (event.content) {
                    renderer.addMessage('agent', event.content);
                }
                renderer.addTypingIndicator();
                break;

            case 'node_complete':
                renderer.removeTypingIndicator();
                renderer.addNodeProgress(event.node, 'complete');
                if (event.content) {
                    renderer.addMessage('agent', event.content);
                }
                renderer.addTypingIndicator();
                break;

            case 'pipeline_info':
                renderer.removeTypingIndicator();
                renderer.addMessage('agent', event.content);
                renderer.addTypingIndicator();
                break;

            case 'complete':
                renderer.removeTypingIndicator();
                renderer.addMessage('agent', event.content);
                if (event.result) {
                    renderer.addMessage('agent', event.result);
                }
                isProcessing = false;
                updateInputState();
                break;

            case 'error':
                renderer.removeTypingIndicator();
                renderer.addMessage('system', event.content);
                isProcessing = false;
                updateInputState();
                break;
        }
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

        isProcessing = true;
        chatInput.value = '';
        chatInput.style.height = 'auto';
        updateInputState();
        gateway.send('chat', text);
    }

    chatInput.addEventListener('input', () => {
        updateInputState();
        // Auto-resize textarea
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

    // ── New Chat ───────────────────────────────────────────────────────
    newChatBtn.addEventListener('click', () => {
        renderer.clearMessages();
        isProcessing = false;
        updateInputState();
        // Reconnect for a fresh session
        gateway.disconnect();
        gateway.connect();
    });

    // ── Quick Action Buttons ───────────────────────────────────────────
    document.querySelectorAll('.quick-action-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const prompt = btn.dataset.prompt;
            if (prompt) {
                chatInput.value = prompt;
                updateInputState();
                chatInput.focus();
            }
        });
    });

    // ── Test Action Buttons ────────────────────────────────────────────
    document.querySelectorAll('.test-action-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const testType = btn.dataset.test;
            if (testType && !isProcessing) {
                isProcessing = true;
                updateInputState();
                gateway.send(testType, "");
            }
        });
    });

    // ── Sidebar Navigation ─────────────────────────────────────────────
    document.querySelectorAll('.nav-item').forEach(item => {
        item.addEventListener('click', () => {
            document.querySelectorAll('.nav-item').forEach(i => i.classList.remove('active'));
            item.classList.add('active');
        });
    });
});
