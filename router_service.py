# router_service.py
"""
Entry point for the Ambrio Cognitive Router process.
Run this as a separate process before launching the UI.
"""
import asyncio, logging, sys
from ambrio.router.service import RouterService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [ROUTER] %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)

if __name__ == "__main__":
    asyncio.run(RouterService().start())
