"""EVE Online SSO (OAuth2) integration.

Flow:
  /sso/login  -> redirects to EVE authorize
  /sso/callback -> exchanges code, verifies JWT via EVE JWKS, checks corp
                   membership, fetches roles+titles, stores in session
  /sso/logout -> clears session
"""
from __future__ import annotations

import base64
import re
import secrets
import time
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

import httpx
import jwt
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from . import config

router = APIRouter(prefix="/sso", tags=["sso"])

AUTHORIZE_URL = "https://login.eveonline.com/v2/oauth/authorize"
TOKEN_URL = "https://login.eveonline.com/v2/oauth/token"
JWKS_URL = "https://login.eveonline.com/oauth/jwks"
ESI = "https://esi.evetech.net/latest"

# Default scope set — matches what we told the EVE dev app to request.
DEFAULT_SCOPES = [
    "publicData",
    "esi-characters.read_corporation_roles.v1",
    "esi-characters.read_titles.v1",
    "esi-corporations.read_fittings.v1",
    "esi-fittings.read_fittings.v1",
    "esi-fittings.write_fittings.v1",
]

_COLOR_TAG = re.compile(r"</?(?:color|b|i|u)[^>]*>", re.IGNORECASE)


def _strip_title_markup(name: str) -> str:
    """EVE corp titles carry inline XML colour tags — strip them for comparison."""
    return _COLOR_TAG.sub("", name or "").strip()


# --- JWKS cache -------------------------------------------------------------

_jwks_cache: Dict[str, Any] = {"at": 0.0, "keys": None}


async def _get_jwks(client: httpx.AsyncClient) -> Any:
    now = time.time()
    if _jwks_cache["keys"] and now - _jwks_cache["at"] < 3600:
        return _jwks_cache["keys"]
    r = await client.get(JWKS_URL, timeout=10)
    r.raise_for_status()
    _jwks_cache["keys"] = jwt.PyJWKSet.from_dict(r.json())
    _jwks_cache["at"] = now
    return _jwks_cache["keys"]


async def _verify_access_token(access_token: str, client: httpx.AsyncClient) -> Dict[str, Any]:
    """Verify the EVE access token JWT and return its claims."""
    jwks = await _get_jwks(client)
    unverified = jwt.get_unverified_header(access_token)
    key = jwks[unverified["kid"]].key
    return jwt.decode(
        access_token,
        key=key,
        algorithms=[unverified.get("alg", "RS256")],
        issuer=["login.eveonline.com", "https://login.eveonline.com"],
        audience="EVE Online",
    )


def _basic_auth_header() -> str:
    creds = f"{config.EVE_CLIENT_ID}:{config.EVE_CLIENT_SECRET}".encode()
    return "Basic " + base64.b64encode(creds).decode()


# --- Routes -----------------------------------------------------------------


@router.get("/login")
async def login(request: Request, next: Optional[str] = None):
    if not config.EVE_CLIENT_ID or not config.EVE_CLIENT_SECRET:
        raise HTTPException(500, "EVE_CLIENT_ID / EVE_CLIENT_SECRET not configured")

    state = secrets.token_urlsafe(24)
    request.session["oauth_state"] = state
    request.session["oauth_next"] = next or "/"

    params = {
        "response_type": "code",
        "redirect_uri": config.EVE_CALLBACK_URL,
        "client_id": config.EVE_CLIENT_ID,
        "scope": " ".join(DEFAULT_SCOPES),
        "state": state,
    }
    return RedirectResponse(f"{AUTHORIZE_URL}?{urlencode(params)}", status_code=302)


