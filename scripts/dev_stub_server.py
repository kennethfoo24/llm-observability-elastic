"""Run the offline stub backend (no Elastic, no EIS) on http://localhost:8000, password 'demo'.

STUB_GEMMA_UP=1 to make the Gemma model available. Serves frontend/dist if it has been built.
"""
import os
import sys
from pathlib import Path

import uvicorn

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
from app.stub_app import build_stub_app  # noqa: E402

if __name__ == "__main__":
    app = build_stub_app(gemma_up=os.getenv("STUB_GEMMA_UP") == "1")
    uvicorn.run(app, host="127.0.0.1", port=int(os.getenv("PORT", "8000")))
