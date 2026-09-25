import json
import re
import time
from typing import List, Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
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

# Tag hygiene — normalise to uppercase alnum + spaces, 1..24 chars, max 8 per fit.
_TAG_ALLOWED = re.compile(r"[^A-Z0-9 _\-]")
MAX_TAGS_PER_FIT = 8
MAX_TAG_LEN = 24
MAX_CATEGORY_LEN = 48


def _normalise_category(raw: str) -> str:
    # Titlecase-ish, strip surrounding whitespace, collapse inner spaces.
    v = re.sub(r"\s+", " ", (raw or "").strip())
    return v[:MAX_CATEGORY_LEN]


def _normalise_tag(raw: str) -> Optional[str]:
    t = _TAG_ALLOWED.sub("", (raw or "").upper()).strip()
    t = re.sub(r"\s+", " ", t)
    if not t or len(t) > MAX_TAG_LEN:
        return None
    return t


def _normalise_tag_list(raw_list: List[str]) -> List[str]:
    out: List[str] = []
    seen = set()
    for t in raw_list or []:
        n = _normalise_tag(t)
        if n and n not in seen:
            out.append(n)
            seen.add(n)
        if len(out) >= MAX_TAGS_PER_FIT:
            break
    return out


# --- Browse -----------------------------------------------------------------

@router.get("/", response_class=HTMLResponse)
async def index(
    request: Request,
    user: User = Depends(require_user),
    q: Optional[str] = None,
    tag: Optional[str] = None,
    group: Optional[int] = None,
    category: Optional[str] = None,
    mine: Optional[int] = None,
):
    where = []
    params: List = []
    if q:
        where.append("(name LIKE ? OR ship_type_name LIKE ?)")
        wildcard = f"%{q.strip()}%"
        params += [wildcard, wildcard]
    if tag:
        # tags stored as JSON array; naive LIKE match on the serialised form
        where.append("tags LIKE ?")
        params.append(f'%"{_normalise_tag(tag) or ""}"%')
    if group:
        where.append("ship_group_id = ?")
        params.append(int(group))
    if category:
        where.append("category = ?")
        params.append(_normalise_category(category))
    if mine:
        where.append("owner_id = ?")
        params.append(user.character_id)

    sql = (
        "SELECT id, name, category, ship_type_id, ship_type_name, ship_group_id, "
        "ship_group_name, owner_name, tags, updated_at "
        "FROM fittings"
    )
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY updated_at DESC LIMIT 200"

    with db.connect() as conn:
        rows = conn.execute(sql, params).fetchall()

        # Facets for the filter bar (over all fits, not just current filter)
        groups = conn.execute(
            "SELECT ship_group_id, ship_group_name, COUNT(*) AS n "
            "FROM fittings WHERE ship_group_id > 0 "
            "GROUP BY ship_group_id ORDER BY n DESC, ship_group_name"
        ).fetchall()
        categories = conn.execute(
            "SELECT category, COUNT(*) AS n FROM fittings "
            "WHERE category <> '' GROUP BY category ORDER BY category"
        ).fetchall()
        tag_rows = conn.execute("SELECT tags FROM fittings").fetchall()

    tag_counts = {}
    for r in tag_rows:
        for t in db.load_tags(r["tags"]):
            tag_counts[t] = tag_counts.get(t, 0) + 1
    top_tags = sorted(tag_counts.items(), key=lambda kv: (-kv[1], kv[0]))[:30]

    fits = []
    for r in rows:
        d = dict(r)
        d["tags"] = db.load_tags(d["tags"])
        fits.append(d)

    # Group by category when no explicit narrowing filter is active
    any_filter = bool(q or tag or group or category or mine)
    grouped: List[dict] = []
    if not any_filter:
        buckets: dict[str, List[dict]] = {}
        for f in fits:
            buckets.setdefault(f["category"] or "", []).append(f)
        # Named categories first (alphabetical), then Uncategorized
        for name in sorted(k for k in buckets if k):
            grouped.append({"name": name, "fits": buckets[name]})
        if "" in buckets:
            grouped.append({"name": "", "fits": buckets[""]})

    return templates.TemplateResponse(
        request, "index.html",
        {
            "user": user,
            "fits": fits,
            "grouped": grouped,
            "groups": [dict(g) for g in groups],
            "categories": [dict(c) for c in categories],
            "top_tags": top_tags,
            "filters": {
                "q": q or "", "tag": tag or "", "group": group or 0,
                "category": category or "", "mine": bool(mine),
                "any": any_filter,
            },
        },
    )


