import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import Base, engine
from app.routers import consultas, processos

logging.basicConfig(level=settings.log_level)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # MVP: cria as tabelas diretamente. Numa fase seguinte isso migra para Alembic.
    Base.metadata.create_all(bind=engine)
    yield


# Em produção não expõe o mapa da API (/docs, /redoc, /openapi.json).
app = FastAPI(
    title="Eproc Tracker API",
    version="1.0.0",
    lifespan=lifespan,
    docs_url=None if settings.is_production else "/docs",
    redoc_url=None if settings.is_production else "/redoc",
    openapi_url=None if settings.is_production else "/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(processos.router)
app.include_router(consultas.router)


@app.get("/health", tags=["health"])
def health():
    return {"status": "ok"}
