"""
Constrói a coleção `search_index` para a busca vetorial (Etapa 5).

O que este script faz:
  1. Monta uma FRASE descritiva para cada entidade pesquisável
     (licenças e fornecedores), juntando nome + contexto (produto,
     fornecedor, como é licenciada). Frase rica = busca melhor.
  2. SINCRONIZA a coleção `search_index` de forma INCREMENTAL: só gera
     embedding para frases novas ou que mudaram, reaproveita as inalteradas
     e remove as órfãs (entidade que sumiu). Cada doc guarda {entity_type,
     entity_id, name, text, embedding}, com chave única (entity_type, entity_id).

Rode assim (a partir da pasta backend/):
    .venv/bin/python -m app.ingestion.build_embeddings

Depois de rodar, crie no Atlas o índice de Vector Search "vector_index"
na coleção "search_index" — a definição está em
app/ingestion/atlas_vector_index.json.

É idempotente E econômico: rodar de novo sem nada ter mudado NÃO chama a
Voyage (nenhuma cota gasta) — o texto de cada entidade é comparado com o já
indexado e só o que mudou é re-embeddado.
"""
from typing import Any, Dict, List, Tuple

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


def _chave(doc: Dict[str, Any]) -> Tuple[str, Any]:
    """Chave única de um doc do índice: (entity_type, entity_id)."""
    return (doc["entity_type"], doc["entity_id"])


def _dim_ok(vetor: Any) -> bool:
    """True se `vetor` é uma lista com a dimensão esperada (embeddings.DIM)."""
    return isinstance(vetor, (list, tuple)) and len(vetor) == embeddings.DIM


def _validar_dim(vetor: Any) -> None:
    """Aborta com erro claro se um vetor NOVO não tiver a dimensão esperada."""
    if not _dim_ok(vetor):
        tam = len(vetor) if isinstance(vetor, (list, tuple)) else "n/d"
        raise ValueError(
            f"Embedding com dimensão inesperada: {tam} (esperado {embeddings.DIM}). "
            "Verifique o modelo da Voyage e a definição do índice no Atlas."
        )


def _diff(desejados: List[Dict[str, Any]],
          existentes: Dict[Tuple[str, Any], Dict[str, Any]]
          ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Tuple[str, Any]]]:
    """
    Compara o que DEVE existir com o que JÁ existe no índice. Devolve:
      - a_gerar:        docs cujo texto é novo/mudou (ou cujo embedding gravado
                        está com dimensão inválida) — precisam de embedding novo.
      - reaproveitados: docs inalterados — recebem o embedding que já estava lá.
      - orfaos:         chaves que existem no índice mas não são mais desejadas.
    """
    a_gerar: List[Dict[str, Any]] = []
    reaproveitados: List[Dict[str, Any]] = []
    desejadas_keys = set()

    for doc in desejados:
        k = _chave(doc)
        desejadas_keys.add(k)
        antigo = existentes.get(k)
        if antigo and antigo.get("text") == doc["text"] and _dim_ok(antigo.get("embedding")):
            reaproveitados.append({**doc, "embedding": antigo["embedding"]})
        else:
            a_gerar.append(doc)

    orfaos = [k for k in existentes if k not in desejadas_keys]
    return a_gerar, reaproveitados, orfaos


def build(col=None) -> int:
    """
    Sincroniza a `search_index` de forma incremental.

    `col` permite injetar uma coleção (usado nos testes, para não tocar no
    índice real da demo); em produção usa a `search_index` padrão.
    """
    db = get_db()
    if col is None:
        col = db[C.SEARCH_INDEX]

    docs = _license_docs(db) + _vendor_docs(db)
    if not docs:
        print("Nenhuma entidade encontrada. Rode o seed antes:")
        print("    .venv/bin/python -m app.ingestion.seed")
        return 0

    # Chave única (entity_type, entity_id): sustenta o upsert e impede duplicatas.
    col.create_index([("entity_type", 1), ("entity_id", 1)], unique=True)

    # O que já está indexado hoje (para comparar texto e reaproveitar vetores).
    existentes = {_chave(d): d for d in col.find(
        {}, {"entity_type": 1, "entity_id": 1, "text": 1, "embedding": 1})}

    a_gerar, reaproveitados, orfaos = _diff(docs, existentes)

    # Só chama a Voyage para o que realmente mudou (nada mudou -> zero cota).
    if a_gerar:
        print(f"Gerando embeddings de {len(a_gerar)} entidade(s) nova(s)/alterada(s) "
              f"com a Voyage AI... ({len(reaproveitados)} reaproveitada(s))")
        vetores = embeddings.embed_documents([d["text"] for d in a_gerar])
        for doc, vetor in zip(a_gerar, vetores):
            _validar_dim(vetor)        # valida ANTES de gravar
            doc["embedding"] = vetor
    else:
        print(f"Nada mudou: {len(reaproveitados)} entidade(s) já indexada(s) — "
              "nenhuma chamada à Voyage.")

    # Upsert por chave única (grava os novos, mantém os reaproveitados).
    for doc in a_gerar + reaproveitados:
        col.replace_one(
            {"entity_type": doc["entity_type"], "entity_id": doc["entity_id"]},
            doc,
            upsert=True,
        )

    # Remove órfãos: entidades que sumiram do banco não podem sobrar no índice.
    for entity_type, entity_id in orfaos:
        col.delete_one({"entity_type": entity_type, "entity_id": entity_id})
    if orfaos:
        print(f"Removidas {len(orfaos)} entrada(s) órfã(s) do índice.")

    total = len(a_gerar) + len(reaproveitados)
    print(f"OK: {total} entidade(s) em '{col.name}' "
          f"(dimensão do vetor: {embeddings.DIM}).")
    print("\nPRÓXIMO PASSO (uma vez, no site do Atlas):")
    print("  Crie um índice de Atlas Vector Search chamado 'vector_index'")
    print(f"  na coleção '{C.SEARCH_INDEX}' usando a definição em")
    print("  app/ingestion/atlas_vector_index.json")
    return total


if __name__ == "__main__":
    build()
