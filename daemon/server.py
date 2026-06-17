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

from fastapi import (FastAPI, WebSocket, WebSocketDisconnect, Request, Header, HTTPException,
                     Depends)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import config
from .engines import get_engine, available
from .speech import SpeechManager

WEB_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "web", "public")

app = FastAPI(title="claudiad")
# The shared secret is the real gate when the daemon is reached over a tunnel, so wildcard CORS is
# fine (no cookies/credentials are used). Lets the Vercel-hosted UI call the tunneled daemon.
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"],
                   allow_headers=["*"], allow_credentials=False)


def require_secret(request: Request, x_claudia_secret: str = Header(default="")):
    """Gate actions when a shared secret is set — but ONLY for proxied/tunneled requests.

    Direct local requests (the same-origin control panel on the Mac) carry no forwarding headers and
    stay exempt, so they work without a secret. Anything arriving via a tunnel/proxy (Cloudflare adds
    cf-connecting-ip; reverse proxies add x-forwarded-for) must present the matching secret.
    """
    secret = config.get("shared_secret")
    if not secret:
        return
    proxied = bool(request.headers.get("x-forwarded-for") or request.headers.get("cf-connecting-ip"))
    if proxied and x_claudia_secret != secret:
        raise HTTPException(status_code=401, detail="bad or missing secret")


speech = SpeechManager()
# each client: {"ws": WebSocket, "role": "control" | "remote"}
#   control  -> sees transcript/config only; audio plays on the host's speakers (no echo)
#   remote   -> also receives streamed audio frames to play in-browser (phone / other computer)
_clients: List[dict] = []
_loop: Optional[asyncio.AbstractEventLoop] = None


class SpeakBody(BaseModel):
    text: str
    mode: Optional[str] = None  # verbatim | summary | headline; default = config.verbosity


def _broadcast(payload: dict, role: Optional[str] = None) -> None:
    """Thread-safe push to connected WS clients. If `role` is set, only clients of that role."""
    if not _clients or _loop is None:
        return
    async def _send():
        dead = []
        for c in list(_clients):
            if role and c["role"] != role:
                continue
            try:
                await c["ws"].send_json(payload)
            except Exception:
                dead.append(c)
        for c in dead:
            if c in _clients:
                _clients.remove(c)
    asyncio.run_coroutine_threadsafe(_send(), _loop)


@app.on_event("startup")
async def _startup():
    global _loop
    _loop = asyncio.get_running_loop()
    config.load()
    speech.has_remote = lambda: any(c["role"] == "remote" for c in _clients)
    speech.on_transcript = lambda raw, spoken: _broadcast(
        {"type": "transcript", "spoken": spoken, "speaking": True})
    speech.on_idle = lambda: _broadcast({"type": "idle", "speaking": False})
    speech.on_audio = lambda wav, utt: _broadcast(
        {"type": "audio", "wav": base64.b64encode(wav).decode()}, role="remote")


@app.get("/health")
async def health():
    return {"ok": True, "engines": available(), "speaking": speech.speaking}


@app.post("/speak", dependencies=[Depends(require_secret)])
async def speak(body: SpeakBody):
    spoken = speech.enqueue(body.text, body.mode)
    return {"spoken": spoken}


@app.post("/say", dependencies=[Depends(require_secret)])
async def say(body: SpeakBody):
    spoken = speech.enqueue(body.text, mode="verbatim")
    return {"spoken": spoken}


@app.post("/stop", dependencies=[Depends(require_secret)])
async def stop():
    speech.interrupt()
    return {"ok": True}


@app.get("/voices", dependencies=[Depends(require_secret)])
async def voices():
    return {"engine": config.get("engine"), "voices": get_engine(config.get("engine")).list_voices()}


@app.get("/config", dependencies=[Depends(require_secret)])
async def get_config():
    return config.all()


@app.post("/config", dependencies=[Depends(require_secret)])
async def set_config(request: Request):
    patch = await request.json()
    new = config.update(patch)
    _broadcast({"type": "config", "config": new})
    return new


@app.websocket("/ws")
async def ws(websocket: WebSocket):
    await websocket.accept()
    client = {"ws": websocket, "role": "control"}
    proxied = bool(websocket.headers.get("x-forwarded-for") or websocket.headers.get("cf-connecting-ip"))
    secret = config.get("shared_secret") if proxied else ""  # local WS is exempt (same as REST)
    # First frame may be a hello carrying {secret?, role?}. Required only for proxied/tunneled clients.
    try:
        first = await asyncio.wait_for(websocket.receive_json(), timeout=5)
        if first.get("type") == "hello":
            if secret and first.get("secret") != secret:
                await websocket.close(code=4401)
                return
            client["role"] = "remote" if first.get("role") == "remote" else "control"
            first = None  # consumed
    except asyncio.TimeoutError:
        first = None
        if secret:
            await websocket.close(code=4401)
            return
    except Exception:
        await websocket.close(code=4401)
        return

    _clients.append(client)
    await websocket.send_json({"type": "config", "config": config.all()})
    try:
        pending = first
        while True:
            msg = pending if pending else await websocket.receive_json()
            pending = None
            if not msg:
                continue
            t = msg.get("type")
            if t == "speak":
                speech.enqueue(msg.get("text", ""), msg.get("mode"))
            elif t == "say":
                speech.enqueue(msg.get("text", ""), mode="verbatim")
            elif t == "stop":
                speech.interrupt()
            elif t == "config":
                new = config.update(msg.get("config", {}))
                _broadcast({"type": "config", "config": new})
            # t == "mic": reserved for streaming STT (listening side)
    except WebSocketDisconnect:
        pass
    finally:
        if client in _clients:
            _clients.remove(client)


if os.path.isdir(WEB_DIR):
    app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
