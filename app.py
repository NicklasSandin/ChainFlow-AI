from __future__ import annotations

import asyncio
import json
import os
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from playwright.async_api import BrowserContext, Page, Playwright, async_playwright

APP = FastAPI(title="ChainFlow AI")

PROVIDERS = ["chatgpt", "grok", "claude", "kimi"]

HOME = {
    "chatgpt": "https://chatgpt.com/",
    "grok": "https://grok.com/",
    "claude": "https://claude.ai/",
    "kimi": "https://www.kimi.com/",
}

@dataclass
class ProviderSession:
    name: str
    page: Optional[Page] = None

@dataclass
class RelayState:
    running: bool = False
    paused: bool = False
    mode: str = "debate"
    topic: str = ""
    max_turns: int = 12
    turn: int = 0
    current_provider: int = 0
    transcript: List[dict] = field(default_factory=list)
    providers: List[str] = field(default_factory=lambda: ["chatgpt", "grok"])
    injection: Optional[str] = None
    error: Optional[str] = None

state = RelayState()
playwright: Optional[Playwright] = None
context: Optional[BrowserContext] = None
sessions: Dict[str, ProviderSession] = {}
relay_task: Optional[asyncio.Task] = None

class StartRequest(BaseModel):
    topic: str = Field(min_length=1)
    mode: str = "debate"
    providers: List[str] = ["chatgpt", "grok"]
    max_turns: int = Field(default=12, ge=1, le=100)

class InjectRequest(BaseModel):
    message: str = Field(min_length=1)

async def ensure_browser():
    global playwright, context
    if context:
        return
    playwright = await async_playwright().start()
    profile = os.path.join(os.path.dirname(__file__), ".chainflow-browser")
    context = await playwright.chromium.launch_persistent_context(
        profile,
        headless=False,
        viewport={"width": 1440, "height": 1000},
    )
    for provider in PROVIDERS:
        page = await context.new_page()
        sessions[provider] = ProviderSession(provider, page)
        await page.goto(HOME[provider], wait_until="domcontentloaded")

async def provider_ready(provider: str) -> bool:
    session = sessions.get(provider)
    return bool(session and session.page and not session.page.is_closed())

async def send_to_provider(provider: str, prompt: str) -> str:
    """Best-effort browser adapter. Selectors are isolated here because provider UIs change."""
    if not await provider_ready(provider):
        raise RuntimeError(f"{provider}: browser session is not ready")
    page = sessions[provider].page

    selectors = {
        "chatgpt": ["#prompt-textarea", "textarea"],
        "grok": ["textarea", "[contenteditable='true']"],
        "claude": ["textarea", "[contenteditable='true']"],
        "kimi": ["textarea", "[contenteditable='true']"],
    }[provider]

    box = None
    for selector in selectors:
        try:
            loc = page.locator(selector).last
            if await loc.is_visible(timeout=1500):
                box = loc
                break
        except Exception:
            pass
    if box is None:
        raise RuntimeError(f"{provider}: could not find message input; update provider adapter")

    before = await page.locator("body").inner_text()
    await box.fill(prompt)
    await box.press("Enter")

    # Wait for the DOM to change, then settle. This intentionally avoids relying on private APIs.
    await page.wait_for_timeout(1500)
    for _ in range(120):
        await asyncio.sleep(1)
        text = await page.locator("body").inner_text()
        if text != before and len(text) > len(before) + 20:
            await asyncio.sleep(1.5)
            return text[-12000:]
    raise TimeoutError(f"{provider}: response timeout")

PROMPTS = {
    "debate": "You are one participant in a structured multi-AI debate. Respond directly to the previous participant. Challenge weak assumptions, defend strong claims, and add concrete evidence or reasoning. Do not merely agree.",
    "critic": "You are the critical reviewer in a multi-AI workflow. Identify factual errors, hidden assumptions, missing edge cases, practical risks, and better alternatives. Be specific and constructive.",
    "research": "You are a research analyst. Investigate the topic from your role, distinguish known facts from assumptions, identify uncertainties, and provide actionable findings. Do not fabricate sources.",
}

async def relay_loop():
    global state
    try:
        previous = state.topic
        while state.running and state.turn < state.max_turns:
            while state.paused and state.running:
                await asyncio.sleep(.25)
            if not state.running:
                break

            if state.injection:
                previous += "\n\nUSER INJECTION:\n" + state.injection
                state.injection = None

            provider = state.providers[state.current_provider % len(state.providers)]
            role = PROMPTS.get(state.mode, PROMPTS["debate"])
            prompt = f"""{role}\n\nOriginal objective:\n{state.topic}\n\nConversation so far:\n{previous[-30000:]}\n\nProduce your next contribution. Keep it focused and do not talk about browser automation or this relay."""
            answer = await send_to_provider(provider, prompt)
            state.turn += 1
            state.transcript.append({"turn": state.turn, "provider": provider, "text": answer, "time": time.time()})
            previous += f"\n\n[{provider.upper()}]\n{answer}"
            state.current_provider += 1
    except Exception as exc:
        state.error = str(exc)
    finally:
        state.running = False

@APP.get("/", response_class=HTMLResponse)
async def index():
    return HTMLResponse(open(os.path.join(os.path.dirname(__file__), "ui.html"), encoding="utf-8").read())

@APP.post("/api/browser/start")
async def browser_start():
    await ensure_browser()
    return {"ok": True, "providers": {p: await provider_ready(p) for p in PROVIDERS}}

@APP.post("/api/relay/start")
async def relay_start(req: StartRequest):
    global relay_task, state
    if any(p not in PROVIDERS for p in req.providers) or len(req.providers) < 2:
        raise HTTPException(400, "Choose at least two supported providers")
    if state.running:
        raise HTTPException(409, "Relay already running")
    await ensure_browser()
    state = RelayState(running=True, mode=req.mode, topic=req.topic, max_turns=req.max_turns, providers=req.providers)
    relay_task = asyncio.create_task(relay_loop())
    return {"ok": True}

@APP.post("/api/relay/pause")
async def pause():
    state.paused = True
    return {"paused": True}

@APP.post("/api/relay/resume")
async def resume():
    state.paused = False
    return {"paused": False}

@APP.post("/api/relay/stop")
async def stop():
    state.running = False
    state.paused = False
    return {"stopped": True}

@APP.post("/api/relay/inject")
async def inject(req: InjectRequest):
    state.injection = req.message
    return {"ok": True}

@APP.get("/api/state")
async def get_state():
    return {
        "running": state.running,
        "paused": state.paused,
        "mode": state.mode,
        "topic": state.topic,
        "turn": state.turn,
        "max_turns": state.max_turns,
        "providers": state.providers,
        "transcript": state.transcript,
        "error": state.error,
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(APP, host="127.0.0.1", port=8765)
