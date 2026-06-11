<template>
  <div class="app">
    <!-- ── Header ── -->
    <header class="header">
      <div class="header-brand">
        <span class="brand-logo">AMBRIO</span>
        <span class="brand-tagline">MULTI-AGENT AI</span>
      </div>

      <div class="header-status">
        <span class="status-dot" :class="statusClass" aria-label="connection status"></span>
        <span class="status-label">{{ statusLabel }}</span>
      </div>

      <div class="header-session">
        <svg class="session-icon" viewBox="0 0 16 16" width="12" height="12" fill="none" stroke="currentColor" stroke-width="1.5">
          <rect x="1" y="3" width="14" height="10" rx="1.5"/>
          <path d="M4 7h8M4 10h5"/>
        </svg>
        <span class="session-id">{{ shortSessionId }}</span>
      </div>
    </header>

    <!-- ── Messages ── -->
    <main class="messages" ref="messagesEl">
      <!-- Empty state -->
      <div v-if="messages.length === 0" class="empty-state">
        <div class="empty-logo">
          <div class="logo-ring"></div>
          <span class="logo-text">AMBRIO</span>
        </div>
        <p class="empty-subtitle">Autonomous Multi-Agent Intelligence</p>
        <div class="suggestions">
          <button
            v-for="chip in suggestions"
            :key="chip"
            class="suggestion-chip"
            @click="sendSuggestion(chip)"
          >
            {{ chip }}
          </button>
        </div>
      </div>

      <!-- Message list -->
      <div
        v-for="(msg, idx) in messages"
        :key="idx"
        class="message-wrapper"
        :class="msg.role"
      >
        <div class="message-bubble" :class="msg.role">
          <!-- Role badge -->
          <div class="message-role">
            <template v-if="msg.role === 'user'">
              <svg viewBox="0 0 16 16" width="12" height="12" fill="currentColor">
                <circle cx="8" cy="5" r="3"/>
                <path d="M2 14c0-3.314 2.686-6 6-6s6 2.686 6 6"/>
              </svg>
              YOU
            </template>
            <template v-else-if="msg.role === 'assistant'">
              <svg viewBox="0 0 16 16" width="12" height="12" fill="none" stroke="currentColor" stroke-width="1.5">
                <rect x="2" y="4" width="12" height="9" rx="2"/>
                <path d="M5 4V3a3 3 0 016 0v1M6 9h.01M10 9h.01"/>
              </svg>
              AMBRIO
            </template>
            <template v-else>
              <svg viewBox="0 0 16 16" width="12" height="12" fill="currentColor">
                <path d="M8 1a7 7 0 100 14A7 7 0 008 1zm0 3a1 1 0 011 1v3a1 1 0 11-2 0V5a1 1 0 011-1zm0 8a1 1 0 110-2 1 1 0 010 2z"/>
              </svg>
              ERROR
            </template>
          </div>

          <!-- Content -->
          <div
            class="message-content"
            v-if="msg.role === 'assistant'"
            v-html="renderMarkdown(msg.content)"
          ></div>
          <div class="message-content" v-else>{{ msg.content }}</div>

          <!-- Typing cursor (streaming) -->
          <span
            v-if="msg.role === 'assistant' && isLoading && idx === messages.length - 1"
            class="typing-cursor"
            aria-hidden="true"
          >▋</span>

          <!-- Meta info -->
          <div v-if="msg.meta" class="message-meta">
            <span>{{ msg.meta.model }}</span>
            <span class="meta-dot">•</span>
            <span>{{ msg.meta.elapsed?.toFixed(1) }}s</span>
            <span class="meta-dot">•</span>
            <span>{{ msg.meta.tokens?.toLocaleString() }} tokens</span>
          </div>
        </div>
      </div>
    </main>

    <!-- ── Input ── -->
    <footer class="input-area">
      <div class="input-wrapper" :class="{ focused: inputFocused, loading: isLoading }">
        <textarea
          ref="inputEl"
          v-model="inputText"
          class="input-field"
          placeholder="Ask Ambrio anything..."
          rows="1"
          :disabled="isLoading"
          @keydown.enter.exact.prevent="handleSend"
          @focus="inputFocused = true"
          @blur="inputFocused = false"
          @input="autoResize"
          aria-label="Message input"
        ></textarea>

        <button
          class="send-btn"
          :disabled="isLoading || !inputText.trim()"
          @click="handleSend"
          aria-label="Send message"
        >
          <!-- Spinner while loading -->
          <svg v-if="isLoading" class="spin" viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="12" cy="12" r="10" stroke-opacity="0.3"/>
            <path d="M12 2a10 10 0 0110 10"/>
          </svg>
          <!-- Arrow when idle -->
          <svg v-else viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
            <line x1="22" y1="2" x2="11" y2="13"/>
            <polygon points="22 2 15 22 11 13 2 9 22 2"/>
          </svg>
        </button>
      </div>
      <p class="input-hint">Enter to send · Shift+Enter for newline</p>
    </footer>
  </div>
