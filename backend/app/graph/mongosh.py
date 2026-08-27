"""
Formata pipelines de agregação e chamadas find() como comandos prontos para
colar no mongosh. É só APRESENTAÇÃO: a string gerada espelha exatamente o que
o backend executa — o objetivo é o público técnico ver o comando por trás do
resultado, não a gente inventar um pipeline "bonito".

Por que um serializador próprio e não o bson.json_util?
  O Extended JSON renderiza ObjectId como {"$oid": "..."} e datas como
  {"$date": ...}. É válido, mas não é o que se digita no mongosh. Aqui geramos
  ObjectId("...") e ISODate("..."), então copiar e colar funciona direto.
"""
from datetime import datetime
from typing import Any, List

from bson import ObjectId

# Dois espaços de indentação por nível (deixa o pipeline legível na tela).
_IND = "  "

# O vetor de embedding é gigante (1024 números). Em vez de despejá-lo na tela,
# mostramos um marcador — quem lê entende que ali entra o vetor da pergunta.
_LIMIAR_VETOR = 50
_PLACEHOLDER_VETOR = '"<embedding de 1024 dimensões da pergunta>"'


def _e_vetor_de_embedding(valor: Any) -> bool:
    """True se for uma lista longa só de números (o queryVector da busca)."""
    return (
        isinstance(valor, list)
        and len(valor) > _LIMIAR_VETOR
        and all(isinstance(x, (int, float)) for x in valor)
    )


def _string(s: str) -> str:
    """String entre aspas duplas, com escape do necessário."""
    esc = s.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{esc}"'


def _valor(v: Any, nivel: int) -> str:
    """Serializa um valor Python para a sintaxe do mongosh (JavaScript)."""
    if _e_vetor_de_embedding(v):
        return _PLACEHOLDER_VETOR
    if isinstance(v, bool):
        return "true" if v else "false"
    if v is None:
        return "null"
    if isinstance(v, ObjectId):
        return f'ObjectId("{v}")'
    if isinstance(v, datetime):
        return f'ISODate("{v.isoformat()}")'
    if isinstance(v, (int, float)):
        return repr(v)
    if isinstance(v, str):
        return _string(v)
    if isinstance(v, list):
        return _lista(v, nivel)
    if isinstance(v, dict):
        return _objeto(v, nivel)
    return _string(str(v))


def _lista(v: List[Any], nivel: int) -> str:
    if not v:
        return "[]"
    dentro = nivel + 1
    itens = [_IND * dentro + _valor(x, dentro) for x in v]
    return "[\n" + ",\n".join(itens) + "\n" + _IND * nivel + "]"


def _objeto(d: dict, nivel: int) -> str:
    if not d:
        return "{}"
    dentro = nivel + 1
    itens = [
        f"{_IND * dentro}{_string(str(k))}: {_valor(val, dentro)}"
        for k, val in d.items()
    ]
    return "{\n" + ",\n".join(itens) + "\n" + _IND * nivel + "}"


def formatar_aggregate(colecao: str, pipeline: List[dict]) -> str:
    """`db.<colecao>.aggregate([ ...estágios... ])` pronto para o mongosh."""
    return f"db.{colecao}.aggregate({_lista(pipeline, 0)})"


def formatar_finds(colecoes: List[str], limite: int = None) -> str:
    """
    Uma linha `db.<colecao>.find({})` por coleção (na ordem informada).
    Com `limite`, cada linha ganha `.limit(<n>)` — espelhando o `.limit()` real
    aplicado na execução (ver explore.full_graph).
    """
    sufixo = f".limit({limite})" if limite else ""
    return "\n".join(f"db.{c}.find({{}}){sufixo}" for c in colecoes)


def formatar_find(colecao: str, filtro: dict, sort: dict = None) -> str:
    """`db.<colecao>.find(<filtro>)` com `.sort(...)` opcional, pronto para o mongosh."""
    comando = f"db.{colecao}.find({_objeto(filtro, 0)})"
    if sort:
        comando += f".sort({_objeto(sort, 0)})"
    return comando
