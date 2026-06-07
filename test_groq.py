"""Test Groq API with browser User-Agent — same as fixed tester."""
import urllib.request, urllib.error, json
from pathlib import Path

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"

env = {}
for line in Path(r"C:\MY PROJECTS\Ambrio\.env").read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if "=" in line and not line.startswith("#"):
        k, _, v = line.partition("=")
        env[k.strip()] = v.strip()

key = env.get("GROQ_API_KEYS", "").split(",")[0].strip()
print(f"Key: {key[:12]}...")

req = urllib.request.Request(
    "https://api.groq.com/openai/v1/models",
    headers={"Authorization": f"Bearer {key}", "User-Agent": UA}
)
try:
    with urllib.request.urlopen(req, timeout=10) as r:
        data = json.loads(r.read())
        models = [m["id"] for m in data.get("data", [])]
        print(f"SUCCESS — {len(models)} models:")
        for m in models:
            print(f"  - {m}")
except urllib.error.HTTPError as e:
    print(f"HTTP {e.code}: {e.read().decode()[:300]}")
except Exception as e:
    print(f"Error: {e}")