</template>

<script setup>
import { ref, computed, nextTick, watch } from 'vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import { useWebSocket } from './composables/useWebSocket.js'

// Session — persisted across page reloads (I3)
const SESSION_KEY = 'ambrio_session_id'
const sessionId = localStorage.getItem(SESSION_KEY) ?? (() => {
  const id = crypto.randomUUID()
  localStorage.setItem(SESSION_KEY, id)
  return id
})()
const shortSessionId = computed(() => sessionId.slice(0, 8).toUpperCase())

// WebSocket
const { messages, isLoading, status, send } = useWebSocket(sessionId)

// Status
const statusClass = computed(() => ({
  'status-connected':    status.value === 'connected',
  'status-disconnected': status.value === 'disconnected',
  'status-error':        status.value === 'error',
}))
const statusLabel = computed(() => ({
  connected:    'CONNECTED',
  disconnected: 'OFFLINE',
  error:        'ERROR',
}[status.value] ?? 'OFFLINE'))

// Input
const inputText   = ref('')
const inputFocused = ref(false)
const inputEl     = ref(null)
const messagesEl  = ref(null)

// Suggestions
const suggestions = [
  'What agents are available?',
  'Search the web for recent AI news',
  'Summarize my recent tasks',
  'Analyze the codebase structure',
]

// Markdown renderer — C2: async:false, C1: DOMPurify sanitization
marked.setOptions({ breaks: true, gfm: true, async: false })
function renderMarkdown(text) {
  if (!text) return ''
  return DOMPurify.sanitize(/** @type {string} */ (marked.parse(text)))
}

function handleSend() {
  const text = inputText.value.trim()
  if (!text || isLoading.value) return
  send(text)
  inputText.value = ''
  nextTick(() => {
    if (inputEl.value) {
      inputEl.value.style.height = 'auto'
    }
  })
}



function sendSuggestion(chip) {
  if (isLoading.value) return
  send(chip)
}

function autoResize() {
  const el = inputEl.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = Math.min(el.scrollHeight, 160) + 'px'
}

// Auto-scroll — only if user is near the bottom (I5)
watch(
  messages,
  async () => {
    await nextTick()
    const el = messagesEl.value
    if (!el) return
    const threshold = 100  // px from bottom
    const isNearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < threshold
    if (isNearBottom) el.scrollTop = el.scrollHeight
  },
  { deep: true }
)
</script>

<style scoped>
/* ── Layout ── */
.app {
  display: flex;
  flex-direction: column;
  height: 100vh;
  max-width: 900px;
  margin: 0 auto;
  position: relative;
}

/* ── Header ── */
.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 20px;
  background: rgba(13, 17, 23, 0.95);
  border-bottom: 1px solid var(--border);
  backdrop-filter: blur(8px);
  position: sticky;
  top: 0;
  z-index: 100;
  gap: 12px;
}

.header-brand {
  display: flex;
  flex-direction: column;
  line-height: 1;
}

.brand-logo {
  font-family: 'Orbitron', monospace;
  font-size: 1.25rem;
  font-weight: 700;
  color: var(--green);
  text-shadow: 0 0 12px rgba(0, 255, 65, 0.6), 0 0 30px rgba(0, 255, 65, 0.3);
  letter-spacing: 0.15em;
}

.brand-tagline {
  font-size: 0.55rem;
  color: var(--text-muted);
  letter-spacing: 0.2em;
  margin-top: 2px;
  font-family: 'Exo 2', sans-serif;
}

