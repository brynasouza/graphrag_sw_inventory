"""
Montagem do contexto do GraphRAG (Etapa 6).

Este é o "R" (retrieval) do RAG: junta os FATOS que o Claude vai usar
para responder. O fluxo é:

  1. Busca vetorial acha o(s) nó(s) de entrada a partir da pergunta.
  2. Para cada nó, buscamos os fatos certos no grafo:
       - licença   -> impacto (projetos, times, centros, servidores,
                      validade) + custo unitário + qual é o fornecedor;
       - fornecedor -> (marcado para o consolidado de gasto abaixo).
  3. Montamos um CONSOLIDADO de gasto por centro de custo para todo
     fornecedor envolvido — inclusive o fornecedor das licenças achadas.
     Assim, mesmo que a busca caia numa "licença", a pergunta de custo
     ("quanto gastamos com a VMware?") tem os números para ser respondida.
  4. Devolvemos tudo como um dicionário estruturado.

Regra de ouro do GraphRAG: o grafo garante os FATOS; o LLM só escreve o
texto. Por isso reunimos aqui apenas dados verificáveis do banco.
"""
from typing import Any, Dict, List, Optional, Tuple

from app.core.db import get_db
from app.graph import costs, graphdata, queries, subgraph
from app.models.schemas import Collections as C
from app.retrieval import vector_search


def _licenca_detalhe(db, license_id: str) -> Tuple[Optional[str], Optional[float], Optional[str]]:
    """Descobre (fornecedor, custo_unitario, moeda) de uma licença."""
    oid = queries.to_object_id(license_id)
    if oid is None:
        return None, None, None
    lic = db[C.LICENSES].find_one(
        {"_id": oid}, {"product_id": 1, "unit_cost": 1, "currency": 1}
    )
    if lic is None:
        return None, None, None
    prod = db[C.PRODUCTS].find_one({"_id": lic["product_id"]}, {"vendor_id": 1})
    vend = db[C.VENDORS].find_one(
        {"_id": prod["vendor_id"]}, {"name": 1}) if prod else None
    fornecedor = vend["name"] if vend else None
    return fornecedor, lic.get("unit_cost"), lic.get("currency")


def build_context(query: str, k: int = 3) -> Dict[str, Any]:
    """
    Monta o contexto para a pergunta `query`.

    Buscamos os `k` melhores candidatos e reunimos os fatos de cada um.
    O Claude usa só o que for relevante — trazer os 3 melhores deixa a
    resposta robusta mesmo quando a pergunta é ambígua.
    """
    db = get_db()
    hits = vector_search.search(query, k=k)

    fatos: List[Dict[str, Any]] = []
    fornecedores: set = set()   # fornecedores p/ o consolidado de gasto
    vistos: set = set()         # evita repetir a mesma entidade
    subgrafos: List[Dict[str, Any]] = []  # mini-grafo de cada entidade usada

    for h in hits:
        chave = (h["entity_type"], h["entity_id"])
        if chave in vistos:
            continue
        vistos.add(chave)

        if h["entity_type"] == "license":
            fornecedor, custo, moeda = _licenca_detalhe(db, h["entity_id"])
            if fornecedor:
                fornecedores.add(fornecedor)
            fatos.append({
                "tipo": "licenca",
                "nome": h["name"],
                "entity_id": h["entity_id"],
                "fornecedor": fornecedor,
                "custo_unitario": custo,
                "moeda": moeda,
                # impacto já traz validade, projetos, times, centros e servidores
                "impacto": queries.license_impact(h["entity_id"]),
            })
            subgrafos.append(subgraph.subgraph_for_license(db, h["entity_id"]))
        elif h["entity_type"] == "vendor":
            fornecedores.add(h["name"])
            fatos.append({"tipo": "fornecedor", "nome": h["name"],
                          "entity_id": h["entity_id"]})
            subgrafos.append(subgraph.subgraph_for_vendor(db, h["entity_id"]))
        else:
            fatos.append({"tipo": h["entity_type"], "nome": h["name"],
                          "entity_id": h["entity_id"]})

    # Consolidado de gasto por centro de custo, para cada fornecedor envolvido.
    gastos_por_fornecedor = [
        {
            "fornecedor": nome,
            "gasto_por_centro_de_custo": costs.cost_by_cost_center(nome),
        }
        for nome in sorted(fornecedores)
    ]

    return {
        "pergunta": query,
        "candidatos": [
            {"tipo": h["entity_type"], "nome": h["name"], "score": h["score"]}
            for h in hits
        ],
        "fatos": fatos,
        "gastos_por_fornecedor": gastos_por_fornecedor,
        # Mini-grafo consolidado: só as entidades usadas para responder.
        "subgrafo": graphdata.merge(subgrafos),
    }
