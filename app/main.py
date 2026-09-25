from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from starlette.middleware.sessions import SessionMiddleware

from . import config, db, sso
from .routes import pages

app = FastAPI(title="WDS Fittings", docs_url=None, redoc_url=None)

if not config.SESSION_SECRET:
    raise RuntimeError("SESSION_SECRET is required (generate one with: python -c 'import secrets;print(secrets.token_hex(32))')")

app.add_middleware(
    SessionMiddleware,
    secret_key=config.SESSION_SECRET,
    session_cookie="wdsfit",
    max_age=60 * 60 * 24 * 7,  # 7 days
    same_site="lax",
    https_only=not config.DEV_CHARACTER_ID,
)

app.mount("/static", StaticFiles(directory=str(config.STATIC_DIR)), name="static")

app.include_router(sso.router)
app.include_router(pages.router)


@app.on_event("startup")
async def _startup() -> None:
    db.init_db()


@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse({"ok": True})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=config.PORT, reload=True)