.header-status {
  display: flex;
  align-items: center;
  gap: 8px;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 20px;
  padding: 5px 14px;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.status-connected {
  background: var(--green);
  box-shadow: 0 0 8px var(--green);
  animation: blink 2s ease-in-out infinite;
}

.status-disconnected { background: var(--text-muted); }

.status-error {
  background: var(--red);
  box-shadow: 0 0 8px var(--red);
  animation: blink 1s ease-in-out infinite;
}

@keyframes blink {
  0%, 100% { opacity: 1; }
  50%       { opacity: 0.35; }
}

.status-label {
  font-family: 'Orbitron', monospace;
  font-size: 0.6rem;
  font-weight: 600;
  letter-spacing: 0.1em;
  color: var(--text-muted);
}

.header-session {
  display: flex;
  align-items: center;
  gap: 6px;
  color: var(--text-muted);
  font-size: 0.7rem;
  font-family: monospace;
}

.session-icon { opacity: 0.6; }

/* ── Messages ── */
.messages {
  flex: 1;
  overflow-y: auto;
  padding: 24px 20px;
  display: flex;
  flex-direction: column;
  gap: 16px;
  scroll-behavior: smooth;
}

/* ── Empty State ── */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  flex: 1;
  gap: 20px;
  padding: 40px 20px;
  text-align: center;
}

.empty-logo {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 140px;
  height: 140px;
}

.logo-ring {
  position: absolute;
  inset: 0;
  border-radius: 50%;
  border: 2px solid var(--green);
  box-shadow: 0 0 20px rgba(0, 255, 65, 0.3), inset 0 0 20px rgba(0, 255, 65, 0.05);
  animation: pulse-ring 3s ease-in-out infinite;
}

@keyframes pulse-ring {
  0%, 100% { box-shadow: 0 0 20px rgba(0, 255, 65, 0.3), inset 0 0 20px rgba(0, 255, 65, 0.05); transform: scale(1); }
  50%       { box-shadow: 0 0 40px rgba(0, 255, 65, 0.5), inset 0 0 30px rgba(0, 255, 65, 0.1); transform: scale(1.05); }
}

.logo-text {
  font-family: 'Orbitron', monospace;
  font-size: 1.5rem;
  font-weight: 700;
  color: var(--green);
  text-shadow: 0 0 20px rgba(0, 255, 65, 0.7);
  letter-spacing: 0.2em;
  z-index: 1;
}

.empty-subtitle {
  font-size: 0.85rem;
  color: var(--text-muted);
  letter-spacing: 0.05em;
  max-width: 300px;
}

.suggestions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  justify-content: center;
  margin-top: 8px;
  max-width: 560px;
}

.suggestion-chip {
  background: var(--bg-card);
  border: 1px solid var(--border);
  color: var(--text-muted);
  padding: 8px 16px;
  border-radius: 20px;
  font-size: 0.8rem;
  font-family: 'Exo 2', sans-serif;
  cursor: pointer;
  transition: all 200ms ease;
}

.suggestion-chip:hover {
  border-color: var(--green);
  color: var(--green);
  box-shadow: 0 0 10px rgba(0, 255, 65, 0.2);
  background: rgba(0, 255, 65, 0.05);
}

/* ── Message Bubbles ── */
.message-wrapper {
  display: flex;
  width: 100%;
}

.message-wrapper.user      { justify-content: flex-end; }
.message-wrapper.assistant { justify-content: flex-start; }
.message-wrapper.error     { justify-content: flex-start; }

.message-bubble {
  max-width: 78%;
  padding: 14px 16px;
  border-radius: 8px;
  position: relative;
  animation: slide-in 150ms ease;
}

@keyframes slide-in {
  from { opacity: 0; transform: translateY(8px); }
  to   { opacity: 1; transform: translateY(0); }
}

.message-bubble.user {
  background: rgba(0, 255, 65, 0.06);
  border: 1px solid rgba(0, 255, 65, 0.2);
  border-right: 3px solid var(--green);
}

.message-bubble.assistant {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-left: 3px solid var(--green-dim);
}

.message-bubble.error {
  background: rgba(255, 51, 51, 0.08);
  border: 1px solid rgba(255, 51, 51, 0.3);
  border-left: 3px solid var(--red);
}

.message-role {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 0.6rem;
  font-family: 'Orbitron', monospace;
  font-weight: 600;
  letter-spacing: 0.1em;
  margin-bottom: 8px;
}

.message-wrapper.user      .message-role { color: var(--green); }
.message-wrapper.assistant .message-role { color: var(--green-dim); }
.message-wrapper.error     .message-role { color: var(--red); }

.message-content {
  font-size: 0.9rem;
  line-height: 1.65;
  color: var(--text);
  white-space: normal;
  word-break: break-word;
}

/* User messages keep pre-wrap for literal newlines (M3) */
.message-wrapper.user .message-content {
  white-space: pre-wrap;
}

