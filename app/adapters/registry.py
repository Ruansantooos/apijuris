from app.adapters.base import TribunalAdapter
from app.adapters.tjsp import TJSPAdapter

_ADAPTERS: dict[str, TribunalAdapter] = {
    "TJSP": TJSPAdapter(),
}


def get_adapter(tribunal: str) -> TribunalAdapter | None:
    return _ADAPTERS.get(tribunal)


def tribunais_suportados() -> list[str]:
    return sorted(_ADAPTERS.keys())
