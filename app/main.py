from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db import engine
from app.bootstrap import ensure_schema
from app.routers import assets, holdings, portfolio, fx, settings as settings_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    await ensure_schema(engine)   # 부팅 시 invest 스키마/테이블 멱등 생성
    yield
    await engine.dispose()


app = FastAPI(title="invest_portal", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],   # Vite dev 서버
    allow_methods=["*"], allow_headers=["*"],
)

for r in (assets.router, holdings.router, portfolio.router, fx.router, settings_router.router):
    app.include_router(r)


@app.get("/health")
async def health():
    return {"status": "ok"}
