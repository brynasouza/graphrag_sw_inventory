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
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional, Tuple

from app.core.db import get_db
from app.graph import costs, graphdata, queries, subgraph
from app.models.schemas import Collections as C
from app.retrieval import demo_cache, vector_search


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

    É a junção de duas etapas: a busca vetorial (acha o nó de entrada) e a
    montagem do grafo (reúne os fatos). O /ask usa esta função inteira; o
    /ask/stream chama as duas metades separadamente para mostrar o progresso
    ("buscando" -> "percorrendo") entre elas.
    """
    # Instrumentação: o search preenche 'embedding_query_ms' e
    # 'vector_search_ms'; build_from_hits mede 'grafo_lookup_agg_ms'.
    tempos: Dict[str, float] = {}
    hits = vector_search.search(query, k=k, tempos=tempos)
    return build_from_hits(query, hits, k, tempos)


def build_context_cached(query: str, k: int = 3) -> Dict[str, Any]:
    """
    Igual a `build_context`, mas serve as perguntas FIXAS da demo de um cache em
    memória (retrieval inteiro: vetorial + grafo). Em cache HIT, pula embedding,
    $vectorSearch e travessia — sobra só o Claude — e as `consultas` (as duas
    fases do GraphRAG) vêm intactas do cache, para o painel "Ver a consulta"
    ficar idêntico. Em cache MISS, calcula normal e guarda. Perguntas fora da
    whitelist passam direto (comportamento idêntico ao `build_context`).
    """
    cached = demo_cache.obter(query, k)
    if cached is not None:
        # Tempos zerados + flag: nada foi para a rede nas etapas de retrieval.
        cached["tempos"] = {
            "cache": True,
            "embedding_query_ms": 0.0,
            "vector_search_ms": 0.0,
            "grafo_lookup_agg_ms": 0.0,
        }
        return cached
    ctx = build_context(query, k)
    demo_cache.guardar(query, k, ctx)
    return ctx


def build_from_hits(
    query: str,
    hits: List[Dict[str, Any]],
    k: int,
    tempos: Dict[str, float],
) -> Dict[str, Any]:
    """
    Segunda metade do build_context: dado o resultado da busca vetorial
    (`hits`), percorre o grafo e monta o contexto final. Separada para que o
    /ask/stream possa emitir a etapa "percorrendo o grafo" entre a busca e a
    travessia. Grava 'grafo_lookup_agg_ms' em `tempos`.
    """
    db = get_db()

    t_grafo0 = time.perf_counter()

    # Dedup dos hits preservando a ordem (evita repetir a mesma entidade).
    unique_hits: List[Dict[str, Any]] = []
    vistos: set = set()
    for h in hits:
        chave = (h["entity_type"], h["entity_id"])
        if chave in vistos:
            continue
        vistos.add(chave)
        unique_hits.append(h)

    # --- Fan-out: as chamadas independentes de cada hit rodam EM PARALELO ----
    # Antes, para cada hit rodávamos detalhe + impacto + subgrafo em sequência,
    # e um hit só começava depois do outro. Como tudo isso é I/O de rede ao
    # Atlas, threads dão paralelismo real (o pymongo é thread-safe; a chamada
    # get_db() acima já criou o client único antes do fan-out). A MONTAGEM
    # depois é sequencial e determinística — a saída fica idêntica à de antes.
    detalhes: Dict[int, Tuple] = {}          # i -> (fornecedor, custo, moeda)
    impactos: Dict[int, Any] = {}            # i -> license_impact(...)
    subs: Dict[int, Dict[str, Any]] = {}     # i -> subgrafo da entidade

    with ThreadPoolExecutor(max_workers=8) as ex:
        futuros = {}
        for i, h in enumerate(unique_hits):
            eid = h["entity_id"]
            if h["entity_type"] == "license":
                futuros[ex.submit(_licenca_detalhe, db, eid)] = (i, "detalhe")
                futuros[ex.submit(queries.license_impact, eid)] = (i, "impacto")
                futuros[ex.submit(subgraph.subgraph_for_license, db, eid)] = (i, "sub")
            elif h["entity_type"] == "vendor":
                futuros[ex.submit(subgraph.subgraph_for_vendor, db, eid)] = (i, "sub")
        for fut, (i, kind) in futuros.items():
            res = fut.result()  # re-lança exceção do worker, se houver
            if kind == "detalhe":
                detalhes[i] = res
            elif kind == "impacto":
                impactos[i] = res
            else:
                subs[i] = res

    # --- Montagem determinística (na ordem dos hits) ------------------------
    fatos: List[Dict[str, Any]] = []
    fornecedores: set = set()   # fornecedores p/ o consolidado de gasto
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

    for i, h in enumerate(unique_hits):
        if h["entity_type"] == "license":
            fornecedor, custo, moeda = detalhes[i]
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
                "impacto": impactos[i],
            })
            subgrafos.append(subs[i])
            trav = queries.consulta_travessia(h["entity_id"])  # só formata string
            if trav:
                consultas.append({
                    "titulo": f"2) Travessia $lookup encadeada — licença {h['name']}",
                    "consulta": trav,
                })
        elif h["entity_type"] == "vendor":
            fornecedores.add(h["name"])
            fatos.append({"tipo": "fornecedor", "nome": h["name"],
                          "entity_id": h["entity_id"]})
            subgrafos.append(subs[i])
        else:
            fatos.append({"tipo": h["entity_type"], "nome": h["name"],
                          "entity_id": h["entity_id"]})

    # Consolidado de gasto por centro de custo, para cada fornecedor envolvido.
    # As agregações por fornecedor são independentes -> também em paralelo.
    # ex.map preserva a ordem de `fornecedores_ord` (saída determinística).
    fornecedores_ord = sorted(fornecedores)
    with ThreadPoolExecutor(max_workers=8) as ex:
        gastos_calc = list(ex.map(costs.cost_by_cost_center, fornecedores_ord))
    gastos_por_fornecedor = [
        {"fornecedor": nome, "gasto_por_centro_de_custo": gasto}
        for nome, gasto in zip(fornecedores_ord, gastos_calc)
    ]

    # A agregação de custo (unit_cost x quantity) também rodou de verdade.
    for nome in fornecedores_ord:
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
