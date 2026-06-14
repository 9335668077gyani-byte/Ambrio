<template>
  <div class="app-layout">
    <aside class="sidebar neu-container">
      <h2 class="sidebar-title">Ambrio</h2>
      <button class="neu-button primary new-chat-btn">
        + New Chat
      </button>
      <div class="session-list">
        <div class="session-item">Memory Diagnostics</div>
        <div class="session-item">SparePartsPro ERP</div>
      </div>
      <div class="connection-status" :class="connectionStatus">
        <span class="status-dot"></span>
        {{ connectionLabel }}
      </div>
    </aside>

    <main class="chat-main neu-container">
      <div class="chat-history">
        <div class="message assistant animate-fade-in">
          Hello! I am Ambrio. How can I help you today?
        </div>
        <div v-for="msg in messages" :key="msg.id" :class="['message', msg.role, 'animate-fade-in']">
          {{ msg.content }}
        </div>
      </div>

      <div class="chat-input-area">
        <input 
          v-model="prompt" 
          @keydown.enter="sendPrompt" 
          type="text" 
          class="neu-input" 
          placeholder="Ask Ambrio anything..." 
          :disabled="loading"
        />
        <button class="neu-button primary" @click="sendPrompt" :disabled="loading">
          {{ loading ? '...' : 'Send' }}
        </button>
      </div>
    </main>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'

let msgCounter = 0 // I3: monotonic counter for stable :key values

const prompt = ref('')
const messages = ref([])
const loading = ref(false)
const connectionStatus = ref('connecting') // 'connecting' | 'connected' | 'disconnected' | 'error'
let ws = null
let currentAssistantIdx = null // F4: store index, not object reference
let reconnectDelay = 1000      // F3: backoff state
let reconnectTimer = null      // I4: handle so we can cancel on unmount
let isDestroyed = false        // F3: clean-close guard

const connectWS = () => {
  if (isDestroyed) return // F3: guard against reconnect after unmount
  ws = new WebSocket('ws://127.0.0.1:8000/chat/default-web-session')

  // F3: track connected state and reset backoff
  ws.onopen = () => {
    reconnectDelay = 1000
    connectionStatus.value = 'connected'
  }

  // F5: onerror handler
  ws.onerror = (err) => {
    console.error('WebSocket error:', err)
    connectionStatus.value = 'error'
    loading.value = false       // I1: unfreeze Send button on error
    currentAssistantIdx = null  // I1: reset stream tracker
  }

  ws.onmessage = (event) => {
    // F5: JSON.parse guard
    let data
    try {
      data = JSON.parse(event.data)
    } catch (e) {
      console.error('WS message parse error:', e, event.data)
      return
    }

    if (data.type === 'token') {
      // F4: index-based mutation so Vue 3 detects the change
      if (currentAssistantIdx !== null) {
        const msg = messages.value[currentAssistantIdx]
        messages.value[currentAssistantIdx] = { ...msg, content: msg.content + data.data }
      }
    } else if (data.model === 'multi-agent' || data.tokens) {
      // Chat done
      loading.value = false
      currentAssistantIdx = null
    } else if (data.message) {
      // Error message from server
      messages.value.push({ role: 'assistant', content: `Error: ${data.message}` })
      loading.value = false
      currentAssistantIdx = null
    }
  }

  // F3: exponential backoff + clean-close guard
  ws.onclose = (event) => {
    connectionStatus.value = 'disconnected'
    loading.value = false       // I2: unfreeze Send button if mid-stream disconnect
    currentAssistantIdx = null  // I2: reset stream tracker
    // Clean closes (1000=Normal, 1001=GoingAway) — don't reconnect
    if (event.code === 1000 || event.code === 1001 || isDestroyed) return
    console.log(`WS closed (code ${event.code}), reconnecting in ${reconnectDelay}ms`)
    reconnectTimer = setTimeout(connectWS, reconnectDelay) // I4: store handle
    reconnectDelay = Math.min(reconnectDelay * 2, 30000) // cap at 30s
  }
}

