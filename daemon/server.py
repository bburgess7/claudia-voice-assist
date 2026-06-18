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
import json
import os
from typing import List, Optional

from fastapi import (FastAPI, WebSocket, WebSocketDisconnect, Request, Header, HTTPException,
                     Depends)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import config
from . import agent
from .engines import get_engine, available
from .speech import SpeechManager

WEB_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "web", "public")

app = FastAPI(title="claudiad")
# The shared secret is the real gate when the daemon is reached over a tunnel, so wildcard CORS is
# fine (no cookies/credentials are used). Lets the Vercel-hosted UI call the tunneled daemon.
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"],
                   allow_headers=["*"], allow_credentials=False)


def _proxied(headers) -> bool:
    return bool(headers.get("x-forwarded-for") or headers.get("cf-connecting-ip")
                or headers.get("cf-access-authenticated-user-email"))


def _authorized(headers, secret_value: str = "") -> bool:
    """Decide if a request may act. Local (direct) requests are always allowed. Remote requests must
    pass EITHER Cloudflare-Access SSO (preferred, 'super secure') OR the shared secret."""
    if not _proxied(headers):
        return True                                   # direct local request
    allow = (config.get("access_email") or "").strip().lower()
    secret = config.get("shared_secret") or ""
    if not allow and not secret:
        return True                                   # no auth configured at all (open quick tunnel)
    # SSO path: Cloudflare Access injects the verified email (not forgeable through the tunnel).
    if allow:
        cf_email = (headers.get("cf-access-authenticated-user-email") or "").strip().lower()
        if cf_email and cf_email == allow:
            return True
    # secret path (quick tunnel, no SSO)
    if secret and secret_value == secret:
        return True
    return False                                      # auth configured but not satisfied -> reject


def require_secret(request: Request, x_claudia_secret: str = Header(default="")):
    """Gate actions: local is open; remote needs Cloudflare-Access SSO or the shared secret."""
    if not _authorized(request.headers, x_claudia_secret):
        raise HTTPException(status_code=401, detail="unauthorized")


speech = SpeechManager()
# each client: {"ws": WebSocket, "role": "control" | "remote"}
#   control  -> sees transcript/config only; audio plays on the host's speakers (no echo)
#   remote   -> also receives streamed audio frames to play in-browser (phone / other computer)
_clients: List[dict] = []
_loop: Optional[asyncio.AbstractEventLoop] = None


class SpeakBody(BaseModel):
    text: str
    mode: Optional[str] = None    # verbatim | summary | headline; default = config.verbosity
    prefix: Optional[str] = None  # spoken first, unsummarized (e.g. which project a Claude hook fired from)


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
    spoken = speech.enqueue(body.text, body.mode, body.prefix)
    return {"spoken": spoken}


@app.post("/say", dependencies=[Depends(require_secret)])
async def say(body: SpeakBody):
    spoken = speech.enqueue(body.text, mode="verbatim")
    return {"spoken": spoken}


@app.post("/stop", dependencies=[Depends(require_secret)])
async def stop():
    speech.interrupt()
    return {"ok": True}


STT_URL = os.environ.get("CLAUDIA_STT_URL", "http://127.0.0.1:4245")


def _run_agent(text: str):
    model = config.get("agent_model")

    def on_step(name, args):
        _broadcast({"type": "action", "tool": name, "args": args})

    result = agent.run_agent(text, model, on_step)
    spoken = result.get("spoken", "")
    if spoken:
        speech.enqueue(spoken, mode="verbatim")   # agent already wrote spoken-ready prose
    return result


@app.post("/ask", dependencies=[Depends(require_secret)])
async def ask(body: SpeakBody):
    """Agentic: Claudia uses tools to DO something, then speaks the result."""
    return await asyncio.to_thread(_run_agent, body.text)


@app.post("/talk", dependencies=[Depends(require_secret)])
async def talk(request: Request):
    """Voice in: raw audio -> local Whisper STT -> agent -> spoken result. Fully on-device."""
    import urllib.request as _u
    audio = await request.body()

    def _stt():
        req = _u.Request(STT_URL + "/stt", data=audio, headers={"Content-Type": "application/octet-stream"})
        with _u.urlopen(req, timeout=60) as r:
            return json.loads(r.read()).get("text", "")
    try:
        heard = await asyncio.to_thread(_stt)
    except Exception:
        return JSONResponse({"error": "stt_unavailable",
                             "hint": "Run: bash scripts/setup-listen.sh (sets up local speech-to-text)"},
                            status_code=503)
    if not heard.strip():
        return {"heard": "", "spoken": ""}
    _broadcast({"type": "heard", "text": heard})
    result = await asyncio.to_thread(_run_agent, heard)
    result["heard"] = heard
    return result


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
    remote = _proxied(websocket.headers)
    # First frame may be a hello carrying {secret?, role?}. Auth required only for remote clients
    # (local is open); remote passes via Cloudflare-Access SSO or the shared secret.
    try:
        first = await asyncio.wait_for(websocket.receive_json(), timeout=5)
        if first.get("type") == "hello":
            if not _authorized(websocket.headers, first.get("secret", "")):
                await websocket.close(code=4401)
                return
            client["role"] = "remote" if first.get("role") == "remote" else "control"
            first = None  # consumed
        elif remote and not _authorized(websocket.headers, ""):
            await websocket.close(code=4401)
            return
    except asyncio.TimeoutError:
        first = None
        if remote and not _authorized(websocket.headers, ""):
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
