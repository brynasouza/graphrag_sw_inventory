"""
Testes de INTEGRIDADE dos dados (pontos 2, 3 e 4 do plano de integridade).

  - check_integrity: o banco seedado não tem negativos nem referências órfãs.
  - métricas de licença: sempre no domínio {per_cpu, per_host, per_user}, e o
    custo é INDEPENDENTE da métrica (invariante atual do modelo).
  - fronteira ObjectId x string: nenhum ObjectId escapa para o JSON da API.

São de integração (usam o Atlas real via a fixture `client`, que pula se o
banco estiver fora).
"""
from app.core.db import get_db
from app.graph import validation
from app.models.schemas import Collections as C
from app.models.schemas import EdgeTypes as E


# --- Ponto 3: sem negativos, sem referências órfãs --------------------------
def test_seed_sem_violacoes_de_integridade(client):
    problemas = validation.check_integrity(get_db())
    assert problemas == [], f"Integridade violada: {problemas}"


# --- Ponto 2: métricas de licenciamento -------------------------------------
def test_metricas_de_licenca_no_dominio(client):
    permitido = {"per_cpu", "per_host", "per_user"}
    metricas = {
        n["props"].get("metric")
        for n in get_db()[C.GRAPH].find({"tipo": "license"}, {"props.metric": 1})
    }
    assert metricas <= permitido, f"Métrica fora do domínio: {metricas - permitido}"


def test_custo_independe_da_metrica(client):
    """
    O total por fornecedor bate com unit_cost x quantity somado SEM olhar a
    métrica. Trava o invariante: ninguém pode "meter" a métrica no cálculo sem
    antes fechar o elo servers->licenses (ver SPEC.md secoes 4 e 8).
    """
    db = get_db()
    nodes = {n["_id"]: n for n in db[C.GRAPH].find()}
    salto = {
        (nid, a["tipo"]): a["to"]
        for nid, n in nodes.items() for a in n.get("arestas", [])
    }

    esperado = {}
    for lic in nodes.values():
        if lic.get("tipo") != "license":
            continue
        for a in lic.get("arestas", []):
            if a["tipo"] != E.ALOCACAO:
                continue
            prod_id = salto[(lic["_id"], E.LICENCA_PRODUTO)]
            vname = nodes[salto[(prod_id, E.PRODUTO_FORNECEDOR)]]["label"]
            esperado[vname] = esperado.get(vname, 0) + \
                a["props"]["quantity"] * lic["props"]["unit_cost"]
    got = {r["vendor"]: r["total"] for r in
           client.get("/graph/costs/by-vendor").json()}
    assert got == esperado


# --- Ponto 4: nenhum ObjectId vaza para o JSON ------------------------------
def test_ids_expostos_sao_string(client):
    dados = client.get("/graph/explore").json()
    assert dados["nodes"], "grafo vazio — rode o seed"
    for node in dados["nodes"]:
        assert isinstance(node["id"], str), f"id não-string: {node['id']!r}"
    for edge in dados["edges"]:
        assert isinstance(edge["source"], str) and isinstance(edge["target"], str)
