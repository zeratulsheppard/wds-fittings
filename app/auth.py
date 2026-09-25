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

    @property
    def is_fitting_manager(self) -> bool:
        """True for the Fitting_Manager corp role OR the 'Fitting Manager' title."""
        if "Fitting_Manager" in self.roles:
            return True
        return any(t.lower() == "fitting manager" for t in self.titles)

    @property
    def can_manage_fits(self) -> bool:
        """Directors and Fitting Managers can edit/delete any fit."""
        return self.is_director or self.is_fitting_manager


def _split_csv(value: str) -> List[str]:
    return [p.strip() for p in value.split(",") if p.strip()] if value else []


def get_user(request: Request) -> Optional[User]:
    """Prefer session (populated by /sso/callback); fall back to DEV_* env vars."""
    sess_user = request.session.get("user") if hasattr(request, "session") else None
    if sess_user and sess_user.get("character_id"):
        return User(
            character_id=int(sess_user["character_id"]),
            character_name=str(sess_user.get("character_name") or "Capsuleer"),
            roles=list(sess_user.get("roles") or []),
            titles=list(sess_user.get("titles") or []),
        )

    if config.DEV_CHARACTER_ID:
        try:
            cid = int(config.DEV_CHARACTER_ID)
        except ValueError:
            cid = 0
        if cid:
            return User(
                character_id=cid,
                character_name=config.DEV_CHARACTER_NAME or "Capsuleer",
                roles=_split_csv(config.DEV_CHARACTER_ROLES),
                titles=_split_csv(config.DEV_CHARACTER_TITLES),
            )

    return None


def require_user(request: Request) -> User:
    user = get_user(request)
    if user is None:
        # Redirect through /sso/login instead of 401 for browser flows
        raise HTTPException(
            status_code=302,
            headers={"Location": "/sso/login?next=" + str(request.url.path)},
        )
    return user


def require_director(user: User = Depends(require_user)) -> User:
    if not user.is_director:
        raise HTTPException(status_code=403, detail="Directors only")
    return user
