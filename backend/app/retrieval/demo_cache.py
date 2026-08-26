"""
Cache em memória do RETRIEVAL (busca vetorial + grafo) das perguntas FIXAS
da demo. NÃO é um cache geral: só as perguntas conhecidas entram (whitelist).

Por quê: numa demo, as mesmas 4-5 perguntas se repetem. Guardar o contexto já
montado deixa a resposta quase instantânea (sobra só o Claude) e, de quebra,
tira essas perguntas do limite de 3 req/min da Voyage — a demo fica à prova de
rede/quota.

O QUE é guardado: o dicionário de contexto INTEIRO — candidatos, fatos, gastos,
subgrafo e, principalmente, as `consultas`. As `consultas` trazem o $vectorSearch
(com a entidade resolvida e o score) e o $lookup encadeado. Guardá-las junto é o
que faz o painel "Ver a consulta" mostrar as DUAS fases do GraphRAG idêntico a
uma execução normal, mesmo vindo do cache — a narrativa da demo não some. Só os
`tempos` (voláteis) são descartados; quem responde recoloca os seus.

INVALIDAÇÃO: o seed grava um token de versão em `app_meta` ({_id:"seed", ran_at}).
Cada consulta confere esse token com um find_one por _id (a operação mais barata
do Atlas), mas no máximo uma vez a cada _TTL_TOKEN_S segundos — assim cliques
repetidos na demo não pagam o RTT toda vez. Se o token mudou (o seed rodou), o
cache inteiro é descartado.
"""
import copy
import time
from typing import Any, Dict, Optional, Tuple

from app.core.db import get_db
from app.models.schemas import Collections as C

# Perguntas fixas da demo. Espelham EXEMPLOS em
# frontend/src/components/AskForm.tsx + o placeholder da caixa de pergunta.
# Mantidas normalizadas (minúsculas, sem espaços nas pontas). Se mudar as
# sugestões no front, atualize aqui também.
PERGUNTAS_DEMO = {
    "quanto custa nossa virtualização?",
    "o que temos de plataforma de contêineres?",
    "nossos gastos com colaboração e documentação",
    "se a licença vsphere standard 2026 expirar, quais times são impactados?",
    "quanto gastamos com a vmware por centro de custo?",
    # Prova de que não alucina: dado inexistente no banco. Cacheia só o
    # retrieval (fica à prova de quota Voyage); a RECUSA do Claude segue ao vivo,
    # então a prova continua genuína.
    "quanto gastamos com a salesforce?",
}

_TTL_TOKEN_S = 5.0  # janela em que reusamos o token do seed sem reconsultar

_cache: Dict[Tuple[str, int], Dict[str, Any]] = {}  # (pergunta_norm, k) -> contexto
_token_atual: Optional[str] = None   # token do seed sob o qual o cache é válido
_token_checado_em: float = 0.0       # última vez (monotonic) que lemos o token


def _normalizar(pergunta: str) -> str:
    return pergunta.strip().lower()


def elegivel(pergunta: str) -> bool:
    """True se a pergunta faz parte da whitelist da demo (só essas cacheiam)."""
    return _normalizar(pergunta) in PERGUNTAS_DEMO


def _seed_token(db) -> str:
    """Token de versão do seed (gravado em app_meta ao rodar o seed)."""
    doc = db[C.META].find_one({"_id": "seed"}, {"ran_at": 1})
    # Sem doc (banco nunca seedado com esta versão) -> token fixo: ainda cacheia,
    # só não se auto-invalida até o próximo seed gravar o doc.
    return str(doc.get("ran_at")) if doc else "sem-token"


def _garantir_token_valido(db) -> None:
    """
    Confere o token do seed no máximo 1x a cada _TTL_TOKEN_S. Se mudou desde a
    última vez, esvazia o cache (o seed rodou -> os dados podem ter mudado).
    """
    global _token_atual, _token_checado_em
    agora = time.monotonic()
    if _token_atual is not None and (agora - _token_checado_em) < _TTL_TOKEN_S:
        return  # dentro da janela: confia no cache sem novo RTT
    token = _seed_token(db)
    _token_checado_em = agora
    if token != _token_atual:
        _cache.clear()
        _token_atual = token


def obter(pergunta: str, k: int) -> Optional[Dict[str, Any]]:
    """Devolve uma CÓPIA do contexto cacheado, ou None se não houver hit válido."""
    if not elegivel(pergunta):
        return None
    _garantir_token_valido(get_db())
    ctx = _cache.get((_normalizar(pergunta), k))
    return copy.deepcopy(ctx) if ctx is not None else None


def guardar(pergunta: str, k: int, contexto: Dict[str, Any]) -> None:
    """Guarda uma CÓPIA do contexto (sem os tempos voláteis), se for da whitelist."""
    if not elegivel(pergunta):
        return
    _garantir_token_valido(get_db())  # fixa _token_atual antes de gravar
    copia = copy.deepcopy(contexto)
    copia.pop("tempos", None)
    _cache[(_normalizar(pergunta), k)] = copia
