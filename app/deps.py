"""Dependências compartilhadas pelas rotas.

Sem autenticação por API Key ainda (fase seguinte do roadmap). Por enquanto todo
o sistema opera sob um único tenant "default", mas todas as tabelas já carregam
tenant_id para não exigir migração de dados quando a autenticação multi-tenant
entrar (PRD seção 17).
"""
import uuid

from sqlalchemy.orm import Session

from app.models import Tenant

DEFAULT_TENANT_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


def get_or_create_default_tenant(db: Session) -> Tenant:
    tenant = db.get(Tenant, DEFAULT_TENANT_ID)
    if tenant is None:
        tenant = Tenant(id=DEFAULT_TENANT_ID, name="default", plan="starter", status="ativo")
        db.add(tenant)
        db.commit()
    return tenant
