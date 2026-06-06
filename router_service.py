# router_service.py
"""
Entry point for the Ambrio Cognitive Router process.
Run via start_ambrio.ps1, or manually:
    .venv\\Scripts\\python.exe router_service.py [--db ambrio.db]
"""
import asyncio, logging, sys, argparse
from ambrio.router.service import RouterService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [ROUTER] %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ambrio Cognitive Router")
    parser.add_argument("--db", default="ambrio.db", help="Path to SQLite DB file")
    args = parser.parse_args()

    # Windows: ProactorEventLoop (default) breaks ZMQ add_reader.
    # Create SelectorEventLoop directly — works on Python 3.10–3.16.
    if sys.platform == "win32":
        loop = asyncio.SelectorEventLoop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(RouterService().start(db_path=args.db))
    else:
        asyncio.run(RouterService().start(db_path=args.db))
