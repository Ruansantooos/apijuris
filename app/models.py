import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(120))
    plan: Mapped[str] = mapped_column(String(40), default="starter")
    status: Mapped[str] = mapped_column(String(20), default="ativo")
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)


class Client(Base):
    __tablename__ = "clients"
    __table_args__ = (UniqueConstraint("tenant_id", "external_id", name="uq_client_tenant_external_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    external_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    name: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)


class Process(Base):
    __tablename__ = "processes"
    __table_args__ = (UniqueConstraint("tenant_id", "number", name="uq_process_tenant_number"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    client_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("clients.id"), nullable=True)
    number: Mapped[str] = mapped_column(String(25))
    tribunal: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default="monitorando")
    monitoring_active: Mapped[bool] = mapped_column(default=True)
    monitoring_interval_minutes: Mapped[int] = mapped_column(default=60)
    last_checked_at: Mapped[datetime | None] = mapped_column(nullable=True)
    last_movement_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

    client: Mapped["Client"] = relationship()
    movimentacoes: Mapped[list["ProcessMovement"]] = relationship(
        back_populates="process", order_by="ProcessMovement.date.desc()"
    )

    @property
    def numero(self) -> str:
        """Alias em português de `number`, exposto na API pública (ver ProcessoOut)."""
        return self.number


class ProcessMovement(Base):
    __tablename__ = "process_movements"
    __table_args__ = (UniqueConstraint("process_id", "hash", name="uq_movement_process_hash"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    process_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("processes.id"))
    external_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    date: Mapped[datetime | None] = mapped_column(nullable=True)
    date_raw: Mapped[str | None] = mapped_column(String(60), nullable=True)
    type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    description: Mapped[str] = mapped_column(Text)
    hash: Mapped[str] = mapped_column(String(64))
    raw_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

    process: Mapped["Process"] = relationship(back_populates="movimentacoes")


class Consultation(Base):
    __tablename__ = "consultations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    process_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("processes.id"))
    started_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(String(30))
    source: Mapped[str | None] = mapped_column(String(40), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_movements_count: Mapped[int] = mapped_column(default=0)

    process: Mapped["Process"] = relationship()
