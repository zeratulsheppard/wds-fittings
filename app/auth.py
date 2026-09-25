from dataclasses import dataclass, field
from typing import List, Optional
from fastapi import Request, HTTPException, Depends
from . import config


@dataclass
class User:
    character_id: int
    character_name: str
    roles: List[str] = field(default_factory=list)
    titles: List[str] = field(default_factory=list)

    @property
    def is_director(self) -> bool:
        return "Director" in self.roles


def _split_csv(value: str) -> List[str]:
    return [p.strip() for p in value.split(",") if p.strip()] if value else []


def get_user(request: Request) -> Optional[User]:
    """Read WDS SSO gateway headers; fall back to DEV_* env vars for local runs."""
    h = request.headers
    cid_raw = h.get("x-character-id") or config.DEV_CHARACTER_ID or "0"
    try:
        cid = int(cid_raw)
    except ValueError:
        cid = 0
    if not cid:
        return None
    name = h.get("x-authenticated-user") or config.DEV_CHARACTER_NAME or "Capsuleer"
    roles = _split_csv(h.get("x-character-roles") or config.DEV_CHARACTER_ROLES)
    titles = _split_csv(h.get("x-character-titles") or config.DEV_CHARACTER_TITLES)
    return User(character_id=cid, character_name=name, roles=roles, titles=titles)


def require_user(request: Request) -> User:
    user = get_user(request)
    if user is None:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return user


def require_director(user: User = Depends(require_user)) -> User:
    if not user.is_director:
        raise HTTPException(status_code=403, detail="Directors only")
    return user
