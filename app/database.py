from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings

connect_args = {"sslmode": "require"} if settings.db_require_ssl else {}

# Teto de conexões: no máximo 30 simultâneas (20 fixas + 10 de pico). Acima disso a
# requisição espera até 30s e falha, em vez de abrir conexões sem limite e derrubar o banco.
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_size=20,
    max_overflow=10,
    pool_timeout=30,
    connect_args=connect_args,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
