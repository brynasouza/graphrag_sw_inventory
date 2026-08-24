"""
Formato canônico de grafo (nós + arestas) usado pelos endpoints de
visualização.

Um NÓ representa uma entidade do domínio (fornecedor, licença, projeto…).
Uma ARESTA representa um relacionamento entre duas entidades.

    node  = {"id": str, "tipo": str, "label": str, "props": {...}}
    edge  = {"source": str, "target": str, "tipo": str, "label": str|None}

Decisão de modelagem: `allocations` NÃO vira um nó. Ela é a ponte
licença↔projeto, então a representamos como uma ARESTA (licença → projeto)
com `label` = quantidade. Isso deixa o grafo bem mais legível.

Tanto `explore.py` (grafo inteiro) quanto `subgraph.py` (subgrafo de uma
resposta) usam os mesmos ajudantes daqui, para os rótulos e cores ficarem
consistentes entre as duas visualizações.
"""
from datetime import datetime
from typing import Any, Dict, List, Optional

# Tipos de relacionamento (rótulo das arestas), num só lugar.
REL_FORNECEDOR = "fornecedor"       # produto/contrato -> fornecedor
REL_CONTRATO = "contrato"           # licença -> contrato
REL_PRODUTO = "produto"             # licença -> produto
REL_ALOCACAO = "alocação"           # licença -> projeto (via allocations)
REL_TIME = "time"                   # projeto -> time
REL_CENTRO = "centro de custo"      # time -> centro de custo
REL_PROJETO = "projeto"             # servidor -> projeto


def _iso(v: Any) -> Any:
    """Converte datas em texto ISO (JSON não sabe serializar datetime cru)."""
    return v.isoformat() if isinstance(v, datetime) else v


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


# --- Ajudantes para criar cada tipo de nó com rótulo/props consistentes -----

def add_vendor(b: GraphBuilder, doc: Dict[str, Any]) -> str:
    return b.add_node(doc["_id"], "vendor", doc.get("name", ""), {})


def add_product(b: GraphBuilder, doc: Dict[str, Any]) -> str:
    return b.add_node(doc["_id"], "product", doc.get("name", ""), {})


def add_contract(b: GraphBuilder, doc: Dict[str, Any]) -> str:
    return b.add_node(doc["_id"], "contract", doc.get("reference", ""),
                      {"value": doc.get("value"), "currency": doc.get("currency")})


def add_license(b: GraphBuilder, doc: Dict[str, Any]) -> str:
    return b.add_node(doc["_id"], "license", doc.get("name", ""), {
        "expires_at": _iso(doc.get("expires_at")),
        "unit_cost": doc.get("unit_cost"),
        "currency": doc.get("currency"),
        "metric": doc.get("metric"),
    })


def add_project(b: GraphBuilder, doc: Dict[str, Any]) -> str:
    return b.add_node(doc["_id"], "project", doc.get("name", ""), {})


def add_team(b: GraphBuilder, doc: Dict[str, Any]) -> str:
    return b.add_node(doc["_id"], "team", doc.get("name", ""), {})


def add_cost_center(b: GraphBuilder, doc: Dict[str, Any]) -> str:
    return b.add_node(doc["_id"], "cost_center", doc.get("code", ""),
                      {"name": doc.get("name")})


def add_server(b: GraphBuilder, doc: Dict[str, Any]) -> str:
    return b.add_node(doc["_id"], "server", doc.get("hostname", ""),
                      {"cpu_sockets": doc.get("cpu_sockets")})


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
