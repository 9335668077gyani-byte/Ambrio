# ambrio/sandbox/policies/allowlist.py

# Output patterns that indicate unsafe or escape-attempt behavior
UNSAFE_OUTPUT_PATTERNS = [
    "import os",
    "subprocess",
    "__import__",
    "eval(",
    "exec(",
    "open(/etc",
    "open(/proc",
    "socket.connect",
    "requests.get",
    "urllib.request",
]

def is_safe_output(text: str) -> bool:
    """Returns True if text contains no known unsafe patterns."""
    lower = text.lower()
    return not any(p.lower() in lower for p in UNSAFE_OUTPUT_PATTERNS)
