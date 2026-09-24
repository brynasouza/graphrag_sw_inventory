"""
Testes das agregações de custo (Etapa 4).

Confere a soma do MongoDB contra um cálculo independente feito em Python
a partir dos documentos crus — se os dois baterem, a agregação está certa.
"""
from app.core.db import get_db
from app.graph.costs import _pipeline_por_centro, _pipeline_por_fornecedor
from app.models.schemas import Collections as C
from app.models.schemas import EdgeTypes as E


def _group_stage(pipeline):
    """Devolve o corpo do estágio $group do pipeline."""
    return next(s["$group"] for s in pipeline if "$group" in s)


def _estagios(pipeline):
    """Conjunto dos operadores de estágio usados no pipeline (ex.: '$graphLookup')."""
    return {k for s in pipeline for k in s}


# --- Ponto 1: moeda NUNCA colapsa num único total ---------------------------
# Não tocam no banco: inspecionam o pipeline montado. Travam a regressão para
# `$first` sobre a moeda (que somaria BRL+USD silenciosamente sob uma só moeda).
def test_por_centro_agrupa_por_moeda():
    grupo = _group_stage(_pipeline_por_centro())
    assert grupo["_id"].get("currency") == "$props.currency"  # moeda está na CHAVE
    assert set(grupo) == {"_id", "total"}                     # nenhum acumulador de moeda


def test_por_fornecedor_agrupa_por_moeda():
    grupo = _group_stage(_pipeline_por_fornecedor())
    assert grupo["_id"].get("currency") == "$props.currency"
    assert set(grupo) == {"_id", "total"}


# --- Ponto 2: a demo é MongoDB fazendo GRAFO — $graphLookup, nunca $lookup ---
# O propósito do MVP é percorrer relacionamentos com $graphLookup sobre a coleção
# auto-referencial. Um $lookup reaparecendo aqui seria "join estilo SQL" de volta
# no painel "Ver a consulta" — exatamente o que este rewrite eliminou.
def test_pipelines_usam_graphlookup_sem_lookup():
    for pipeline in (_pipeline_por_centro(), _pipeline_por_centro("VMware"),
                     _pipeline_por_fornecedor()):
        estagios = _estagios(pipeline)
        assert "$graphLookup" in estagios
        assert "$lookup" not in estagios


def _expected_totals():
    """
    Recalcula os totais direto do grafo cru (coleção `graph`), percorrendo as
    arestas embutidas na mão — a rede de segurança independente da agregação.
    Gasto de cada alocação = quantity (aresta) x unit_cost (nó licença); o
    fornecedor vem de licença → produto → fornecedor e o centro de custo de
    projeto → time → centro.
    """
    db = get_db()
    nodes = {n["_id"]: n for n in db[C.GRAPH].find()}
    # (from, tipo) -> to: cada aresta de salto único embutida no nó de origem.
    salto = {
        (nid, a["tipo"]): a["to"]
        for nid, n in nodes.items() for a in n.get("arestas", [])
    }

    by_vendor, by_cc = {}, {}
    for lic in nodes.values():
        if lic.get("tipo") != "license":
            continue
        for a in lic.get("arestas", []):
            if a["tipo"] != E.ALOCACAO:
                continue
            spend = a["props"]["quantity"] * lic["props"]["unit_cost"]
            prod_id = salto[(lic["_id"], E.LICENCA_PRODUTO)]
            vname = nodes[salto[(prod_id, E.PRODUTO_FORNECEDOR)]]["label"]
            by_vendor[vname] = by_vendor.get(vname, 0) + spend
            team_id = salto[(a["to"], E.PROJETO_TIME)]
            code = nodes[salto[(team_id, E.TIME_CENTRO)]]["label"]
            by_cc[code] = by_cc.get(code, 0) + spend
    return by_vendor, by_cc


def test_cost_by_vendor_matches_manual(client):
    expected, _ = _expected_totals()
    got = {r["vendor"]: r["total"] for r in
           client.get("/graph/costs/by-vendor").json()}
    assert got == expected


def test_cost_by_cost_center_matches_manual(client):
    _, expected = _expected_totals()
    got = {r["cost_center"]: r["total"] for r in
           client.get("/graph/costs/by-cost-center").json()}
    assert got == expected


def test_cost_filtered_by_vendor(client):
    r = client.get("/graph/costs/by-cost-center", params={"vendor": "VMware"})
    assert r.status_code == 200
    # VMware só aparece em centros de custo onde há alocação VMware.
    assert all(row["total"] > 0 for row in r.json())
