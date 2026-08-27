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


# --- Ponto 3: sem negativos, sem referências órfãs --------------------------
def test_seed_sem_violacoes_de_integridade(client):
    problemas = validation.check_integrity(get_db())
    assert problemas == [], f"Integridade violada: {problemas}"


# --- Ponto 2: métricas de licenciamento -------------------------------------
def test_metricas_de_licenca_no_dominio(client):
    permitido = {"per_cpu", "per_host", "per_user"}
    metricas = {l.get("metric") for l in get_db().licenses.find({}, {"metric": 1})}
    assert metricas <= permitido, f"Métrica fora do domínio: {metricas - permitido}"


def test_custo_independe_da_metrica(client):
    """
    O total por fornecedor bate com unit_cost x quantity somado SEM olhar a
    métrica. Trava o invariante: ninguém pode "meter" a métrica no cálculo sem
    antes fechar o elo servers->licenses (ver SPEC.md secoes 4 e 8).
    """
    db = get_db()
    lic = {l["_id"]: l for l in db.licenses.find()}
    prod = {p["_id"]: p for p in db.products.find()}
    vend = {v["_id"]: v["name"] for v in db.vendors.find()}
    esperado = {}
    for a in db.allocations.find():
        l = lic[a["license_id"]]
        vname = vend[prod[l["product_id"]]["vendor_id"]]
        esperado[vname] = esperado.get(vname, 0) + a["quantity"] * l["unit_cost"]
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
