"""页面路由：返回完整 HTML 页面"""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


def _page(request: Request, name: str, template: str) -> HTMLResponse:
    """统一页面渲染：base.html + 内容模板"""
    return templates.TemplateResponse("base.html", {
        "request": request,
        "active_page": name,
        "content_template": template,
    })


@router.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return _page(request, "chat", "pages/chat.html")


@router.get("/chat", response_class=HTMLResponse)
async def chat_page(request: Request):
    return _page(request, "chat", "pages/chat.html")


@router.get("/challenge", response_class=HTMLResponse)
async def challenge_page(request: Request):
    return _page(request, "challenge", "pages/challenge.html")


@router.get("/progress", response_class=HTMLResponse)
async def progress_page(request: Request):
    return _page(request, "progress", "pages/progress.html")


@router.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request):
    return _page(request, "admin", "pages/admin.html")


@router.get("/qbank", response_class=HTMLResponse)
async def qbank_page(request: Request):
    return _page(request, "qbank", "pages/qbank.html")


@router.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    from config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, MAIN_MODEL, REFLECT_MODEL, QUALITY_THRESHOLD
    return templates.TemplateResponse("base.html", {
        "request": request,
        "active_page": "settings",
        "content_template": "pages/settings.html",
        "api_key": DEEPSEEK_API_KEY or "",
        "base_url": DEEPSEEK_BASE_URL,
        "main_model": MAIN_MODEL,
        "reflect_model": REFLECT_MODEL,
        "threshold": QUALITY_THRESHOLD,
    })
