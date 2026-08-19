"""
Aegis Engine Root Main Entrypoint
"""
import os
import sys
import uvicorn

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 3000))
    print("=================================================")
    print(">> Resilient Stealth Scraper Engine Online (Python)")
    print(f">> Server listening on http://localhost:{port}")
    print(f">> Real-time Telemetry: http://localhost:{port}/api/stream")
    print("=================================================")
    uvicorn.run("server.main:app", host="0.0.0.0", port=port, reload=False)
