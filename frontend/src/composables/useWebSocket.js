// frontend/src/composables/useWebSocket.js
import { ref, readonly } from 'vue'

export function useWebSocket(sessionId) {
  const messages  = ref([])
  const isLoading = ref(false)
  const status    = ref('disconnected') // 'connected' | 'disconnected' | 'error'
  let ws = null

  function connect() {
    if (ws && ws.readyState === WebSocket.OPEN) return
    ws = new WebSocket(`ws://localhost:8765/chat/${sessionId}`)

    ws.onopen  = () => { status.value = 'connected' }
    ws.onclose = () => { status.value = 'disconnected'; ws = null }
    ws.onerror = () => { status.value = 'error' }

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
