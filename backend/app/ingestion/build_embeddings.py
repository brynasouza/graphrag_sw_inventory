"""
Constrói a coleção `search_index` para a busca vetorial (Etapa 5).

O que este script faz:
  1. Monta uma FRASE descritiva para cada entidade pesquisável
     (licenças e fornecedores), juntando nome + contexto (produto,
     fornecedor, como é licenciada). Frase rica = busca melhor.
  2. Gera o embedding de cada frase com a Voyage AI.
  3. Regrava a coleção `search_index` com {entity_type, entity_id,
     name, text, embedding}.

Rode assim (a partir da pasta backend/):
    .venv/bin/python -m app.ingestion.build_embeddings

Depois de rodar, crie no Atlas o índice de Vector Search "vector_index"
na coleção "search_index" — a definição está em
app/ingestion/atlas_vector_index.json.

É idempotente: pode rodar quantas vezes quiser; sempre reconstrói do zero.
"""
from typing import Any, Dict, List

from app.core.db import get_db
from app.models.schemas import Collections as C
from app.retrieval import embeddings


# Âncora semântica CIRÚRGICA: descrição funcional só dos produtos cujo termo de
# negócio o usuário usaria mas que NÃO aparece em nenhum campo do banco. Sem
# isso, "plataforma de contêineres" e "colaboração/documentação" resolviam por
# margem frágil (medido: OpenShift/Red Hat contaminava com VMware no k=3;
# Confluence/Jira ficavam a ~0,004 de um banco de dados irrelevante).
# vSphere/vCenter (virtualização) NÃO entram: já resolvem com folga sozinhos —
# enriquecer o que já funciona só adiciona ruído. O conceito passa a existir no
# TEXTO indexado (fonte do embedding), nunca nos campos de negócio: um find()
# por palavra-chave continua não achando — é essa a diferença que a busca prova.
_DESCRICAO_FUNCIONAL = {
    "OpenShift": "plataforma de contêineres e orquestração Kubernetes",
    "Confluence": "colaboração, wiki e documentação de equipes",
    "Jira": "colaboração, gestão de projetos e acompanhamento de tarefas",
}


def _license_docs(db) -> List[Dict[str, Any]]:
    """Uma frase por licença, enriquecida com produto e fornecedor."""
    produtos = {p["_id"]: p for p in db[C.PRODUCTS].find()}
    fornecedores = {v["_id"]: v["name"] for v in db[C.VENDORS].find()}

    docs = []
    for lic in db[C.LICENSES].find():
        prod = produtos.get(lic["product_id"], {})
        fornecedor = fornecedores.get(prod.get("vendor_id"), "?")
        texto = (
            f"Licença {lic['name']}. "
            f"Produto {prod.get('name', '?')} do fornecedor {fornecedor}. "
            f"Licenciada por {lic.get('metric', '?')}. "
            f"Vence em {lic['expires_at'].strftime('%d/%m/%Y')}."
        )
        # Âncora funcional só para os produtos frágeis (ver _DESCRICAO_FUNCIONAL).
        desc = _DESCRICAO_FUNCIONAL.get(prod.get("name"))
        if desc:
            texto += f" Usado para {desc}."
        docs.append({
            "entity_type": "license",
            "entity_id": lic["_id"],
            "name": lic["name"],
            "text": texto,
        })
    return docs


def _vendor_docs(db) -> List[Dict[str, Any]]:
    """Uma frase por fornecedor, com seus produtos."""
    produtos_por_fornecedor: Dict[Any, List[str]] = {}
    for p in db[C.PRODUCTS].find():
        produtos_por_fornecedor.setdefault(p["vendor_id"], []).append(p["name"])

    docs = []
    for v in db[C.VENDORS].find():
        nomes = produtos_por_fornecedor.get(v["_id"], [])
        prods = ", ".join(nomes) or "sem produtos"
        texto = f"Fornecedor {v['name']}. Produtos: {prods}."
        # Herda a âncora funcional dos produtos que a têm (só Red Hat e Atlassian).
        categorias = [_DESCRICAO_FUNCIONAL[n] for n in nomes if n in _DESCRICAO_FUNCIONAL]
        if categorias:
            texto += f" Atua em: {'; '.join(categorias)}."
        docs.append({
            "entity_type": "vendor",
            "entity_id": v["_id"],
            "name": v["name"],
            "text": texto,
        })
    return docs


def build() -> int:
    db = get_db()

    docs = _license_docs(db) + _vendor_docs(db)
    if not docs:
        print("Nenhuma entidade encontrada. Rode o seed antes:")
        print("    .venv/bin/python -m app.ingestion.seed")
        return 0

    # Gera todos os embeddings de uma vez (mais rápido e mais barato).
    textos = [d["text"] for d in docs]
    print(f"Gerando embeddings de {len(textos)} entidades com a Voyage AI...")
    vetores = embeddings.embed_documents(textos)
    for doc, vetor in zip(docs, vetores):
        doc["embedding"] = vetor

    # Reconstrói a coleção do zero (idempotente).
    col = db[C.SEARCH_INDEX]
    col.delete_many({})
    col.insert_many(docs)

    print(f"OK: {len(docs)} entidades indexadas em '{C.SEARCH_INDEX}' "
          f"(dimensão do vetor: {embeddings.DIM}).")
    print("\nPRÓXIMO PASSO (uma vez, no site do Atlas):")
    print("  Crie um índice de Atlas Vector Search chamado 'vector_index'")
    print(f"  na coleção '{C.SEARCH_INDEX}' usando a definição em")
    print("  app/ingestion/atlas_vector_index.json")
    return len(docs)


if __name__ == "__main__":
    build()