onMounted(() => {
  connectWS()
})

// F3: set destroyed flag before closing so onclose doesn't re-trigger connectWS
onUnmounted(() => {
  isDestroyed = true
  reconnectDelay = 1000 // C2: reset backoff for next mount
  if (reconnectTimer !== null) {
    clearTimeout(reconnectTimer) // I4: cancel pending reconnect
    reconnectTimer = null
  }
  if (ws) {
    ws.onclose = null
    ws.close(1000) // clean close with code 1000
  }
})

// M2: computed label replaces nested ternary in template
const connectionLabel = computed(() => {
  if (connectionStatus.value === 'connected') return 'Connected'
  if (connectionStatus.value === 'connecting') return 'Connecting...'
  if (connectionStatus.value === 'error') return 'Error'
  return 'Disconnected'
})

const sendPrompt = () => {
  if (!prompt.value.trim() || loading.value || !ws || ws.readyState !== WebSocket.OPEN) return

  const userText = prompt.value
  // I3: assign stable id from monotonic counter
  messages.value.push({ id: ++msgCounter, role: 'user', content: userText })
  prompt.value = ''
  loading.value = true

  // F4: push placeholder and store its index
  // NOTE: currentAssistantIdx is safe from concurrent sends because the Send button
  // is disabled while loading=true. This is enforced by :disabled="loading" in the template. (C1)
  const assistantIdx = messages.value.length
  messages.value.push({ id: ++msgCounter, role: 'assistant', content: '' })
  currentAssistantIdx = assistantIdx

  ws.send(JSON.stringify({ content: userText }))
}
</script>

<style scoped>
.app-layout {
  display: flex;
  gap: 24px;
  width: 90vw;
  max-width: 1400px;
  height: 90vh;
}

.sidebar {
  width: 280px;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.sidebar-title {
  font-size: 1.5rem;
  font-weight: 600;
  text-align: center;
  color: var(--text-main);
  margin-bottom: 10px;
}

.new-chat-btn {
  width: 100%;
}

.session-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
  overflow-y: auto;
  flex-grow: 1;
}

.session-item {
  padding: 12px 16px;
  border-radius: 12px;
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  transition: all 0.3s;
}

.session-item:hover {
  background: rgba(255, 255, 255, 0.03);
  color: var(--text-main);
}

.chat-main {
  flex-grow: 1;
  display: flex;
  flex-direction: column;
  gap: 20px;
  position: relative;
}

.chat-history {
  flex-grow: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding-right: 12px;
}

.message {
  padding: 16px 20px;
  border-radius: 16px;
  max-width: 80%;
  line-height: 1.5;
}

.message.user {
  align-self: flex-end;
  background: linear-gradient(145deg, #2a2d39, #23252f);
  box-shadow: var(--neu-drop-sm);
  color: var(--text-main);
  border-bottom-right-radius: 4px;
}

.message.assistant {
  align-self: flex-start;
  background: rgba(139, 92, 246, 0.1);
  border: 1px solid rgba(139, 92, 246, 0.2);
  color: var(--text-main);
  border-bottom-left-radius: 4px;
}

.chat-input-area {
  display: flex;
  gap: 16px;
  align-items: center;
  padding-top: 16px;
  border-top: 1px solid rgba(255, 255, 255, 0.05);
}

.chat-input-area .neu-input {
  flex-grow: 1;
}

/* F3/F5: Connection status indicator */
.connection-status {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 0.75rem;
  color: var(--text-muted);
  padding: 8px 0;
}
.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #94a3b8;
  flex-shrink: 0;
}
.connection-status.connected .status-dot { background: #22c55e; }
.connection-status.error .status-dot { background: #ef4444; }
.connection-status.disconnected .status-dot { background: #f59e0b; }

/* M1: connecting state — animated blue pulse */
.connection-status.connecting .status-dot {
  background: #3b82f6;
  animation: pulse 1.5s infinite;
}
@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}
</style>
