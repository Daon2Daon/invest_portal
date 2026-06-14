from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.db import engine
from app.bootstrap import ensure_schema
from app.routers import assets, holdings, portfolio, fx, settings as settings_router, cash

STATIC_DIR = Path(__file__).parent / "static"
UI_DIR = STATIC_DIR / "ui"


@asynccontextmanager
async def lifespan(app: FastAPI):
    await ensure_schema(engine)   # 부팅 시 invest 스키마/테이블 멱등 생성
    yield
    await engine.dispose()


app = FastAPI(title="invest_portal", lifespan=lifespan)

# 개발 시 Vite dev 서버(5173)에서 직접 호출하는 경우를 위해 허용.
# 프로덕션(Docker)에서는 FastAPI가 SPA를 같은 오리진으로 서빙하므로 CORS가 불필요하다.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"], allow_headers=["*"],
)

for r in (assets.router, holdings.router, portfolio.router, fx.router, settings_router.router, cash.router):
    app.include_router(r)


@app.get("/health")
async def health():
    return {"status": "ok"}


# --- React SPA 서빙 (빌드 산출물은 app/static/ui, Vite base=/static/ui/) ---
if STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
async def index():
    index_file = UI_DIR / "index.html"
    if not index_file.exists():
        return JSONResponse(
            status_code=503,
            content={"detail": "UI가 아직 빌드되지 않았습니다. frontend에서 npm run build 후 사용하세요."},
        )
    return FileResponse(str(index_file))


@app.get("/{full_path:path}")
async def spa_fallback(full_path: str):
    """클라이언트 사이드 라우팅(/assets, /holdings 등)을 위한 SPA 폴백.
    /api·/static·/health·/docs·/openapi.json 은 위 라우트/마운트가 먼저 처리하므로,
    여기 도달한 그런 경로는 매칭 실패로 보고 404를 반환한다."""
    if full_path.startswith(("api", "static", "health", "docs", "redoc", "openapi.json")):
        return JSONResponse(status_code=404, content={"detail": "Not Found"})
    index_file = UI_DIR / "index.html"
    if not index_file.exists():
        return JSONResponse(
            status_code=503,
            content={"detail": "UI가 아직 빌드되지 않았습니다. frontend에서 npm run build 후 사용하세요."},
        )
    return FileResponse(str(index_file))
