import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ClienteIn(BaseModel):
    external_id: str | None = None
    nome: str | None = None


class MonitoramentoIn(BaseModel):
    ativo: bool = True
    intervalo_minutos: int = Field(default=60, ge=5)


class ProcessoCreate(BaseModel):
    numero: str
    cliente: ClienteIn | None = None
    monitoramento: MonitoramentoIn = MonitoramentoIn()


class ProcessoOut(BaseModel):
    id: uuid.UUID
    numero: str
    tribunal: str
    status: str
    monitoring_active: bool
    monitoring_interval_minutes: int
    last_checked_at: datetime | None
    last_movement_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class MovimentacaoOut(BaseModel):
    id: uuid.UUID
    external_id: str | None
    date: datetime | None
    date_raw: str | None
    type: str | None
    description: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ConsultaOut(BaseModel):
    id: uuid.UUID
    process_id: uuid.UUID
    started_at: datetime
    finished_at: datetime | None
    status: str
    source: str | None
    error: str | None
    new_movements_count: int

    model_config = {"from_attributes": True}