@router.get("/callback")
async def callback(request: Request, code: Optional[str] = None, state: Optional[str] = None):
    if not code or not state:
        raise HTTPException(400, "Missing code or state")
    if state != request.session.get("oauth_state"):
        raise HTTPException(400, "State mismatch — restart login")
    request.session.pop("oauth_state", None)
    next_path = request.session.pop("oauth_next", "/") or "/"

    async with httpx.AsyncClient(timeout=15) as client:
        # 1. Exchange code for tokens
        tok_r = await client.post(
            TOKEN_URL,
            headers={
                "Authorization": _basic_auth_header(),
                "Content-Type": "application/x-www-form-urlencoded",
                "Host": "login.eveonline.com",
            },
            data={"grant_type": "authorization_code", "code": code},
        )
        if tok_r.status_code != 200:
            raise HTTPException(400, f"Token exchange failed: {tok_r.text}")
        tok = tok_r.json()
        access_token: str = tok["access_token"]
        refresh_token: str = tok.get("refresh_token", "")
        expires_in: int = int(tok.get("expires_in", 1200))

        # 2. Verify JWT, extract character
        claims = await _verify_access_token(access_token, client)
        sub = claims.get("sub", "")  # "CHARACTER:EVE:91940343"
        if not sub.startswith("CHARACTER:EVE:"):
            raise HTTPException(400, "Unexpected token subject")
        character_id = int(sub.split(":")[-1])
        character_name = claims.get("name", "Capsuleer")

        # 3. Corp membership gate
        pub_r = await client.get(f"{ESI}/characters/{character_id}/")
        if pub_r.status_code != 200:
            raise HTTPException(502, "ESI character lookup failed")
        pub = pub_r.json()
        if int(pub.get("corporation_id", 0)) != config.CORP_ID:
            return HTMLResponse(
                _forbidden_page(character_name, int(pub.get("corporation_id", 0))),
                status_code=403,
            )

        # 4. Roles + titles (best-effort — may 403 if scopes not granted)
        headers = {"Authorization": f"Bearer {access_token}"}
        roles: List[str] = []
        titles: List[str] = []
        try:
            r = await client.get(f"{ESI}/characters/{character_id}/roles/", headers=headers)
            if r.status_code == 200:
                roles = list(r.json().get("roles", []) or [])
        except httpx.HTTPError:
            pass
        try:
            r = await client.get(f"{ESI}/characters/{character_id}/titles/", headers=headers)
            if r.status_code == 200:
                titles = [_strip_title_markup(t.get("name", "")) for t in (r.json() or [])]
                titles = [t for t in titles if t]
        except httpx.HTTPError:
            pass

    # 5. Store session
    request.session["user"] = {
        "character_id": character_id,
        "character_name": character_name,
        "corporation_id": int(pub.get("corporation_id", 0)),
        "roles": roles,
        "titles": titles,
        "refresh_token": refresh_token,
        "access_token": access_token,
        "access_expires_at": int(time.time()) + expires_in,
    }

    if not next_path.startswith("/"):
        next_path = "/"
    return RedirectResponse(next_path, status_code=302)


@router.post("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/", status_code=303)


@router.get("/me")
async def me(request: Request):
    u = request.session.get("user")
    if not u:
        return {"authenticated": False}
    return {
        "authenticated": True,
        "character_id": u.get("character_id"),
        "character_name": u.get("character_name"),
        "corporation_id": u.get("corporation_id"),
        "roles": u.get("roles", []),
        "titles": u.get("titles", []),
    }


def _forbidden_page(name: str, corp_id: int) -> str:
    return f"""<!DOCTYPE html>
<html><head><title>Access denied — WDS Fittings</title>
<link rel="stylesheet" href="/static/style.css"></head>
<body><main style="max-width:600px;margin:5rem auto;text-align:center">
  <h1 style="color:var(--orange)">Access denied</h1>
  <p>{name} is not a member of WiNGSPAN Delivery Services (corp {corp_id}).</p>
  <p><a href="/sso/logout" onclick="event.preventDefault();fetch('/sso/logout',{{method:'POST'}}).then(()=>location.href='/');">Log out</a></p>
</main></body></html>"""
