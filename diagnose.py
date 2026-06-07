"""Ambrio diagnostic script — finds exactly why it's not replying."""
import sys, traceback, urllib.request, json, asyncio, re
sys.path.insert(0, r'C:\MY PROJECTS\Ambrio')

print("=" * 60)
print("  AMBRIO DIAGNOSTIC")
print("=" * 60)

# 1. Check tool patterns
print("\n[1] TOOL PATTERNS")
try:
    from ambrio.router.service import _TOOL_PATTERNS, _extract_text_tool_call
    print(f"    Loaded: {len(_TOOL_PATTERNS)} patterns")
    for pat, name, arg in _TOOL_PATTERNS:
        try:
            test = pat.search(f'{name}("test")')
            status = "OK" if test else "NO MATCH"
        except Exception as e:
            status = f"BROKEN: {e}"
        print(f"    [{status}] {name}")
    # Test extraction
    result = _extract_text_tool_call('web_search("python tips")')
    print(f"    Extract test: {result}")
except Exception as e:
    print(f"    ERROR: {e}")
    traceback.print_exc()

# 2. Check Ollama
print("\n[2] OLLAMA")
try:
    with urllib.request.urlopen('http://localhost:11434/api/tags', timeout=3) as r:
        data = json.loads(r.read())
        models = [m['name'] for m in data.get('models', [])]
        print(f"    Running: YES")
        print(f"    Models: {models}")
        if not models:
            print("    WARNING: No models pulled! Run: ollama pull llama3.2:1b")
except Exception as e:
    print(f"    Running: NO — {e}")
    print("    FIX: Start Ollama app or run 'ollama serve'")

# 3. Check API keys
print("\n[3] API KEYS (.env)")
try:
    from ambrio.config import PROVIDER_KEYS
    for provider, keys in PROVIDER_KEYS.items():
        status = f"{len(keys)} key(s)" if keys else "NO KEYS"
        print(f"    {provider:<12}: {status}")
except Exception as e:
    print(f"    ERROR: {e}")

# 4. Check ZMQ bridge
print("\n[4] ZMQ BRIDGE")
try:
    import zmq
    ctx = zmq.Context()
    sock = ctx.socket(zmq.DEALER)
    sock.setsockopt(zmq.RCVTIMEO, 1000)
    sock.connect("tcp://127.0.0.1:5555")
    print("    ZMQ connect: OK (port 5555)")
    sock.close()
    ctx.term()
except Exception as e:
    print(f"    ZMQ error: {e}")

# 5. Check context_pruner + compressor
print("\n[5] CONTEXT PRUNER")
try:
    from ambrio.router.memory.token_compressor import _headroom_available, compress_text
    engine = "headroom-ai" if _headroom_available else "built-in"
    print(f"    Compression engine: {engine}")
    result = compress_text("Hello world " * 100, max_tokens=50)
    print(f"    Compress test: {len(result)} chars (from {len('Hello world '*100)})")
except Exception as e:
    print(f"    ERROR: {e}")
    traceback.print_exc()

# 6. Async stream test (try one response)
print("\n[6] STREAM TEST (Ollama direct)")
async def test_stream():
    try:
        from ambrio.router.ollama_client import OllamaClient
        client = OllamaClient()
        chunks = []
        async for chunk in client.stream([{"role": "user", "content": "Say hi"}]):
            if chunk.get("done"):
                break
            token = chunk.get("message", {}).get("content", "")
            chunks.append(token)
            if len(chunks) >= 5:
                break
        reply = "".join(chunks)
        print(f"    Stream test: {'OK — got: ' + repr(reply[:50]) if reply else 'NO RESPONSE'}")
    except Exception as e:
        print(f"    Stream error: {e}")
        traceback.print_exc()

asyncio.run(test_stream())

print("\n" + "=" * 60)
print("  DIAGNOSIS COMPLETE")
print("=" * 60)
