import sys
sys.path.insert(0, r"C:\MY PROJECTS\Ambrio")

from ambrio.config import PROVIDER_KEYS
from ambrio.router.model_router import ModelRouter
from ambrio.router.model_registry import REGISTRY, DEFAULT_ROUTING, get_model, print_registry

print("=== REGISTERED MODELS ===")
print_registry()

print(f"\nTotal models registered: {len(REGISTRY)}")

print("\n=== DEFAULT ROUTING ===")
for task, alias in DEFAULT_ROUTING.items():
    m = get_model(alias)
    model_id = m.model_id if m else "NOT FOUND"
    print(f"  {task:<12} -> {alias:<38} [{model_id}]")

print("\n=== ROUTER STATUS (no API keys yet) ===")
r = ModelRouter(PROVIDER_KEYS)
status = r.status()
print(f"  API providers configured: {list(status['providers'].keys()) or 'none'}")
print(f"  Total models in registry: {status['total_models_registered']}")
print("\nSMOKE TEST PASSED")
