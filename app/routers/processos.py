import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_or_create_default_tenant
from app.models import Process, ProcessMovement
from app.schemas import ConsultaOut, MovimentacaoOut, ProcessoCreate, ProcessoOut
from app.services.processos import (
    ProcessoInvalidoError,
    ProcessoJaExisteError,
    TribunalNaoSuportadoError,
    criar_processo,
    executar_consulta,
)

router = APIRouter(prefix="/v1/processos", tags=["processos"])


def _get_processo_or_404(db: Session, tenant_id: uuid.UUID, processo_id: uuid.UUID) -> Process:
    processo = (
        db.query(Process).filter(Process.id == processo_id, Process.tenant_id == tenant_id).first()
    )
    if processo is None:
        raise HTTPException(status_code=404, detail="Processo não encontrado")
    return processo


@router.post("", response_model=ProcessoOut, status_code=201)
def cadastrar_processo(payload: ProcessoCreate, db: Session = Depends(get_db)):
    tenant = get_or_create_default_tenant(db)
    try:
        processo = criar_processo(db, tenant.id, payload)
    except ProcessoInvalidoError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except TribunalNaoSuportadoError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ProcessoJaExisteError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return processo


@router.get("", response_model=list[ProcessoOut])
def listar_processos(limit: int = 50, offset: int = 0, db: Session = Depends(get_db)):
    tenant = get_or_create_default_tenant(db)
    return (
        db.query(Process)
        .filter(Process.tenant_id == tenant.id)
        .order_by(Process.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )


@router.get("/{processo_id}", response_model=ProcessoOut)
def detalhar_processo(processo_id: uuid.UUID, db: Session = Depends(get_db)):
    tenant = get_or_create_default_tenant(db)
    return _get_processo_or_404(db, tenant.id, processo_id)


@router.delete("/{processo_id}", response_model=ProcessoOut)
def desativar_processo(processo_id: uuid.UUID, db: Session = Depends(get_db)):
    tenant = get_or_create_default_tenant(db)
    processo = _get_processo_or_404(db, tenant.id, processo_id)
    processo.monitoring_active = False
    processo.status = "pausado"
    db.commit()
    db.refresh(processo)
    return processo


@router.get("/{processo_id}/movimentacoes", response_model=list[MovimentacaoOut])
def listar_movimentacoes(
    processo_id: uuid.UUID, limit: int = 50, offset: int = 0, db: Session = Depends(get_db)
):
    tenant = get_or_create_default_tenant(db)
    _get_processo_or_404(db, tenant.id, processo_id)
    return (
        db.query(ProcessMovement)
        .filter(ProcessMovement.process_id == processo_id)
        .order_by(ProcessMovement.date.desc().nullslast(), ProcessMovement.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )


@router.post("/{processo_id}/consultar", response_model=ConsultaOut, status_code=201)
def consultar_processo_agora(processo_id: uuid.UUID, db: Session = Depends(get_db)):
    tenant = get_or_create_default_tenant(db)
    processo = _get_processo_or_404(db, tenant.id, processo_id)
    return executar_consulta(db, processo)
