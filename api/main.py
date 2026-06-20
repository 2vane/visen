from __future__ import annotations
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from vsentinel import Sentinel

app = FastAPI(title="V-Sentinel")
_WEB = Path(__file__).resolve().parents[1] / "web" / "index.html"

sentinel = Sentinel()


class ChatIn(BaseModel):
    message: str


@app.post("/chat")
def chat(body: ChatIn):
    return sentinel.run(body.message)


@app.get("/", response_class=HTMLResponse)
def index():
    return _WEB.read_text(encoding="utf-8")
