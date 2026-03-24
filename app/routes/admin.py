"""Admin: user, operator, aircraft and engine catalogue administration."""
from pathlib import Path

from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.models.operator import Operator
from app.models.aircraft_type import AircraftType, EngineType
from app.auth import hash_password
from app.routes.web import _require_login, _require_admin

router = APIRouter(prefix="/admin", tags=["admin"])
BASE = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE / "templates"))


@router.get("/users", response_class=HTMLResponse)
async def users_list(request: Request, db: AsyncSession = Depends(get_db)):
    if (r := _require_login(request)):
        return r
    if (r := _require_admin(request)):
        return r
    result = await db.execute(select(User).order_by(User.username))
    users = result.scalars().all()
    return templates.TemplateResponse(request, "admin/users.html", {"users": users})


@router.get("/users/new", response_class=HTMLResponse)
async def user_new(request: Request):
    if (r := _require_login(request)):
        return r
    if (r := _require_admin(request)):
        return r
    return templates.TemplateResponse(request, "admin/user_form.html", {"user": None, "error": None})


@router.post("/users", response_class=HTMLResponse)
async def user_create(
    request: Request,
    username: str = Form(...),
    first_name: str = Form(...),
    last_name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    role: str = Form("auditor"),
    db: AsyncSession = Depends(get_db),
):
    if (r := _require_login(request)):
        return r
    if (r := _require_admin(request)):
        return r
    existing = (await db.execute(select(User).where(User.username == username))).scalars().first()
    if existing:
        return templates.TemplateResponse(
            request, "admin/user_form.html",
            {"user": None, "error": "Username already exists.",
             "username": username, "first_name": first_name,
             "last_name": last_name, "email": email, "role": role},
        )
    if len(password) < 8:
        return templates.TemplateResponse(
            request, "admin/user_form.html",
            {"user": None, "error": "Password must be at least 8 characters.",
             "username": username, "first_name": first_name,
             "last_name": last_name, "email": email, "role": role},
        )
    user = User(
        username=username,
        first_name=first_name,
        last_name=last_name,
        email=email,
        password_hash=hash_password(password),
        role=role,
        active=True,
    )
    db.add(user)
    await db.commit()
    return RedirectResponse("/admin/users", status_code=303)


@router.get("/users/{user_id}/edit", response_class=HTMLResponse)
async def user_edit(request: Request, user_id: int, db: AsyncSession = Depends(get_db)):
    if (r := _require_login(request)):
        return r
    if (r := _require_admin(request)):
        return r
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalars().one_or_none()
    if not user:
        return RedirectResponse("/admin/users", status_code=303)
    return templates.TemplateResponse(request, "admin/user_form.html", {"user": user, "error": None})


@router.post("/users/{user_id}", response_class=HTMLResponse)
async def user_update(
    request: Request,
    user_id: int,
    username: str = Form(...),
    first_name: str = Form(...),
    last_name: str = Form(...),
    email: str = Form(...),
    role: str = Form("auditor"),
    db: AsyncSession = Depends(get_db),
):
    if (r := _require_login(request)):
        return r
    if (r := _require_admin(request)):
        return r
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalars().one_or_none()
    if not user:
        return RedirectResponse("/admin/users", status_code=303)
    if user.username != username:
        existing = (await db.execute(select(User).where(User.username == username))).scalars().first()
        if existing:
            return templates.TemplateResponse(
                request, "admin/user_form.html",
                {"user": user, "error": "Username already exists.",
                 "username": username, "first_name": first_name,
                 "last_name": last_name, "email": email, "role": role},
            )
    user.username = username
    user.first_name = first_name
    user.last_name = last_name
    user.email = email
    user.role = role
    await db.commit()
    return RedirectResponse("/admin/users", status_code=303)


@router.get("/users/{user_id}/password", response_class=HTMLResponse)
async def user_password_page(request: Request, user_id: int, db: AsyncSession = Depends(get_db)):
    if (r := _require_login(request)):
        return r
    if (r := _require_admin(request)):
        return r
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalars().one_or_none()
    if not user:
        return RedirectResponse("/admin/users", status_code=303)
    return templates.TemplateResponse(request, "admin/user_password.html", {"user": user, "error": None})


