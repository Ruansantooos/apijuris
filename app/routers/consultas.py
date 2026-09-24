import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_or_create_default_tenant
from app.models import Consultation, Process
from app.schemas import ConsultaOut

router = APIRouter(prefix="/v1/consultas", tags=["consultas"])


@router.get("/{consulta_id}", response_model=ConsultaOut)
def detalhar_consulta(consulta_id: uuid.UUID, db: Session = Depends(get_db)):
    tenant = get_or_create_default_tenant(db)
    consulta = (
        db.query(Consultation)
        .join(Process, Process.id == Consultation.process_id)
        .filter(Consultation.id == consulta_id, Process.tenant_id == tenant.id)
        .first()
    )
    if consulta is None:
        raise HTTPException(status_code=404, detail="Consulta não encontrada")
    return consulta
