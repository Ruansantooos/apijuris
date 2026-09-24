import logging

from fastapi import FastAPI

from app.config import settings
from app.database import Base, engine
from app.routers import consultas, processos

logging.basicConfig(level=settings.log_level)

app = FastAPI(title="Eproc Tracker API", version="1.0.0")

app.include_router(processos.router)
app.include_router(consultas.router)


@app.on_event("startup")
def on_startup():
    # MVP: cria as tabelas diretamente. Numa fase seguinte isso migra para Alembic,
    # quando o schema passar a evoluir com mais frequência (fila, webhooks, api_keys).
    Base.metadata.create_all(bind=engine)


@app.get("/health")
def health():
    return {"status": "ok"}
