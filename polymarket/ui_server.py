# ui_server.py
from __future__ import annotations

import json
import logging
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from bot.runtime import BotRuntime

logging.basicConfig(level=logging. INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("ui")

app = FastAPI()
runtime = BotRuntime(cfg_path="config. yaml", log=logging.getLogger("polyscalp"))

# Serve static files (CSS, JS, images, etc.)
static_dir = Path(__file__).parent / "static"
static_dir.mkdir(exist_ok=True)

@app.get("/")
async def home():
    return FileResponse(static_dir / "index.html")

# Mount static directory for CSS, JS, images
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

@app.post("/api/start")
async def api_start():
    await runtime.start()
    return JSONResponse({"ok": True, "running": runtime.is_running()})

@app.post("/api/stop")
async def api_stop():
    await runtime.stop()
    return JSONResponse({"ok": True, "running": runtime.is_running()})

class CloseReq(BaseModel):
    asset_id: str
    shares: float | None = None
    price: float | None = None

@app.post("/api/close")
async def api_close(req: CloseReq):
    await runtime.cmd_close_position(req.asset_id, req.shares, req. price)
    return JSONResponse({"ok": True})

@app.post("/api/close_all")
async def api_close_all():
    await runtime.cmd_close_all()
    return JSONResponse({"ok": True})

@app.websocket("/ws")
async def ws_status(ws: WebSocket):
    await ws.accept()
    seq = 0
    try:
        await ws.send_text(json.dumps(runtime.snapshot))
        while True:
            seq, snap = await runtime.wait_for_update(seq)
            await ws.send_text(json. dumps(snap))
    except WebSocketDisconnect:
        return
    except Exception: 
        return
