// frontend/src/composables/useWebSocket.js
import { ref, readonly } from 'vue'

export function useWebSocket(sessionId) {
  const messages  = ref([])
  const isLoading = ref(false)
  const status    = ref('disconnected') // 'connected' | 'disconnected' | 'error'
  let ws = null
  let retryDelay = 1000  // I4: exponential back-off state

  function connect() {
    if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) return
    ws = new WebSocket(`ws://localhost:8765/chat/${sessionId}`)

    // I4: reset delay on success
    ws.onopen = () => {
      status.value = 'connected'
      retryDelay = 1000
    }

    // I1 + I4: reset loading on disconnect, schedule reconnect
    ws.onclose = () => {
      status.value = 'disconnected'
      ws = null
      if (isLoading.value) {
        isLoading.value = false
        messages.value.push({ role: 'error', content: 'Connection lost mid-response.', meta: null })
      }
      // I4: exponential back-off reconnect
      setTimeout(connect, retryDelay)
      retryDelay = Math.min(retryDelay * 2, 30000)
    }

    ws.onerror = () => {
      status.value = 'error'
      // ws.onclose will fire next — let it handle retry
    }

    ws.onmessage = (e) => {
      const msg = JSON.parse(e.data)
      if (msg.type === 'token') {
        const last = messages.value.at(-1)
        if (last && last.role === 'assistant') last.content += msg.data
      } else if (msg.type === 'done') {
        const last = messages.value.at(-1)
        if (last) last.meta = { model: msg.model, tokens: msg.tokens, elapsed: msg.elapsed }
        isLoading.value = false
      } else if (msg.type === 'error') {
        // I2: remove ghost empty assistant bubble before showing error
        const last = messages.value.at(-1)
        if (last && last.role === 'assistant' && last.content === '') {
          messages.value.pop()
        }
        messages.value.push({ role: 'error', content: msg.message, meta: null })
        isLoading.value = false
      }
    }
  }

  function send(content) {
    if (!content.trim()) return
    connect()
    messages.value.push({ role: 'user',      content, meta: null })
    messages.value.push({ role: 'assistant', content: '', meta: null })
    isLoading.value = true

    const _send = () => ws.send(JSON.stringify({ content }))
    if (ws.readyState === WebSocket.OPEN) _send()
    else ws.addEventListener('open', _send, { once: true })
  }

  connect()
  return { messages: readonly(messages), isLoading: readonly(isLoading), status: readonly(status), send }
}
