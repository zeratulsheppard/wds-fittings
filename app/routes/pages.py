from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from .. import config, db
from ..auth import User, require_user

router = APIRouter()
templates = Jinja2Templates(directory=str(config.TEMPLATES_DIR))


@router.get("/", response_class=HTMLResponse)
async def index(request: Request, user: User = Depends(require_user)):
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT id, name, ship_type_id, ship_type_name, owner_name, updated_at "
            "FROM fittings ORDER BY updated_at DESC LIMIT 60"
        ).fetchall()
    fits = [dict(r) for r in rows]
    return templates.TemplateResponse(
        request,
        "index.html",
        {"user": user, "fits": fits},
    )


@router.get("/import", response_class=HTMLResponse)
async def import_page(request: Request, user: User = Depends(require_user)):
    return templates.TemplateResponse(
        request,
        "import.html",
        {"user": user},
    )
