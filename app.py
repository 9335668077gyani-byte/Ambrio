import streamlit as st
import requests
import json

# ── Configuration ──────────────────────────────────────────────────────────────
OLLAMA_API_URL = "http://localhost:11434/api/chat"
MODEL_NAME     = "codegemma"
APP_NAME       = "Ambrio"
APP_SUBTITLE   = "Your Personal AI Assistant"

# ── Page Setup ─────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title=APP_NAME,
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Custom CSS ─────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
}

/* Dark background */
.stApp {
    background: linear-gradient(135deg, #0f0f1a 0%, #141428 50%, #0f1420 100%);
    min-height: 100vh;
}

/* Header */
.ambrio-header {
    text-align: center;
    padding: 2rem 0 1rem 0;
}
.ambrio-title {
    font-size: 3rem;
    font-weight: 700;
    background: linear-gradient(135deg, #7c3aed, #2563eb, #06b6d4);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    letter-spacing: -1px;
    margin: 0;
}
.ambrio-sub {
    color: #64748b;
    font-size: 1rem;
    margin-top: 0.3rem;
}

/* Chat container */
.chat-bubble-user {
    background: linear-gradient(135deg, #7c3aed22, #2563eb22);
    border: 1px solid #7c3aed44;
    border-radius: 12px;
    padding: 12px 16px;
    margin: 8px 0;
    color: #e2e8f0;
}
.chat-bubble-ai {
    background: #1e293b;
    border: 1px solid #334155;
    border-radius: 12px;
    padding: 12px 16px;
    margin: 8px 0;
    color: #e2e8f0;
}

/* Model badge */
.model-badge {
    display: inline-block;
    background: linear-gradient(135deg, #7c3aed, #2563eb);
    color: white;
    font-size: 0.7rem;
    font-weight: 600;
    padding: 2px 10px;
    border-radius: 999px;
    letter-spacing: 0.5px;
    text-transform: uppercase;
}

/* Input area */
.stChatInput textarea {
    background: #1e293b !important;
    border: 1px solid #334155 !important;
    color: #e2e8f0 !important;
    border-radius: 12px !important;
}
</style>
""", unsafe_allow_html=True)

# ── Header ─────────────────────────────────────────────────────────────────────
st.markdown(f"""
<div class="ambrio-header">
    <div class="ambrio-title">🧠 {APP_NAME}</div>
    <div class="ambrio-sub">{APP_SUBTITLE} &nbsp;·&nbsp; <span class="model-badge">{MODEL_NAME}</span></div>
</div>
""", unsafe_allow_html=True)

st.divider()

# ── Session State ──────────────────────────────────────────────────────────────
if "messages" not in st.session_state:
    st.session_state.messages = []

# ── Chat History ───────────────────────────────────────────────────────────────
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# ── Chat Input ─────────────────────────────────────────────────────────────────
if prompt := st.chat_input(f"Ask {APP_NAME} anything..."):
    # Show user message
    st.chat_message("user").markdown(prompt)
    st.session_state.messages.append({"role": "user", "content": prompt})

    # Build payload with full conversation history
    payload = {
        "model": MODEL_NAME,
        "messages": st.session_state.messages,
        "stream": True,
    }

    # Stream AI response
    with st.chat_message("assistant"):
        response_placeholder = st.empty()
        full_response = ""

        try:
            with requests.post(OLLAMA_API_URL, json=payload, stream=True, timeout=120) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if line:
                        chunk = json.loads(line)
                        if "message" in chunk and "content" in chunk["message"]:
                            full_response += chunk["message"]["content"]
                            response_placeholder.markdown(full_response + "▌")

            response_placeholder.markdown(full_response)
            st.session_state.messages.append({"role": "assistant", "content": full_response})

        except requests.exceptions.ConnectionError:
            st.error("❌ Cannot connect to Ollama. Make sure Ollama is running: `ollama serve`")
        except Exception as e:
            st.error(f"❌ Error: {e}")

# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### 🧠 Ambrio")
    st.markdown(f"**Model:** `{MODEL_NAME}`")
    st.markdown(f"**Messages:** {len(st.session_state.messages)}")
    st.divider()
    if st.button("🗑️ Clear Chat", use_container_width=True):
        st.session_state.messages = []
        st.rerun()
    st.divider()
    st.caption("Powered by Ollama · Runs 100% locally")
