import json
import time
from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from .. import config, db
from ..auth import User, require_user
from ..parsers import (
    Fit,
    ParseError,
    parse_dna,
    parse_eft,
    parse_killmail,
    parse_pyfa_xml,
)
from ..sde import loader as sde

router = APIRouter()
templates = Jinja2Templates(directory=str(config.TEMPLATES_DIR))


# --- Browse -----------------------------------------------------------------

@router.get("/", response_class=HTMLResponse)
async def index(request: Request, user: User = Depends(require_user)):
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT id, name, ship_type_id, ship_type_name, owner_name, updated_at "
            "FROM fittings ORDER BY updated_at DESC LIMIT 60"
        ).fetchall()
    fits = [dict(r) for r in rows]
    return templates.TemplateResponse(
        request, "index.html", {"user": user, "fits": fits},
    )


# --- Import -----------------------------------------------------------------

@router.get("/import", response_class=HTMLResponse)
async def import_page(request: Request, user: User = Depends(require_user)):
    return templates.TemplateResponse(request, "import.html", {"user": user, "error": None})


def _store_fit(fit: Fit, owner_id: int, owner_name: str) -> int:
    now = int(time.time())
    with db.connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO fittings
                (name, description, ship_type_id, ship_type_name, fit_json,
                 owner_id, owner_name, tags, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, '[]', ?, ?)
            """,
            (
                fit.name,
                fit.description,
                fit.ship_type_id,
                fit.ship_type_name,
                json.dumps(fit.to_dict()),
                owner_id,
                owner_name,
                now,
                now,
            ),
        )
        return int(cur.lastrowid)


@router.post("/import", response_class=HTMLResponse)
async def import_submit(
    request: Request,
    user: User = Depends(require_user),
    fmt: str = Form(...),
    text: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
):
    try:
        if fmt == "eft":
            if not text:
                raise ParseError("Paste an EFT fit block")
            fit_id = _store_fit(parse_eft(text), user.character_id, user.character_name)
            return RedirectResponse(f"/fit/{fit_id}", status_code=303)

        if fmt == "dna":
            if not text:
                raise ParseError("Paste a DNA string or <url=fitting:...> link")
            fit_id = _store_fit(parse_dna(text), user.character_id, user.character_name)
            return RedirectResponse(f"/fit/{fit_id}", status_code=303)

        if fmt == "killmail":
            if not text:
                raise ParseError("Paste killmail JSON")
            fit_id = _store_fit(parse_killmail(text), user.character_id, user.character_name)
            return RedirectResponse(f"/fit/{fit_id}", status_code=303)

        if fmt == "xml":
            if file is None:
                raise ParseError("Attach a pyfa XML file")
            payload = await file.read()
            fits = parse_pyfa_xml(payload)
            first_id = None
            for f in fits:
                fid = _store_fit(f, user.character_id, user.character_name)
                first_id = first_id or fid
            if first_id is None:
                raise ParseError("XML contained no fittings")
            if len(fits) == 1:
                return RedirectResponse(f"/fit/{first_id}", status_code=303)
            return RedirectResponse("/", status_code=303)

        raise HTTPException(400, f"Unknown format: {fmt}")

    except ParseError as exc:
        return templates.TemplateResponse(
            request, "import.html",
            {"user": user, "error": str(exc)},
            status_code=400,
        )


# --- View + delete ----------------------------------------------------------

@router.get("/fit/{fit_id}", response_class=HTMLResponse)
async def fit_view(fit_id: int, request: Request, user: User = Depends(require_user)):
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM fittings WHERE id = ?", (fit_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "Fit not found")

    fit_data = json.loads(row["fit_json"])
    slot_layout = sde.ship_slot_layout(row["ship_type_id"])
    can_edit = user.character_id == row["owner_id"] or user.is_director

    return templates.TemplateResponse(
        request, "fit.html",
        {
            "user": user,
            "row": dict(row),
            "fit": fit_data,
            "layout": slot_layout,
            "can_edit": can_edit,
        },
    )


@router.post("/fit/{fit_id}/delete")
async def fit_delete(fit_id: int, user: User = Depends(require_user)):
    with db.connect() as conn:
        row = conn.execute("SELECT owner_id FROM fittings WHERE id = ?", (fit_id,)).fetchone()
        if row is None:
            raise HTTPException(404, "Fit not found")
        if row["owner_id"] != user.character_id and not user.is_director:
            raise HTTPException(403, "Not your fit")
        conn.execute("DELETE FROM fittings WHERE id = ?", (fit_id,))
    return RedirectResponse("/", status_code=303)
