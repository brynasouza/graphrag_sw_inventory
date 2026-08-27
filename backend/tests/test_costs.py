"""
Testes das agregações de custo (Etapa 4).

Confere a soma do MongoDB contra um cálculo independente feito em Python
a partir dos documentos crus — se os dois baterem, a agregação está certa.
"""
from app.core.db import get_db
from app.graph.costs import _pipeline_por_centro, _pipeline_por_fornecedor


def _group_stage(pipeline):
    """Devolve o corpo do estágio $group do pipeline."""
    return next(s["$group"] for s in pipeline if "$group" in s)


# --- Ponto 1: moeda NUNCA colapsa num único total ---------------------------
# Não tocam no banco: inspecionam o pipeline montado. Travam a regressão para
# `$first` sobre a moeda (que somaria BRL+USD silenciosamente sob uma só moeda).
def test_por_centro_agrupa_por_moeda():
    grupo = _group_stage(_pipeline_por_centro())
    assert grupo["_id"].get("currency") == "$lic.currency"  # moeda está na CHAVE
    assert set(grupo) == {"_id", "total"}                   # nenhum acumulador de moeda


def test_por_fornecedor_agrupa_por_moeda():
    grupo = _group_stage(_pipeline_por_fornecedor())
    assert grupo["_id"].get("currency") == "$lic.currency"
    assert set(grupo) == {"_id", "total"}


def _expected_totals():
    db = get_db()
    lic = {l["_id"]: l for l in db.licenses.find()}
    prod = {p["_id"]: p for p in db.products.find()}
    vend = {v["_id"]: v["name"] for v in db.vendors.find()}
    proj = {p["_id"]: p for p in db.projects.find()}
    team = {t["_id"]: t for t in db.teams.find()}
    cc = {c["_id"]: c for c in db.cost_centers.find()}

    by_vendor, by_cc = {}, {}
    for a in db.allocations.find():
        l = lic[a["license_id"]]
        spend = a["quantity"] * l["unit_cost"]
        vname = vend[prod[l["product_id"]]["vendor_id"]]
        by_vendor[vname] = by_vendor.get(vname, 0) + spend
        code = cc[team[proj[a["project_id"]]["team_id"]]["cost_center_id"]]["code"]
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
