"""Utilitários para validar e interpretar números de processo no padrão CNJ."""
import re

_TJ_POR_UF = {
    "01": "TJAC", "02": "TJAL", "03": "TJAP", "04": "TJAM", "05": "TJBA",
    "06": "TJCE", "07": "TJDFT", "08": "TJES", "09": "TJGO", "10": "TJMA",
    "11": "TJMT", "12": "TJMS", "13": "TJMG", "14": "TJPA", "15": "TJPB",
    "16": "TJPR", "17": "TJPE", "18": "TJPI", "19": "TJRJ", "20": "TJRN",
    "21": "TJRS", "22": "TJRO", "23": "TJRR", "24": "TJSC", "25": "TJSE",
    "26": "TJSP", "27": "TJTO",
}


def clean_cnj(numero: str) -> str:
    return re.sub(r"\D", "", numero or "")


def formatar_cnj(clean: str) -> str:
    return (
        f"{clean[0:7]}-{clean[7:9]}.{clean[9:13]}."
        f"{clean[13:14]}.{clean[14:16]}.{clean[16:20]}"
    )


def identificar_tribunal(numero_cnj: str) -> str | None:
    """Deriva a sigla do tribunal a partir do segmento/tribunal do número CNJ (20 dígitos)."""
    clean = clean_cnj(numero_cnj)
    if len(clean) != 20:
        return None

    segmento = clean[13]
    tr = clean[14:16]

    if segmento == "8":
        return _TJ_POR_UF.get(tr)
    if segmento == "4":
        return f"TRF{int(tr)}"
    if segmento == "5":
        return f"TRT{int(tr)}"
    return None
