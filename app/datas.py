"""Parsing tolerante de datas como vêm das fontes (e-SAJ/EPROC), sem padrão único."""
from datetime import datetime

_FORMATOS = ("%d/%m/%Y %H:%M", "%d/%m/%Y", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d")


def parse_data_fonte(valor: str | None) -> datetime | None:
    if not valor:
        return None
    valor = valor.strip()
    for formato in _FORMATOS:
        try:
            return datetime.strptime(valor, formato)
        except ValueError:
            continue
    return None
