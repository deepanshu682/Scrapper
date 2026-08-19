"""
Aegis Resilient Ingestion Server (FastAPI + Python)
Provides real-time SSE telemetry, stealth scraping endpoints, status metrics, and static dashboard serving.
"""
import os
import csv
import io
import json
import time
import datetime
from typing import Optional
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import StreamingResponse, Response, JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .engine.orchestrator import IngestionOrchestrator

app = FastAPI(title="Aegis Stealth Scraper Engine", version="1.4.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

orchestrator = IngestionOrchestrator()
start_time = time.time()

# Path to public dashboard directory
ROOT_DIR = Path(__file__).resolve().parent.parent
PUBLIC_DIR = ROOT_DIR / "public"


class ScrapeRequest(BaseModel):
    sourceId: str
    scenario: Optional[str] = None
    customUrl: Optional[str] = None
    limit: Optional[int] = 25


@app.get("/health")
async def health_check():
    return {
        "status": "ok",
        "time": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }


@app.get("/api/stream")
async def stream_telemetry(request: Request):
    """Real-time SSE event stream for live telemetry logs and metrics"""
    queue = orchestrator.subscribe()

    async def event_generator():
        # Initial greeting event
        init_evt = json.dumps({"type": "CONNECTED", "message": "Real-time Python telemetry stream initialized"})
        yield f"data: {init_evt}\n\n"

        try:
            while True:
                if await request.is_disconnected():
                    break

                try:
                    # Wait for next event or send keep-alive comment
                    event_data = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield f"data: {json.dumps(event_data)}\n\n"
                except asyncio.TimeoutError:
                    # Keep-alive heartbeat comment
                    yield ": keep-alive\n\n"
        finally:
            orchestrator.unsubscribe(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


import asyncio


@app.get("/api/status")
async def get_status():
    """System Health, Proxies, and Circuit Breakers"""
    uptime = time.time() - start_time
    status = orchestrator.get_system_status()
    return {
        "status": "ONLINE",
        "uptime": uptime,
        **status,
    }


@app.post("/api/scrape")
async def trigger_scrape(req: ScrapeRequest):
    """Trigger a stealth scrape run across real sources or sandbox vectors"""
    if not req.sourceId:
        raise HTTPException(status_code=400, detail="sourceId is required")

    try:
        result = await orchestrator.run_ingestion(
            req.sourceId,
            {
                "scenario": req.scenario,
                "customUrl": req.customUrl,
                "limit": req.limit or 25,
            },
        )
        return {"success": True, **result}
    except Exception as err:
        return JSONResponse(status_code=500, content={"success": False, "error": str(err)})


@app.get("/api/history")
async def get_history():
    """Get history of past ingestion runs"""
    return orchestrator.history


@app.get("/api/export/{run_id}")
async def export_data(run_id: str, format: str = Query("json")):
    """Export extracted job listings as CSV or JSON"""
    record = None
    if run_id and run_id != "latest":
        record = next((h for h in orchestrator.history if h.get("runId") == run_id), None)

    # If specific run not found or "latest" requested, pick latest run with jobs
    if not record:
        record = next((h for h in orchestrator.history if h.get("jobs")), None)
        if not record and orchestrator.history:
            record = orchestrator.history[0]

    jobs = record.get("jobs", []) if record else []
    source_id = record.get("sourceId", "listings") if record else "empty"
    safe_run_id = run_id if (run_id and run_id != "latest") else (record.get("runId", "latest") if record else "latest")

    if format.lower() == "csv":
        output = io.StringIO()
        writer = csv.writer(output, quoting=csv.QUOTE_ALL)
        writer.writerow(["ID", "Title", "Company", "Location", "Salary", "URL", "Source", "Tier"])

        for j in jobs:
            writer.writerow([
                j.get("id", ""),
                j.get("title", ""),
                j.get("company", ""),
                j.get("location", ""),
                j.get("salary", ""),
                j.get("url", ""),
                j.get("source", ""),
                j.get("tier", ""),
            ])

        csv_content = output.getvalue()
        return Response(
            content=csv_content,
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="jobs-{source_id}-{safe_run_id}.csv"'},
        )

    return Response(
        content=json.dumps(jobs, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="jobs-{source_id}-{safe_run_id}.json"'},
    )


# Mount static assets from public/
if PUBLIC_DIR.exists():
    app.mount("/", StaticFiles(directory=str(PUBLIC_DIR), html=True), name="static")


@app.get("/{full_path:path}")
async def fallback_spa(full_path: str):
    index_path = PUBLIC_DIR / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path))
    return JSONResponse(status_code=404, content={"error": "Not Found"})
