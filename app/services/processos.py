import hashlib
import uuid
from datetime import datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.adapters.base import AdapterError
from app.adapters.registry import get_adapter
from app.cnj import clean_cnj, identificar_tribunal
from app.datas import parse_data_fonte
from app.models import Client, Consultation, Process, ProcessMovement
from app.schemas import ProcessoCreate


class ProcessoInvalidoError(Exception):
    pass


class TribunalNaoSuportadoError(Exception):
    def __init__(self, tribunal: str | None):
        self.tribunal = tribunal
        super().__init__(f"Tribunal não suportado: {tribunal or 'desconhecido'}")


class ProcessoJaExisteError(Exception):
    pass


def _movimento_hash(numero: str, data_raw: str | None, descricao: str) -> str:
    chave = f"{numero}|{data_raw or ''}|{descricao}"
    return hashlib.sha256(chave.encode("utf-8")).hexdigest()


def criar_processo(db: Session, tenant_id: uuid.UUID, payload: ProcessoCreate) -> Process:
    numero = clean_cnj(payload.numero)
    if len(numero) != 20:
        raise ProcessoInvalidoError("numero deve ser um CNJ válido (20 dígitos)")

    tribunal = identificar_tribunal(numero)
    if get_adapter(tribunal) is None:
        raise TribunalNaoSuportadoError(tribunal)

    client = None
    if payload.cliente and (payload.cliente.external_id or payload.cliente.nome):
        client = (
            db.query(Client)
            .filter(Client.tenant_id == tenant_id, Client.external_id == payload.cliente.external_id)
            .first()
        )
        if client is None:
            client = Client(
                tenant_id=tenant_id,
                external_id=payload.cliente.external_id,
                name=payload.cliente.nome or payload.cliente.external_id or "Sem nome",
            )
            db.add(client)
            db.flush()

    processo = Process(
        tenant_id=tenant_id,
        client_id=client.id if client else None,
        number=numero,
        tribunal=tribunal,
        status="monitorando" if payload.monitoramento.ativo else "pausado",
        monitoring_active=payload.monitoramento.ativo,
        monitoring_interval_minutes=payload.monitoramento.intervalo_minutos,
    )
    db.add(processo)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ProcessoJaExisteError(
            "Já existe um processo cadastrado com este número para este tenant"
        ) from exc
    db.refresh(processo)
    return processo


def executar_consulta(db: Session, processo: Process) -> Consultation:
    """Consulta a fonte do tribunal do processo, persiste o histórico e deduplica
    movimentações novas (PRD seção 13: hash de processo+data+descrição)."""
    consulta = Consultation(process_id=processo.id, started_at=datetime.utcnow(), status="pending")
    db.add(consulta)
    db.commit()

    adapter = get_adapter(processo.tribunal)
    if adapter is None:
        consulta.status = "parser_error"
        consulta.error = f"Tribunal não suportado: {processo.tribunal}"
        consulta.finished_at = datetime.utcnow()
        db.commit()
        return consulta

    try:
        resultado = adapter.consultar_processo(processo.number)
    except AdapterError as exc:
        consulta.status = exc.status
        consulta.error = str(exc)
        consulta.finished_at = datetime.utcnow()
        db.commit()
        return consulta
    except Exception as exc:  # falha inesperada do adapter não deve derrubar a API
        consulta.status = "parser_error"
        consulta.error = f"Erro inesperado no adapter: {exc}"
        consulta.finished_at = datetime.utcnow()
        db.commit()
        return consulta

    hashes_existentes = {
        row.hash for row in db.query(ProcessMovement.hash).filter(ProcessMovement.process_id == processo.id)
    }

    novas = 0
    ultima_data = processo.last_movement_at
    for mov in resultado.movimentacoes:
        h = _movimento_hash(processo.number, mov.data_raw, mov.descricao)
        if h in hashes_existentes:
            continue
        hashes_existentes.add(h)

        data_parseada = parse_data_fonte(mov.data_raw)
        db.add(
            ProcessMovement(
                process_id=processo.id,
                external_id=mov.external_id,
                date=data_parseada,
                date_raw=mov.data_raw,
                type=mov.tipo,
                description=mov.descricao,
                hash=h,
            )
        )
        novas += 1
        if data_parseada and (ultima_data is None or data_parseada > ultima_data):
            ultima_data = data_parseada

    processo.last_checked_at = datetime.utcnow()
    if ultima_data:
        processo.last_movement_at = ultima_data

    consulta.status = "success"
    consulta.source = resultado.fonte
    consulta.new_movements_count = novas
    consulta.finished_at = datetime.utcnow()

    db.commit()
    db.refresh(consulta)
    return consulta
