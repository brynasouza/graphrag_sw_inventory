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
import time
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

    # Instrumentação: mede o tempo de cada etapa (ver /ask). O search preenche
    # 'embedding_query_ms' e 'vector_search_ms'; o bloco de grafo abaixo mede
    # 'grafo_lookup_agg_ms'.
    tempos: Dict[str, float] = {}
    hits = vector_search.search(query, k=k, tempos=tempos)

    t_grafo0 = time.perf_counter()

    fatos: List[Dict[str, Any]] = []
    fornecedores: set = set()   # fornecedores p/ o consolidado de gasto
    vistos: set = set()         # evita repetir a mesma entidade
    subgrafos: List[Dict[str, Any]] = []  # mini-grafo de cada entidade usada

    # Consultas MongoDB que DE FATO rodaram, para o painel "Ver a consulta".
    # Começa pela busca vetorial, que é sempre o primeiro passo. Além do
    # pipeline, guardamos "resultado": as entidades REAIS que a busca retornou
    # (nome, tipo, score), para a tela mostrar PARA QUE o $vectorSearch resolveu
    # — evidenciando a etapa semântica antes da travessia $lookup.
    consulta_vetor: Dict[str, str] = {
        "titulo": "1) Busca vetorial ($vectorSearch) — acha o nó de entrada",
        "consulta": vector_search.consulta_vetorial(k),
    }
    if hits:
        resolvido = ", ".join(
            f"{h['name']} ({h['entity_type']}, score {h['score']:.3f})" for h in hits
        )
        consulta_vetor["resultado"] = f"Resolveu para: {resolvido}"
    consultas: List[Dict[str, str]] = [consulta_vetor]

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
            trav = queries.consulta_travessia(h["entity_id"])
            if trav:
                consultas.append({
                    "titulo": f"2) Travessia $lookup encadeada — licença {h['name']}",
                    "consulta": trav,
                })
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

    # A agregação de custo (unit_cost x quantity) também rodou de verdade.
    for nome in sorted(fornecedores):
        consultas.append({
            "titulo": f"3) Agregação de custo por centro — fornecedor {nome}",
            "consulta": costs.consulta_por_centro(nome),
        })

    tempos["grafo_lookup_agg_ms"] = round((time.perf_counter() - t_grafo0) * 1000, 1)

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
        # Comandos MongoDB reais por trás da resposta (painel "Ver a consulta").
        "consultas": consultas,
        # Tempo (ms) de cada etapa medida até aqui; a rota /ask completa com
        # 'geracao_claude_ms' e 'total_ms'. Metadado de interface (não vai ao LLM).
        "tempos": tempos,
    }
