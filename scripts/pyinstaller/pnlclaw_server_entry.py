"""PyInstaller entry point for PnLClaw local-api sidecar."""

import sys
import os

if getattr(sys, "frozen", False):
    os.chdir(os.path.dirname(sys.executable))

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "services", "local-api"))

import uvicorn  # noqa: E402

from app.main import create_app  # noqa: E402

app = create_app()

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8080, log_level="info")
