"""
Popula o MongoDB com dados de exemplo de uma empresa brasileira média.

Rode a partir da pasta backend/ com:
    .venv/bin/python -m app.ingestion.seed

O script é DETERMINÍSTICO e idempotente: apaga as coleções e recria tudo do
zero com os MESMOS _id a cada execução. Como derivamos os _id de uma chave
natural (nome/código), rodar o seed duas vezes produz exatamente os mesmos
identificadores — o que também mantém a coleção `search_index` válida (os
`entity_id` continuam apontando para documentos que existem).

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


def oid_estavel(chave: str) -> ObjectId:
    """
    Gera um ObjectId determinístico a partir de uma chave natural.
    A mesma chave sempre devolve o mesmo _id — é isso que torna o seed
    reproduzível. A chave já vem "namespaced" por coleção (ex.: "vendor:VMware")
    para não haver colisão entre coleções diferentes.
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

    # 1) Limpa tudo para um estado conhecido -----------------------------
    for nome in [C.VENDORS, C.PRODUCTS, C.CONTRACTS, C.LICENSES,
                 C.ALLOCATIONS, C.PROJECTS, C.TEAMS, C.COST_CENTERS, C.SERVERS]:
        db[nome].delete_many({})

    # 2) Centros de custo (3) -------------------------------------------
    cc = {}
    for name, code in [("Tecnologia da Informação", "CC-TI"),
                       ("Financeiro", "CC-FIN"),
                       ("Operações", "CC-OPS")]:
        cc[code] = db[C.COST_CENTERS].insert_one(
            {"_id": oid_estavel(f"cost_center:{code}"),
             "name": name, "code": code}).inserted_id

    # 3) Times (5) -> centro de custo -----------------------------------
    teams = {}
    for name, cc_code in [("Infraestrutura", "CC-TI"),
                          ("Plataforma", "CC-TI"),
                          ("DevOps", "CC-TI"),
                          ("Dados & BI", "CC-FIN"),
                          ("Aplicações Corporativas", "CC-OPS")]:
        teams[name] = db[C.TEAMS].insert_one(
            {"_id": oid_estavel(f"team:{name}"),
             "name": name, "cost_center_id": cc[cc_code]}).inserted_id

    # 4) Projetos (8) -> time -------------------------------------------
    projects = {}
    for name, team in [("Datacenter Virtualização", "Infraestrutura"),
                       ("Observabilidade", "DevOps"),
                       ("CI/CD Pipeline", "DevOps"),
                       ("Portal do Cliente", "Plataforma"),
                       ("App Mobile", "Plataforma"),
                       ("ERP Corporativo", "Aplicações Corporativas"),
                       ("Intranet", "Aplicações Corporativas"),
                       ("Data Lake", "Dados & BI")]:
        projects[name] = db[C.PROJECTS].insert_one(
            {"_id": oid_estavel(f"project:{name}"),
             "name": name, "team_id": teams[team]}).inserted_id

    # 5) Fornecedores (5) -----------------------------------------------
    vendors = {}
    for name in ["VMware", "Microsoft", "Oracle", "Red Hat", "Atlassian"]:
        vendors[name] = db[C.VENDORS].insert_one(
            {"_id": oid_estavel(f"vendor:{name}"), "name": name}).inserted_id

    # 6) Produtos -> fornecedor -----------------------------------------
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
            products[p] = db[C.PRODUCTS].insert_one(
                {"_id": oid_estavel(f"product:{p}"),
                 "name": p, "vendor_id": vendors[vendor]}).inserted_id

    # 7) Contratos (1 por fornecedor) -----------------------------------
    contracts = {}
    contratos_def = [
        ("VMware", "CT-VMW-2024", 1_200_000, dias(-400), dias(330)),
        ("Microsoft", "CT-MSF-2025", 2_500_000, dias(-200), dias(500)),
        ("Oracle", "CT-ORA-2024", 3_800_000, dias(-500), dias(220)),
        ("Red Hat", "CT-RHT-2025", 900_000, dias(-150), dias(560)),
        ("Atlassian", "CT-ATL-2025", 300_000, dias(-100), dias(260)),
    ]
    for vendor, ref, value, start, end in contratos_def:
        contracts[vendor] = db[C.CONTRACTS].insert_one({
            "_id": oid_estavel(f"contract:{ref}"),
            "vendor_id": vendors[vendor], "reference": ref,
            "value": value, "currency": "BRL",
            "starts_at": start, "ends_at": end,
        }).inserted_id

    # 8) Licenças (15) -> produto + contrato ----------------------------
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
        licenses[rotulo] = db[C.LICENSES].insert_one({
            "_id": oid_estavel(f"license:{rotulo}"),
            "name": rotulo,
            "product_id": products[prod],
            "contract_id": contracts[vendor],
            "expires_at": dias(dvenc),
            "unit_cost": custo,
            "currency": "BRL",
            "metric": metric,
        }).inserted_id

    # 9) Alocações (licença <-> projeto, com quantidade) ----------------
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
        db[C.ALLOCATIONS].insert_one({
            "_id": oid_estavel(f"allocation:{rotulo}:{proj}"),
            "license_id": licenses[rotulo],
            "project_id": projects[proj],
            "quantity": qtd,
            "allocated_at": dias(-30),
        })

    # 10) Servidores -> projeto (VMware é licenciado por host/CPU) ------
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
        db[C.SERVERS].insert_one({
            "_id": oid_estavel(f"server:{hostname}"),
            "hostname": hostname,
            "cpu_sockets": sockets,
            "project_id": projects[proj],
        })

    # 11) Índices das FKs (para as junções não varrerem tudo) -----------
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
    print("Seed concluído. Documentos por coleção:")
    for nome in [C.VENDORS, C.PRODUCTS, C.CONTRACTS, C.LICENSES,
                 C.ALLOCATIONS, C.PROJECTS, C.TEAMS, C.COST_CENTERS, C.SERVERS]:
        print(f"  {nome:>14}: {db[nome].count_documents({})}")

    venc90 = db[C.LICENSES].count_documents({"expires_at": {"$lte": dias(90)}})
    print(f"\nLicenças vencendo nos próximos 90 dias: {venc90}")

    # Rede de segurança: confere integridade (negativos + referências órfãs).
    # Não é fatal — o seed já rodou; só AVISA se algo saiu torto, para pegar
    # cedo um erro introduzido numa futura mudança dos dados.
    problemas = check_integrity(db)
    if problemas:
        print(f"\n⚠️  {len(problemas)} problema(s) de integridade encontrado(s):")
        for p in problemas:
            print(f"  - {p}")
    else:
        print("Integridade: OK (nenhum negativo, nenhuma referência órfã).")


if __name__ == "__main__":
    seed()
