from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse

from . import config, db
from .routes import pages

app = FastAPI(title="WDS Fittings", docs_url=None, redoc_url=None)

app.mount("/static", StaticFiles(directory=str(config.STATIC_DIR)), name="static")

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
