"""
Popula o MongoDB com dados de exemplo de uma empresa brasileira média,
no MODELO GRAFO-NATIVO (`graph_nodes` + `graph_edges`).

Rode a partir da pasta backend/ com:
    .venv/bin/python -m app.ingestion.seed

O script é DETERMINÍSTICO e idempotente: apaga as coleções e recria tudo do
zero com os MESMOS _id a cada execução. Derivamos o _id de cada NÓ de uma chave
natural namespaced por tipo (ex.: "vendor:VMware"), então rodar o seed duas
vezes produz exatamente os mesmos identificadores — o que também mantém a
coleção `search_index` válida (os `entity_id` continuam apontando para nós que
existem, sem precisar re-embeddar).

Sobre as datas: são RELATIVAS a uma data-base (padrão: hoje à meia-noite UTC).
Isso é de propósito — a regra "algumas licenças vencem nos próximos 90 dias"
precisa continuar verdadeira independentemente de quando o seed roda. Para
fixar a data-base (ex.: em teste), defina a variável de ambiente
SEED_DATA_BASE com uma data ISO, por exemplo: SEED_DATA_BASE=2026-01-01.

Atenção: o seed NÃO mexe na coleção `search_index`. Quem a (re)constrói é o
`build_embeddings.py`. Rode-o de novo só quando as entidades ou seus textos
mudarem — não é preciso a cada seed, já que os _id são estáveis.
"""
import hashlib
import os
from datetime import datetime, timedelta

from bson import ObjectId

from app.core.db import get_db
from app.core.indexes import ensure_indexes
from app.graph.validation import check_integrity
from app.models.schemas import Collections as C
from app.models.schemas import EdgeTypes as E


def oid_estavel(chave: str) -> ObjectId:
    """
    Gera um ObjectId determinístico a partir de uma chave natural.
    A mesma chave sempre devolve o mesmo _id — é isso que torna o seed
    reproduzível. A chave já vem "namespaced" por tipo (ex.: "vendor:VMware")
    para não haver colisão entre tipos diferentes de nó.
    """
    return ObjectId(hashlib.md5(chave.encode()).hexdigest()[:24])


def _data_base() -> datetime:
    """Data-base das datas relativas: SEED_DATA_BASE (se definida) ou hoje 00:00 UTC."""
    iso = os.getenv("SEED_DATA_BASE")
    if iso:
        return datetime.fromisoformat(iso)
    return datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)


DATA_BASE = _data_base()


def dias(n: int) -> datetime:
    """Data daqui a n dias a partir da data-base (n negativo = no passado)."""
    return DATA_BASE + timedelta(days=n)


