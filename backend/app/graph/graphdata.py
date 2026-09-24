"""
Formato canônico de grafo (nós + arestas) usado pelos endpoints de
visualização.

Um NÓ representa uma entidade do domínio (fornecedor, licença, projeto…).
Uma ARESTA representa um relacionamento entre duas entidades.

    node  = {"id": str, "tipo": str, "label": str, "props": {...}}
    edge  = {"source": str, "target": str, "tipo": str, "label": str|None}

Como agora os dados vivem numa coleção auto-referencial (`graph`), montar o
formato de exibição é quase direto: cada documento vira um nó e cada item do seu
array `arestas` vira uma aresta (source = o nó dono, target = `aresta.to`). Duas
traduções acontecem aqui:

  - `props` de exibição: expomos só os campos que a tela usa por tipo (o resto
    dos campos de negócio fica no banco, fora do payload do grafo);
  - `tipo` da aresta: no banco é um código de travessia (ex.: "produto_fornecedor");
    na tela mostramos o rótulo legível (ex.: "fornecedor") via DISPLAY_ARESTA.

Decisão de modelagem: `allocation` NÃO é um nó. Ela é a aresta licença → projeto
(tipo "alocacao") com a quantidade em `props.quantity`, exibida como `label`.

Tanto `explore.py` (grafo inteiro) quanto `subgraph.py` (subgrafo de uma
resposta) usam os mesmos ajudantes daqui, para rótulos e cores ficarem
consistentes entre as duas visualizações.
"""
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.models.schemas import EdgeTypes as E

# Tipos de relacionamento (rótulo LEGÍVEL das arestas), num só lugar.
REL_FORNECEDOR = "fornecedor"       # produto/contrato -> fornecedor
REL_CONTRATO = "contrato"           # licença -> contrato
REL_PRODUTO = "produto"             # licença -> produto
REL_ALOCACAO = "alocação"           # licença -> projeto (aresta de alocação)
REL_TIME = "time"                   # projeto -> time
REL_CENTRO = "centro de custo"      # time -> centro de custo
REL_PROJETO = "projeto"             # servidor -> projeto

# Traduz o `tipo` de armazenamento da aresta (código da travessia) no rótulo
# legível exibido no grafo.
DISPLAY_ARESTA = {
    E.PRODUTO_FORNECEDOR: REL_FORNECEDOR,
    E.CONTRATO_FORNECEDOR: REL_FORNECEDOR,
    E.LICENCA_CONTRATO: REL_CONTRATO,
    E.LICENCA_PRODUTO: REL_PRODUTO,
    E.ALOCACAO: REL_ALOCACAO,
    E.PROJETO_TIME: REL_TIME,
    E.TIME_CENTRO: REL_CENTRO,
    E.SERVIDOR_PROJETO: REL_PROJETO,
}


def _iso(v: Any) -> Any:
    """Converte datas em texto ISO (JSON não sabe serializar datetime cru)."""
    return v.isoformat() if isinstance(v, datetime) else v


def _props_exibicao(tipo: str, props: Dict[str, Any]) -> Dict[str, Any]:
    """Só os campos de `props` que a tela mostra, por tipo de nó."""
    if tipo == "contract":
        return {"value": props.get("value"), "currency": props.get("currency")}
    if tipo == "license":
        return {
            "expires_at": _iso(props.get("expires_at")),
            "unit_cost": props.get("unit_cost"),
            "currency": props.get("currency"),
            "metric": props.get("metric"),
        }
    if tipo == "cost_center":
        return {"name": props.get("name")}
    if tipo == "server":
        return {"cpu_sockets": props.get("cpu_sockets")}
    return {}  # vendor, product, project, team: sem props de exibição


class GraphBuilder:
    """Acumula nós e arestas sem duplicar, e devolve {nodes, edges}."""

    def __init__(self) -> None:
        self.nodes: List[Dict[str, Any]] = []
        self.edges: List[Dict[str, Any]] = []
        self._ids: set = set()

    def add_node(self, _id: Any, tipo: str, label: str,
                 props: Optional[Dict[str, Any]] = None) -> str:
        sid = str(_id)
        if sid not in self._ids:
            self._ids.add(sid)
            self.nodes.append(
                {"id": sid, "tipo": tipo, "label": label, "props": props or {}}
            )
        return sid

    def add_edge(self, source: Any, target: Any, tipo: str,
                 label: Optional[str] = None) -> None:
        self.edges.append(
            {"source": str(source), "target": str(target),
             "tipo": tipo, "label": label}
        )

    def result(self) -> Dict[str, List[Dict[str, Any]]]:
        """Mantém só arestas com as duas pontas existentes e sem repetição."""
        vistas: set = set()
        arestas: List[Dict[str, Any]] = []
        for e in self.edges:
            if e["source"] not in self._ids or e["target"] not in self._ids:
                continue
            chave = (e["source"], e["target"], e["tipo"])
            if chave in vistas:
                continue
            vistas.add(chave)
            arestas.append(e)
        return {"nodes": self.nodes, "edges": arestas}


# --- Ajudantes: um documento de `graph` vira nó + arestas de exibição --------

def add_node_doc(b: GraphBuilder, node: Dict[str, Any]) -> str:
    """Adiciona ao builder um documento da coleção `graph` (com props de exibição)."""
    tipo = node.get("tipo", "")
    return b.add_node(
        node["_id"], tipo, node.get("label", ""),
        _props_exibicao(tipo, node.get("props") or {}),
    )


def add_edge_doc(b: GraphBuilder, source_id: Any, aresta: Dict[str, Any]) -> None:
    """Adiciona ao builder uma aresta embutida (`{to, tipo, props}`) do nó `source_id`."""
    tipo_arm = aresta.get("tipo", "")
    props = aresta.get("props") or {}
    # Só a aresta de alocação carrega rótulo (a quantidade).
    label = str(props.get("quantity")) if tipo_arm == E.ALOCACAO else None
    b.add_edge(source_id, aresta["to"], DISPLAY_ARESTA.get(tipo_arm, tipo_arm), label)


def merge(subgrafos: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """Une vários subgrafos {nodes, edges} deduplicando por id / (src,tgt,tipo)."""
    nodes: Dict[str, Any] = {}
    edges: Dict[Any, Any] = {}
    for g in subgrafos:
        for n in g.get("nodes", []):
            nodes[n["id"]] = n
        for e in g.get("edges", []):
            edges[(e["source"], e["target"], e["tipo"])] = e
    return {"nodes": list(nodes.values()), "edges": list(edges.values())}
