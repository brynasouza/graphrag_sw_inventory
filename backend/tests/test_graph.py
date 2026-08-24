"""
Testes da travessia de grafo (Etapa 3).

Assumem que o seed já foi rodado:
    .venv/bin/python -m app.ingestion.seed
"""


def _find_license(client, name):
    r = client.get("/graph/licenses")
    assert r.status_code == 200
    for lic in r.json():
        if lic["name"] == name:
            return lic
    raise AssertionError(f"Licença '{name}' não encontrada (rodou o seed?)")


def test_health(client):
    r = client.get("/health")
    assert r.json()["status"] == "ok"


def test_expiring_licenses(client):
    r = client.get("/graph/licenses", params={"expiring_in_days": 90})
    assert r.status_code == 200
    # O seed garante que algumas licenças vencem em 90 dias.
    assert len(r.json()) >= 1


def test_projects_using_license(client):
    lic = _find_license(client, "vSphere Standard 2026")
    r = client.get(f"/graph/licenses/{lic['_id']}/projects")
    assert r.status_code == 200
    projetos = {row["project"] for row in r.json()}
    assert "Datacenter Virtualização" in projetos


def test_license_impact(client):
    lic = _find_license(client, "vSphere Standard 2026")
    r = client.get(f"/graph/licenses/{lic['_id']}/impact")
    assert r.status_code == 200
    imp = r.json()
    assert "CC-TI" in imp["impacted_cost_centers"]
    assert "esx-prod-01" in imp["impacted_servers"]


def test_license_not_found(client):
    r = client.get("/graph/licenses/000000000000000000000000/impact")
    assert r.status_code == 404
