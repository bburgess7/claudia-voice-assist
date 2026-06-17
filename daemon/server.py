"""claudiad — the local voice daemon. FastAPI + WebSocket.

Endpoints
  POST /speak    {text, mode?}     summarize (per verbosity) then speak; fan out to remote clients
  POST /say      {text}            verbatim convenience (no summarization)
  POST /stop                       interrupt current + queued speech (barge-in)
  GET  /voices                     list voices for the active engine
  GET  /config   POST /config      read / update runtime config (speed, voice, verbosity, mute…)
  GET  /health
  WS   /ws       remote/mobile clients: receive {type:audio} frames + {type:transcript|config}
  /                                serves the control panel + PWA (web/public)
"""
from __future__ import annotations

import asyncio
import base64
import os
from typing import List, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import config
from .engines import get_engine, available
from .speech import SpeechManager

WEB_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "web", "public")

app = FastAPI(title="claudiad")
speech = SpeechManager()
_clients: List[WebSocket] = []
_loop: Optional[asyncio.AbstractEventLoop] = None


class SpeakBody(BaseModel):
    text: str
    mode: Optional[str] = None  # verbatim | summary | headline; default = config.verbosity


def _broadcast(payload: dict) -> None:
    """Thread-safe push to all connected WS clients."""
    if not _clients or _loop is None:
        return
    async def _send():
        dead = []
        for ws in list(_clients):
            try:
                await ws.send_json(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            if ws in _clients:
                _clients.remove(ws)
    asyncio.run_coroutine_threadsafe(_send(), _loop)


@app.on_event("startup")
async def _startup():
    global _loop
    _loop = asyncio.get_running_loop()
    config.load()
    speech.has_remote = lambda: len(_clients) > 0
    speech.on_transcript = lambda raw, spoken: _broadcast(
        {"type": "transcript", "spoken": spoken, "speaking": True})
    speech.on_audio = lambda wav, utt: _broadcast(
        {"type": "audio", "wav": base64.b64encode(wav).decode()})


@app.get("/health")
async def health():
    return {"ok": True, "engines": available(), "speaking": speech.speaking}


@app.post("/speak")
async def speak(body: SpeakBody):
    spoken = speech.enqueue(body.text, body.mode)
    return {"spoken": spoken}


@app.post("/say")
async def say(body: SpeakBody):
    spoken = speech.enqueue(body.text, mode="verbatim")
    return {"spoken": spoken}


@app.post("/stop")
async def stop():
    speech.interrupt()
    return {"ok": True}


@app.get("/voices")
async def voices():
    return {"engine": config.get("engine"), "voices": get_engine(config.get("engine")).list_voices()}


@app.get("/config")
async def get_config():
    return config.all()


@app.post("/config")
async def set_config(request: Request):
    patch = await request.json()
    new = config.update(patch)
    _broadcast({"type": "config", "config": new})
    return new


@app.websocket("/ws")
async def ws(websocket: WebSocket):
    await websocket.accept()
    secret = config.get("shared_secret")
    if secret:
        try:
            hello = await asyncio.wait_for(websocket.receive_json(), timeout=5)
            if hello.get("secret") != secret:
                await websocket.close(code=4401)
                return
        except Exception:
            await websocket.close(code=4401)
            return
    _clients.append(websocket)
    await websocket.send_json({"type": "config", "config": config.all()})
    try:
        while True:
            msg = await websocket.receive_json()
            t = msg.get("type")
            if t == "speak":
                speech.enqueue(msg.get("text", ""), msg.get("mode"))
            elif t == "say":
                speech.enqueue(msg.get("text", ""), mode="verbatim")
            elif t == "stop":
                speech.interrupt()
            elif t == "config":
                config.update(msg.get("config", {}))
            # t == "mic": reserved for streaming STT (listening side)
    except WebSocketDisconnect:
        pass
    finally:
        if websocket in _clients:
            _clients.remove(websocket)


if os.path.isdir(WEB_DIR):
    app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