/* Markdown rendered content styles */
.message-content :deep(p)          { margin-bottom: 0.7em; }
.message-content :deep(p:last-child) { margin-bottom: 0; }
.message-content :deep(code)       { background: rgba(0,255,65,0.08); border: 1px solid rgba(0,255,65,0.15); padding: 1px 5px; border-radius: 3px; font-family: monospace; font-size: 0.85em; color: var(--green); }
.message-content :deep(pre)        { background: rgba(0,0,0,0.4); border: 1px solid var(--border); border-radius: 6px; padding: 12px 16px; overflow-x: auto; margin: 10px 0; }
.message-content :deep(pre code)   { background: none; border: none; padding: 0; color: var(--text); }
.message-content :deep(ul), .message-content :deep(ol) { padding-left: 1.5em; margin: 0.5em 0; }
.message-content :deep(li)         { margin-bottom: 0.3em; }
.message-content :deep(h1), .message-content :deep(h2), .message-content :deep(h3) { font-family: 'Orbitron', monospace; color: var(--green); margin: 1em 0 0.4em; font-size: 1em; }
.message-content :deep(blockquote) { border-left: 3px solid var(--green-dim); padding-left: 12px; color: var(--text-muted); margin: 0.5em 0; }
.message-content :deep(a)          { color: var(--green); text-underline-offset: 3px; }
.message-content :deep(strong)     { color: var(--text); font-weight: 600; }
.message-content :deep(hr)         { border: none; border-top: 1px solid var(--border); margin: 1em 0; }

/* Typing cursor */
.typing-cursor {
  display: inline-block;
  color: var(--green);
  font-size: 1rem;
  margin-left: 2px;
  animation: cursor-blink 0.7s step-end infinite;
}

@keyframes cursor-blink {
  0%, 100% { opacity: 1; }
  50%       { opacity: 0; }
}

/* Message meta */
.message-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 10px;
  font-size: 0.65rem;
  color: var(--text-muted);
  font-family: 'Exo 2', sans-serif;
  opacity: 0.7;
}

.meta-dot { opacity: 0.4; }

/* ── Input Area ── */
.input-area {
  padding: 16px 20px 20px;
  background: rgba(13, 17, 23, 0.95);
  border-top: 1px solid var(--border);
  backdrop-filter: blur(8px);
  position: sticky;
  bottom: 0;
}

.input-wrapper {
  display: flex;
  align-items: flex-end;
  gap: 10px;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-bottom: 2px solid var(--border);
  border-radius: 10px;
  padding: 10px 12px;
  transition: border-color 200ms ease, box-shadow 200ms ease;
}

.input-wrapper.focused {
  border-color: var(--green);
  border-bottom-color: var(--green);
  box-shadow: 0 0 10px rgba(0, 255, 65, 0.2), 0 0 30px rgba(0, 255, 65, 0.05);
}

.input-wrapper.loading {
  border-color: var(--green-dim);
  opacity: 0.8;
}

.input-field {
  flex: 1;
  background: transparent;
  border: none;
  outline: none;
  color: var(--text);
  font-family: 'Exo 2', sans-serif;
  font-size: 0.9rem;
  line-height: 1.5;
  resize: none;
  max-height: 160px;
  scrollbar-width: thin;
}

.input-field::placeholder { color: var(--text-muted); opacity: 0.6; }
.input-field:disabled     { cursor: not-allowed; }

.send-btn {
  width: 36px;
  height: 36px;
  border-radius: 8px;
  background: var(--green);
  border: none;
  color: var(--bg);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  flex-shrink: 0;
  transition: all 200ms ease;
}

.send-btn:hover:not(:disabled) {
  background: #33ff6e;
  box-shadow: 0 0 12px rgba(0, 255, 65, 0.5);
  transform: translateY(-1px);
}

.send-btn:disabled {
  background: var(--border);
  color: var(--text-muted);
  cursor: not-allowed;
  transform: none;
}

.send-btn .spin {
  animation: rotate 1s linear infinite;
}

@keyframes rotate {
  from { transform: rotate(0deg); }
  to   { transform: rotate(360deg); }
}

.input-hint {
  font-size: 0.65rem;
  color: var(--text-muted);
  opacity: 0.5;
  text-align: center;
  margin-top: 8px;
  font-family: 'Exo 2', sans-serif;
}

/* ── Reduced motion ── */
@media (prefers-reduced-motion: reduce) {
  .status-connected, .status-error,
  .logo-ring, .typing-cursor, .send-btn .spin {
    animation: none !important;
  }
  .message-bubble { animation: none !important; }
  .send-btn { transition: none !important; }
  .suggestion-chip { transition: none !important; }
}
</style>
