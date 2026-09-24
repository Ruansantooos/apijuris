"""Contrato comum que todo adapter de tribunal/fonte deve implementar (PRD seção 11).

A API nunca deve ficar acoplada à implementação de uma fonte específica: o serviço de
consulta só conhece `TribunalAdapter`, nunca `TJSPAdapter` diretamente.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


class AdapterError(Exception):
    """Erro base de adapter. `status` deve corresponder a um dos estados do PRD (seção 15)."""

    status = "parser_error"


class InvalidProcessError(AdapterError):
    status = "invalid_process"


class NotFoundError(AdapterError):
    status = "not_found"


class SourceTimeoutError(AdapterError):
    status = "timeout"


class SourceUnavailableError(AdapterError):
    status = "source_unavailable"


class CaptchaRequiredError(AdapterError):
    status = "captcha_required"


class RateLimitedError(AdapterError):
    status = "rate_limited"


class ParserError(AdapterError):
    status = "parser_error"


@dataclass
class Movimentacao:
    descricao: str
    data_raw: str | None = None
    tipo: str | None = None
    external_id: str | None = None


@dataclass
class ConsultaResultado:
    numero: str
    tribunal: str
    fonte: str
    classe: str = "N/A"
    assunto: str = "N/A"
    partes: list[dict] = field(default_factory=list)
    movimentacoes: list[Movimentacao] = field(default_factory=list)


class TribunalAdapter(ABC):
    @abstractmethod
    def consultar_processo(self, numero: str) -> ConsultaResultado:
        """Consulta a fonte e retorna metadados + movimentações do processo."""
        raise NotImplementedError

    def obter_movimentacoes(self, numero: str) -> list[Movimentacao]:
        return self.consultar_processo(numero).movimentacoes