# --- Import -----------------------------------------------------------------

@router.get("/import", response_class=HTMLResponse)
async def import_page(request: Request, user: User = Depends(require_user)):
    return templates.TemplateResponse(request, "import.html", {"user": user, "error": None})


def _store_fit(fit: Fit, owner_id: int, owner_name: str, category: str = "") -> int:
    ship = sde.get_type(fit.ship_type_id)
    group_id = ship.group_id if ship else 0
    group_name = ship.group_name if ship else ""
    now = int(time.time())
    with db.connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO fittings
                (name, description, ship_type_id, ship_type_name,
                 ship_group_id, ship_group_name, category,
                 fit_json, owner_id, owner_name, tags,
                 created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '[]', ?, ?)
            """,
            (
                fit.name,
                fit.description,
                fit.ship_type_id,
                fit.ship_type_name,
                group_id,
                group_name,
                _normalise_category(category),
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


# --- View / tag / delete ----------------------------------------------------

def _load_fit_row(fit_id: int):
    with db.connect() as conn:
        return conn.execute("SELECT * FROM fittings WHERE id = ?", (fit_id,)).fetchone()


@router.get("/fit/{fit_id}", response_class=HTMLResponse)
async def fit_view(fit_id: int, request: Request, user: User = Depends(require_user)):
    row = _load_fit_row(fit_id)
    if row is None:
        raise HTTPException(404, "Fit not found")

    fit_data = json.loads(row["fit_json"])
    slot_layout = sde.ship_slot_layout(row["ship_type_id"])
    can_edit = user.character_id == row["owner_id"] or user.can_manage_fits
    tags = db.load_tags(row["tags"])

    return templates.TemplateResponse(
        request, "fit.html",
        {
            "user": user,
            "row": dict(row),
            "fit": fit_data,
            "layout": slot_layout,
            "can_edit": can_edit,
            "tags": tags,
        },
    )


@router.post("/fit/{fit_id}/tags")
async def fit_set_tags(fit_id: int, request: Request, user: User = Depends(require_user)):
    row = _load_fit_row(fit_id)
    if row is None:
        raise HTTPException(404, "Fit not found")
    if row["owner_id"] != user.character_id and not user.can_manage_fits:
        raise HTTPException(403, "Not your fit")

    payload = await request.json()
    incoming = payload.get("tags", [])
    if not isinstance(incoming, list):
        raise HTTPException(400, "tags must be a list")
    tags = _normalise_tag_list([str(t) for t in incoming])

    with db.connect() as conn:
        conn.execute(
            "UPDATE fittings SET tags = ?, updated_at = ? WHERE id = ?",
            (json.dumps(tags), int(time.time()), fit_id),
        )
    return JSONResponse({"tags": tags})


def _require_edit(row, user: User) -> None:
    if row["owner_id"] != user.character_id and not user.can_manage_fits:
        raise HTTPException(403, "Not your fit")


def _existing_categories() -> List[str]:
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT DISTINCT category FROM fittings WHERE category <> '' ORDER BY category"
        ).fetchall()
    return [r["category"] for r in rows]


@router.get("/fit/{fit_id}/edit", response_class=HTMLResponse)
async def fit_edit_page(fit_id: int, request: Request, user: User = Depends(require_user)):
    row = _load_fit_row(fit_id)
    if row is None:
        raise HTTPException(404, "Fit not found")
    _require_edit(row, user)
    return templates.TemplateResponse(
        request, "edit.html",
        {
            "user": user,
            "row": dict(row),
            "categories": _existing_categories(),
            "error": None,
        },
    )


@router.post("/fit/{fit_id}/edit")
async def fit_edit_submit(
    fit_id: int,
    request: Request,
    user: User = Depends(require_user),
    name: str = Form(...),
    description: str = Form(""),
    category: str = Form(""),
    fmt: Optional[str] = Form(None),
    text: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
):
    row = _load_fit_row(fit_id)
    if row is None:
        raise HTTPException(404, "Fit not found")
    _require_edit(row, user)

    name = (name or "").strip()[:120]
    description = (description or "").strip()[:2000]
    category = _normalise_category(category)
    if not name:
        return templates.TemplateResponse(
            request, "edit.html",
            {"user": user, "row": dict(row), "categories": _existing_categories(), "error": "Name is required"},
            status_code=400,
        )

    new_fit_json = None
    new_ship_type_id = None
    new_ship_type_name = None
    new_ship_group_id = None
    new_ship_group_name = None

    try:
        parsed: Optional[Fit] = None
        if fmt == "eft" and text:
            parsed = parse_eft(text)
        elif fmt == "dna" and text:
            parsed = parse_dna(text)
        elif fmt == "killmail" and text:
            parsed = parse_killmail(text)
        elif fmt == "xml" and file is not None:
            payload = await file.read()
            fits = parse_pyfa_xml(payload)
            if not fits:
                raise ParseError("XML contained no fittings")
            parsed = fits[0]

        if parsed is not None:
            # Preserve the user-entered name/description over anything the paste carried.
            parsed.name = name
            parsed.description = description
            new_fit_json = json.dumps(parsed.to_dict())
            new_ship_type_id = parsed.ship_type_id
            new_ship_type_name = parsed.ship_type_name
            ship_info = sde.get_type(parsed.ship_type_id)
            new_ship_group_id = ship_info.group_id if ship_info else 0
            new_ship_group_name = ship_info.group_name if ship_info else ""
    except ParseError as exc:
        return templates.TemplateResponse(
            request, "edit.html",
            {"user": user, "row": dict(row), "categories": _existing_categories(), "error": str(exc)},
            status_code=400,
        )

    now = int(time.time())
    with db.connect() as conn:
        if new_fit_json is not None:
            conn.execute(
                """
                UPDATE fittings
                SET name = ?, description = ?, category = ?, fit_json = ?,
                    ship_type_id = ?, ship_type_name = ?,
                    ship_group_id = ?, ship_group_name = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    name, description, category, new_fit_json,
                    new_ship_type_id, new_ship_type_name,
                    new_ship_group_id, new_ship_group_name,
                    now, fit_id,
                ),
            )
        else:
            # Rename / description / category only — also refresh the stored
            # fit_json name so the fit view header stays in sync with the DB.
            try:
                fit_data = json.loads(row["fit_json"])
                fit_data["name"] = name
                fit_data["description"] = description
                embedded_json = json.dumps(fit_data)
            except (json.JSONDecodeError, TypeError):
                embedded_json = row["fit_json"]
            conn.execute(
                "UPDATE fittings SET name = ?, description = ?, category = ?, "
                "fit_json = ?, updated_at = ? WHERE id = ?",
                (name, description, category, embedded_json, now, fit_id),
            )

    return RedirectResponse(f"/fit/{fit_id}", status_code=303)


@router.post("/fit/{fit_id}/delete")
async def fit_delete(fit_id: int, user: User = Depends(require_user)):
    row = _load_fit_row(fit_id)
    if row is None:
        raise HTTPException(404, "Fit not found")
    if row["owner_id"] != user.character_id and not user.can_manage_fits:
        raise HTTPException(403, "Not your fit")
    with db.connect() as conn:
        conn.execute("DELETE FROM fittings WHERE id = ?", (fit_id,))
    return RedirectResponse("/", status_code=303)
