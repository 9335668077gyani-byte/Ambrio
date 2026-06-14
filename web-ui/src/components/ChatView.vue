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
    </aside>

    <main class="chat-main neu-container">
      <div class="chat-history">
        <div class="message assistant animate-fade-in">
          Hello! I am Ambrio. How can I help you today?
        </div>
        <div v-for="(msg, idx) in messages" :key="idx" :class="['message', msg.role, 'animate-fade-in']">
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
import { ref, onMounted, onUnmounted } from 'vue'

const prompt = ref('')
const messages = ref([])
const loading = ref(false)
let ws = null
let currentAssistantMessage = null

const connectWS = () => {
  ws = new WebSocket('ws://127.0.0.1:8000/chat/default-web-session')
  
  ws.onmessage = (event) => {
    const data = JSON.parse(event.data)
    
    if (data.type === 'token') {
      if (currentAssistantMessage) {
        currentAssistantMessage.content += data.data
      }
    } else if (data.model === 'multi-agent' || data.tokens) {
      // Chat done
      loading.value = false
      currentAssistantMessage = null
    } else if (data.message) {
      // Error message
      messages.value.push({ role: 'assistant', content: `Error: ${data.message}` })
      loading.value = false
      currentAssistantMessage = null
    }
  }

  ws.onclose = () => {
    console.log('WS Disconnected, reconnecting...')
    setTimeout(connectWS, 2000)
  }
}

onMounted(() => {
  connectWS()
})

onUnmounted(() => {
  if (ws) {
    ws.onclose = null
    ws.close()
  }
})

const sendPrompt = () => {
  if (!prompt.value.trim() || loading.value || !ws || ws.readyState !== WebSocket.OPEN) return;
  
  const userText = prompt.value
  messages.value.push({ role: 'user', content: userText })
  prompt.value = ''
  loading.value = true
  
  currentAssistantMessage = { role: 'assistant', content: '' }
  messages.value.push(currentAssistantMessage)
  
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
</style>
