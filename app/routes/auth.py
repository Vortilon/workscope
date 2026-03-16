"""Authentication: CTA-style login for Scopewrath."""
from pathlib import Path

from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

router = APIRouter()
BASE = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE / "templates"))


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    # If already logged in, go to dashboard
    if request.session.get("user"):
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse("login.html", {"request": request, "error": None})


@router.post("/login", response_class=HTMLResponse)
async def login_submit(request: Request, username: str = Form(...), password: str = Form(...)):
    # Simple hard-coded credential for MVP
    if username == "admin" and password == "Tam123!":
        request.session["user"] = "admin"
        return RedirectResponse("/", status_code=303)
    error = "Invalid username or password."
    return templates.TemplateResponse("login.html", {"request": request, "error": error, "username": username})


@router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)