def seed():
    db = get_db()
    nodes = db[C.GRAPH_NODES]
    edges = db[C.GRAPH_EDGES]

    # 1) Limpa tudo para um estado conhecido -----------------------------
    nodes.delete_many({})
    edges.delete_many({})

    # Helpers locais: criam nó/aresta com _id determinístico e devolvem o _id.
    def no(chave: str, tipo: str, label: str, props: dict) -> ObjectId:
        _id = oid_estavel(chave)
        nodes.insert_one({"_id": _id, "tipo": tipo, "label": label, "props": props})
        return _id

    def aresta(from_id: ObjectId, to_id: ObjectId, tipo: str, props: dict = None) -> None:
        _id = oid_estavel(f"edge:{tipo}:{from_id}:{to_id}")
        edges.insert_one({"_id": _id, "from": from_id, "to": to_id,
                          "tipo": tipo, "props": props or {}})

    # 2) Centros de custo (3) -------------------------------------------
    cc = {}
    for name, code in [("Tecnologia da Informação", "CC-TI"),
                       ("Financeiro", "CC-FIN"),
                       ("Operações", "CC-OPS")]:
        cc[code] = no(f"cost_center:{code}", "cost_center", code,
                      {"code": code, "name": name})

    # 3) Times (5) -> centro de custo (aresta time → centro) ------------
    teams = {}
    for name, cc_code in [("Infraestrutura", "CC-TI"),
                          ("Plataforma", "CC-TI"),
                          ("DevOps", "CC-TI"),
                          ("Dados & BI", "CC-FIN"),
                          ("Aplicações Corporativas", "CC-OPS")]:
        teams[name] = no(f"team:{name}", "team", name, {"name": name})
        aresta(teams[name], cc[cc_code], E.TIME_CENTRO)

    # 4) Projetos (8) -> time (aresta projeto → time) -------------------
    projects = {}
    for name, team in [("Datacenter Virtualização", "Infraestrutura"),
                       ("Observabilidade", "DevOps"),
                       ("CI/CD Pipeline", "DevOps"),
                       ("Portal do Cliente", "Plataforma"),
                       ("App Mobile", "Plataforma"),
                       ("ERP Corporativo", "Aplicações Corporativas"),
                       ("Intranet", "Aplicações Corporativas"),
                       ("Data Lake", "Dados & BI")]:
        projects[name] = no(f"project:{name}", "project", name, {"name": name})
        aresta(projects[name], teams[team], E.PROJETO_TIME)

    # 5) Fornecedores (5) -----------------------------------------------
    vendors = {}
    for name in ["VMware", "Microsoft", "Oracle", "Red Hat", "Atlassian"]:
        vendors[name] = no(f"vendor:{name}", "vendor", name, {"name": name})

    # 6) Produtos -> fornecedor (aresta produto → fornecedor) -----------
    products = {}
    catalogo = {
        "VMware": ["vSphere", "vCenter"],
        "Microsoft": ["Windows Server", "SQL Server", "Microsoft 365"],
        "Oracle": ["Oracle Database", "Oracle WebLogic"],
        "Red Hat": ["RHEL", "OpenShift"],
        "Atlassian": ["Jira", "Confluence"],
    }
    for vendor, prods in catalogo.items():
        for p in prods:
            products[p] = no(f"product:{p}", "product", p, {"name": p})
            aresta(products[p], vendors[vendor], E.PRODUTO_FORNECEDOR)

    # 7) Contratos (1 por fornecedor) -> fornecedor ---------------------
    contracts = {}
    contratos_def = [
        ("VMware", "CT-VMW-2024", 1_200_000, dias(-400), dias(330)),
        ("Microsoft", "CT-MSF-2025", 2_500_000, dias(-200), dias(500)),
        ("Oracle", "CT-ORA-2024", 3_800_000, dias(-500), dias(220)),
        ("Red Hat", "CT-RHT-2025", 900_000, dias(-150), dias(560)),
        ("Atlassian", "CT-ATL-2025", 300_000, dias(-100), dias(260)),
    ]
    for vendor, ref, value, start, end in contratos_def:
        contracts[vendor] = no(f"contract:{ref}", "contract", ref, {
            "reference": ref, "value": value, "currency": "BRL",
            "starts_at": start, "ends_at": end,
        })
        aresta(contracts[vendor], vendors[vendor], E.CONTRATO_FORNECEDOR)

    # 8) Licenças (15) -> produto + contrato (2 arestas por licença) ----
    # (produto, contrato_fornecedor, rótulo, dias_p/_vencer, custo_unit, métrica)
    licencas_def = [
        ("vSphere",        "VMware",    "vSphere Standard 2026",     47,   4_500, "per_cpu"),   # vence < 90d
        ("vCenter",        "VMware",    "vCenter Server 2026",       67,   8_000, "per_host"),  # vence < 90d
        ("vSphere",        "VMware",    "vSphere Enterprise Plus",   244,  9_000, "per_cpu"),
        ("Windows Server", "Microsoft", "Windows Server Datacenter", 78,   1_200, "per_cpu"),   # vence < 90d
        ("Windows Server", "Microsoft", "Windows Server Standard",   210,  1_200, "per_cpu"),
        ("SQL Server",     "Microsoft", "SQL Server Enterprise",     83,  15_000, "per_cpu"),   # vence < 90d
        ("Microsoft 365",  "Microsoft", "Microsoft 365 E3",          170,     55, "per_user"),
        ("Oracle Database","Oracle",    "Oracle DB Enterprise",      48,  47_000, "per_cpu"),   # vence < 90d
        ("Oracle Database","Oracle",    "Oracle DB Standard",        520, 17_500, "per_cpu"),
        ("Oracle WebLogic","Oracle",    "WebLogic Suite",            320, 30_000, "per_cpu"),
        ("RHEL",           "Red Hat",   "RHEL Server Premium",       27,   2_500, "per_host"),  # vence < 90d
        ("RHEL",           "Red Hat",   "RHEL Server Standard",      350,  1_800, "per_host"),
        ("OpenShift",      "Red Hat",   "OpenShift Platform Plus",   200, 12_000, "per_cpu"),
        ("Jira",           "Atlassian", "Jira Software Cloud",       110,     40, "per_user"),
        ("Confluence",     "Atlassian", "Confluence Cloud",          110,     30, "per_user"),
    ]
    licenses = {}  # rótulo -> _id
    for prod, vendor, rotulo, dvenc, custo, metric in licencas_def:
        licenses[rotulo] = no(f"license:{rotulo}", "license", rotulo, {
            "name": rotulo,
            "expires_at": dias(dvenc),
            "unit_cost": custo,
            "currency": "BRL",
            "metric": metric,
        })
        aresta(licenses[rotulo], products[prod], E.LICENCA_PRODUTO)
        aresta(licenses[rotulo], contracts[vendor], E.LICENCA_CONTRATO)

    # 9) Alocações: aresta licença → projeto, com a quantidade em props --
    # (rótulo_licença, projeto, quantidade)
    alocacoes_def = [
        ("vSphere Standard 2026",     "Datacenter Virtualização", 8),
        ("vSphere Standard 2026",     "Observabilidade",          2),
        ("vCenter Server 2026",       "Datacenter Virtualização", 2),
        ("vSphere Enterprise Plus",   "Datacenter Virtualização", 6),
        ("Windows Server Datacenter", "ERP Corporativo",          4),
        ("Windows Server Datacenter", "Intranet",                 2),
        ("Windows Server Standard",   "Portal do Cliente",        3),
        ("SQL Server Enterprise",     "ERP Corporativo",          2),
        ("SQL Server Enterprise",     "Data Lake",                2),
        ("Microsoft 365 E3",          "Intranet",               120),
        ("Oracle DB Enterprise",      "ERP Corporativo",          4),
        ("Oracle DB Standard",        "Data Lake",                2),
        ("WebLogic Suite",            "ERP Corporativo",          2),
        ("RHEL Server Premium",       "Datacenter Virtualização", 10),
        ("RHEL Server Standard",      "CI/CD Pipeline",           6),
        ("OpenShift Platform Plus",   "CI/CD Pipeline",           8),
        ("OpenShift Platform Plus",   "App Mobile",               4),
        ("Jira Software Cloud",       "CI/CD Pipeline",          60),
        ("Jira Software Cloud",       "Portal do Cliente",       40),
        ("Confluence Cloud",          "Intranet",                80),
    ]
    for rotulo, proj, qtd in alocacoes_def:
        aresta(licenses[rotulo], projects[proj], E.ALOCACAO,
               {"quantity": qtd, "allocated_at": dias(-30)})

    # 10) Servidores -> projeto (aresta servidor → projeto) -------------
    # (VMware é licenciado por host/CPU, daí os sockets)
    servers_def = [
        ("esx-prod-01", 2, "Datacenter Virtualização"),
        ("esx-prod-02", 2, "Datacenter Virtualização"),
        ("esx-prod-03", 4, "Datacenter Virtualização"),
        ("obs-node-01", 2, "Observabilidade"),
        ("erp-db-01",   4, "ERP Corporativo"),
        ("erp-app-01",  2, "ERP Corporativo"),
        ("cicd-run-01", 2, "CI/CD Pipeline"),
        ("lake-node-01", 4, "Data Lake"),
    ]
    for hostname, sockets, proj in servers_def:
        sid = no(f"server:{hostname}", "server", hostname,
                 {"hostname": hostname, "cpu_sockets": sockets})
        aresta(sid, projects[proj], E.SERVIDOR_PROJETO)

    # 11) Índices do grafo (para o $graphLookup e os $match não varrerem tudo)
    ensure_indexes(db)

    # 12) Token de versão do seed --------------------------------------
    # A API guarda em memória o retrieval das perguntas fixas da demo.
    # Este doc é o sinal para invalidar esse cache: como o seed muda o
    # `ran_at`, a API percebe que os dados mudaram e recomputa.
    db[C.META].replace_one(
        {"_id": "seed"},
        {"_id": "seed", "ran_at": datetime.utcnow()},
        upsert=True,
    )

    # Resumo -------------------------------------------------------------
    print("Seed concluído (modelo grafo-nativo).")
    print(f"  {C.GRAPH_NODES:>12}: {nodes.count_documents({})} nós")
    print(f"  {C.GRAPH_EDGES:>12}: {edges.count_documents({})} arestas")
    print("\nNós por tipo:")
    for tipo in ["vendor", "product", "contract", "license",
                 "project", "team", "cost_center", "server"]:
        print(f"  {tipo:>12}: {nodes.count_documents({'tipo': tipo})}")

    venc90 = nodes.count_documents(
        {"tipo": "license", "props.expires_at": {"$lte": dias(90)}})
    print(f"\nLicenças vencendo nos próximos 90 dias: {venc90}")

    # Rede de segurança: confere integridade (negativos + arestas órfãs).
    # Não é fatal — o seed já rodou; só AVISA se algo saiu torto, para pegar
    # cedo um erro introduzido numa futura mudança dos dados.
    problemas = check_integrity(db)
    if problemas:
        print(f"\n⚠️  {len(problemas)} problema(s) de integridade encontrado(s):")
        for p in problemas:
            print(f"  - {p}")
    else:
        print("Integridade: OK (nenhum negativo, nenhuma aresta órfã).")


if __name__ == "__main__":
    seed()
