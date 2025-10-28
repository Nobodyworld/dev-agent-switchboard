"""UI routes for serving the operator dashboard."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from jinja2 import Environment, FileSystemLoader, select_autoescape

router = APIRouter()

TEMPLATE_ROOT = Path(__file__).resolve().parents[3] / "web" / "templates"
templates = Environment(
    loader=FileSystemLoader(str(TEMPLATE_ROOT)),
    autoescape=select_autoescape(enabled_extensions=("html", "xml")),
)


@router.get("/", response_class=HTMLResponse)
async def index(_request: Request) -> str:
    tmpl = templates.get_template("index.html")
    return tmpl.render()
