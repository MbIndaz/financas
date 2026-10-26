from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import settings
from .routers import auth, account, income_entries, spendings, expenses, buckets, summary

app = FastAPI(title="Finanças API", description="API multi-user de gestão financeira", version="1.0.0")

origins = [o.strip() for o in settings.cors_origins.split(",")] if settings.cors_origins != "*" else ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api")
app.include_router(account.router, prefix="/api")
app.include_router(income_entries.router, prefix="/api")
app.include_router(spendings.router, prefix="/api")
app.include_router(expenses.router, prefix="/api")
app.include_router(buckets.router, prefix="/api")
app.include_router(buckets.movements_router, prefix="/api")
app.include_router(summary.router, prefix="/api")


# A PWA só se atualiza de forma fiável se o browser revalidar sempre estes ficheiros
# em vez de os servir da cache HTTP.
_NO_CACHE_PATHS = {"/", "/index.html", "/sw.js"}


@app.middleware("http")
async def no_cache_app_shell(request: Request, call_next):
    response = await call_next(request)
    if request.url.path in _NO_CACHE_PATHS:
        response.headers["Cache-Control"] = "no-cache"
    return response


@app.get("/api/health")
def health():
    return {"status": "ok"}


# Serve o frontend estático (PWA) na raiz, se a pasta existir (produção via Docker).
_frontend_dir = Path(__file__).resolve().parent.parent / "static"
if _frontend_dir.exists():
    app.mount("/", StaticFiles(directory=str(_frontend_dir), html=True), name="frontend")