@router.post("/users/{user_id}/password", response_class=HTMLResponse)
async def user_password_set(
    request: Request,
    user_id: int,
    password: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    if (r := _require_login(request)):
        return r
    if (r := _require_admin(request)):
        return r
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalars().one_or_none()
    if not user:
        return RedirectResponse("/admin/users", status_code=303)
    if len(password) < 8:
        return templates.TemplateResponse(
            request, "admin/user_password.html",
            {"user": user, "error": "Password must be at least 8 characters."},
        )
    user.password_hash = hash_password(password)
    await db.commit()
    return RedirectResponse("/admin/users", status_code=303)


@router.post("/users/{user_id}/toggle-active", response_class=HTMLResponse)
async def user_toggle_active(
    request: Request, user_id: int, db: AsyncSession = Depends(get_db)
):
    if (r := _require_login(request)):
        return r
    if (r := _require_admin(request)):
        return r
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalars().one_or_none()
    if not user:
        return RedirectResponse("/admin/users", status_code=303)
    if user.id == request.session.get("user_id"):
        return RedirectResponse("/admin/users?error=self", status_code=303)
    user.active = not user.active
    await db.commit()
    return RedirectResponse("/admin/users", status_code=303)


@router.post("/users/{user_id}/delete", response_class=HTMLResponse)
async def user_delete(
    request: Request, user_id: int, db: AsyncSession = Depends(get_db)
):
    if (r := _require_login(request)):
        return r
    if (r := _require_admin(request)):
        return r
    if user_id == request.session.get("user_id"):
        return RedirectResponse("/admin/users?error=self_delete", status_code=303)
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalars().one_or_none()
    if user:
        await db.delete(user)
        await db.commit()
    return RedirectResponse("/admin/users", status_code=303)


# ── Operators ─────────────────────────────────────────────────────────────────

@router.get("/operators", response_class=HTMLResponse)
async def operators_list(request: Request, db: AsyncSession = Depends(get_db)):
    if (r := _require_login(request)):
        return r
    if (r := _require_admin(request)):
        return r
    result = await db.execute(select(Operator).order_by(Operator.name))
    operators = result.scalars().all()
    return templates.TemplateResponse(request, "admin/operators.html", {"operators": operators, "error": ""})


@router.post("/operators", response_class=HTMLResponse)
async def operator_create(
    request: Request,
    name: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    if (r := _require_login(request)):
        return r
    if (r := _require_admin(request)):
        return r
    name = name.strip()
    if not name:
        result = await db.execute(select(Operator).order_by(Operator.name))
        return templates.TemplateResponse(request, "admin/operators.html",
                                          {"operators": result.scalars().all(), "error": "Name is required."})
    existing = (await db.execute(select(Operator).where(Operator.name == name))).scalars().first()
    if existing:
        result = await db.execute(select(Operator).order_by(Operator.name))
        return templates.TemplateResponse(request, "admin/operators.html",
                                          {"operators": result.scalars().all(), "error": f'Operator "{name}" already exists.'})
    db.add(Operator(name=name))
    await db.commit()
    return RedirectResponse("/admin/operators", status_code=303)


@router.post("/operators/{op_id}/edit", response_class=HTMLResponse)
async def operator_edit(
    request: Request,
    op_id: int,
    name: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    if (r := _require_login(request)):
        return r
    if (r := _require_admin(request)):
        return r
    op = (await db.execute(select(Operator).where(Operator.id == op_id))).scalars().one_or_none()
    if op:
        op.name = name.strip()
        await db.commit()
    return RedirectResponse("/admin/operators", status_code=303)


@router.post("/operators/{op_id}/delete", response_class=HTMLResponse)
async def operator_delete(
    request: Request,
    op_id: int,
    db: AsyncSession = Depends(get_db),
):
    if (r := _require_login(request)):
        return r
    if (r := _require_admin(request)):
        return r
    op = (await db.execute(select(Operator).where(Operator.id == op_id))).scalars().one_or_none()
    if op:
        await db.delete(op)
        await db.commit()
    return RedirectResponse("/admin/operators", status_code=303)


# ── Aircraft Type Catalogue ────────────────────────────────────────────────────

async def _aircraft_page(request, db, error=""):
    aircraft = (await db.execute(
        select(AircraftType).order_by(AircraftType.manufacturer, AircraftType.model)
    )).scalars().all()
    # Group by manufacturer for display
    manufacturers = sorted({a.manufacturer for a in aircraft})
    return templates.TemplateResponse(request, "admin/aircraft.html", {
        "aircraft": aircraft, "manufacturers": manufacturers, "error": error,
    })


@router.get("/aircraft", response_class=HTMLResponse)
async def aircraft_list(request: Request, db: AsyncSession = Depends(get_db)):
    if (r := _require_login(request)): return r
    if (r := _require_admin(request)): return r
    return await _aircraft_page(request, db)


@router.post("/aircraft", response_class=HTMLResponse)
async def aircraft_create(
    request: Request,
    manufacturer: str = Form(...),
    model: str = Form(...),
    series: str = Form(""),
    db: AsyncSession = Depends(get_db),
):
    if (r := _require_login(request)): return r
    if (r := _require_admin(request)): return r
    manufacturer, model, series = manufacturer.strip(), model.strip(), series.strip()
    if not manufacturer or not model:
        return await _aircraft_page(request, db, "Manufacturer and model are required.")
    db.add(AircraftType(manufacturer=manufacturer, model=model, series=series or None))
    await db.commit()
    return RedirectResponse("/admin/aircraft", status_code=303)


@router.post("/aircraft/{ac_id}/edit", response_class=HTMLResponse)
async def aircraft_edit(
    request: Request, ac_id: int,
    manufacturer: str = Form(...), model: str = Form(...), series: str = Form(""),
    db: AsyncSession = Depends(get_db),
):
    if (r := _require_login(request)): return r
    if (r := _require_admin(request)): return r
    ac = (await db.execute(select(AircraftType).where(AircraftType.id == ac_id))).scalars().one_or_none()
    if ac:
        ac.manufacturer = manufacturer.strip()
        ac.model = model.strip()
        ac.series = series.strip() or None
        await db.commit()
    return RedirectResponse("/admin/aircraft", status_code=303)


@router.post("/aircraft/{ac_id}/delete", response_class=HTMLResponse)
async def aircraft_delete(
    request: Request, ac_id: int, db: AsyncSession = Depends(get_db),
):
    if (r := _require_login(request)): return r
    if (r := _require_admin(request)): return r
    ac = (await db.execute(select(AircraftType).where(AircraftType.id == ac_id))).scalars().one_or_none()
    if ac:
        await db.delete(ac)
        await db.commit()
    return RedirectResponse("/admin/aircraft", status_code=303)


# ── Engine Type Catalogue ──────────────────────────────────────────────────────

async def _engine_page(request, db, error=""):
    engines = (await db.execute(
        select(EngineType).order_by(
            EngineType.engine_manufacturer, EngineType.engine_family, EngineType.engine_model
        )
    )).scalars().all()
    manufacturers = sorted({e.engine_manufacturer for e in engines})
    return templates.TemplateResponse(request, "admin/engines.html", {
        "engines": engines, "manufacturers": manufacturers, "error": error,
    })


@router.get("/engines", response_class=HTMLResponse)
async def engines_list(request: Request, db: AsyncSession = Depends(get_db)):
    if (r := _require_login(request)): return r
    if (r := _require_admin(request)): return r
    return await _engine_page(request, db)


@router.post("/engines", response_class=HTMLResponse)
async def engine_create(
    request: Request,
    engine_manufacturer: str = Form(...),
    engine_family: str = Form(...),
    engine_model: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    if (r := _require_login(request)): return r
    if (r := _require_admin(request)): return r
    engine_manufacturer = engine_manufacturer.strip()
    engine_family = engine_family.strip()
    engine_model = engine_model.strip()
    if not engine_manufacturer or not engine_family or not engine_model:
        return await _engine_page(request, db, "All three fields are required.")
    db.add(EngineType(engine_manufacturer=engine_manufacturer,
                      engine_family=engine_family, engine_model=engine_model))
    await db.commit()
    return RedirectResponse("/admin/engines", status_code=303)


@router.post("/engines/{eng_id}/edit", response_class=HTMLResponse)
async def engine_edit(
    request: Request, eng_id: int,
    engine_manufacturer: str = Form(...),
    engine_family: str = Form(...),
    engine_model: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    if (r := _require_login(request)): return r
    if (r := _require_admin(request)): return r
    eng = (await db.execute(select(EngineType).where(EngineType.id == eng_id))).scalars().one_or_none()
    if eng:
        eng.engine_manufacturer = engine_manufacturer.strip()
        eng.engine_family = engine_family.strip()
        eng.engine_model = engine_model.strip()
        await db.commit()
    return RedirectResponse("/admin/engines", status_code=303)


@router.post("/engines/{eng_id}/delete", response_class=HTMLResponse)
async def engine_delete(
    request: Request, eng_id: int, db: AsyncSession = Depends(get_db),
):
    if (r := _require_login(request)): return r
    if (r := _require_admin(request)): return r
    eng = (await db.execute(select(EngineType).where(EngineType.id == eng_id))).scalars().one_or_none()
    if eng:
        await db.delete(eng)
        await db.commit()
    return RedirectResponse("/admin/engines", status_code=303)
