"""
Geração da resposta final com o Claude (Etapa 6).

Recebe a pergunta + os FATOS montados pelo grafo (context.py) e pede ao
Claude que escreva a resposta em português, usando SOMENTE esses fatos.
Assim evitamos "alucinação": o modelo não inventa números nem nomes,
apenas organiza em linguagem natural o que o grafo já provou.

Seguimos a referência atual da Anthropic:
  - SDK oficial `anthropic`;
  - modelo padrão `claude-opus-5`;
  - "adaptive thinking" (o modelo decide quanto raciocinar).
O cliente é preguiçoso; erro amigável se a chave faltar.
"""
import json
from typing import Any, Dict, Iterator, Optional

import anthropic

from app.core.config import settings

MODEL = "claude-opus-5"

# Instruções fixas de comportamento (system prompt).
SYSTEM = (
    "Você é um assistente de inventário de software corporativo. "
    "Responda SEMPRE em português do Brasil, de forma clara e objetiva. "
    "Use EXCLUSIVAMENTE os fatos fornecidos no JSON de contexto — nunca "
    "invente licenças, valores, datas ou nomes. Cite números e datas "
    "exatamente como aparecem nos fatos (valores estão na moeda indicada). "
    "Se os fatos não contiverem o necessário para responder, diga isso "
    "com franqueza e sugira reformular a pergunta."
)

_client: Optional[anthropic.Anthropic] = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        if not settings.anthropic_api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY não configurada no .env. "
                "Preencha a chave da Anthropic para gerar respostas."
            )
        _client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    return _client


# Chaves do contexto que servem só para a interface e NÃO vão ao modelo.
# ("consultas" = comandos MongoDB do painel "Ver a consulta"; "tempos" =
# instrumentação de latência do /ask. Ambos são ruído para o LLM, que deve
# receber apenas fatos.)
_CHAVES_SO_INTERFACE = {"consultas", "tempos"}


def _build_prompt(query: str, context: Dict[str, Any]) -> str:
    """
    Monta o prompt do usuário a partir da pergunta + fatos do grafo.
    Usado tanto pela geração normal quanto pela em streaming, para não haver
    divergência entre as duas.
    """
    # Manda ao modelo só os fatos — tira o que é exclusivo da interface.
    fatos = {k: v for k, v in context.items() if k not in _CHAVES_SO_INTERFACE}
    # `default=str` garante que datas/ObjectId virem texto no JSON.
    fatos_json = json.dumps(fatos, ensure_ascii=False, default=str, indent=2)
    return (
        f"Pergunta do usuário:\n{query}\n\n"
        f"Fatos disponíveis (JSON, vindos do grafo de inventário):\n{fatos_json}\n\n"
        "Escreva a resposta final para o usuário com base apenas nesses fatos."
    )


def generate_answer(query: str, context: Dict[str, Any]) -> str:
    """
    Gera a resposta em linguagem natural para `query` usando `context`
    (os fatos do grafo). Devolve apenas o texto da resposta.
    """
    prompt = _build_prompt(query, context)

    msg = _get_client().messages.create(
        model=MODEL,
        max_tokens=1500,
        thinking={"type": "adaptive"},
        system=SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )

    # A resposta pode conter blocos de "pensamento" + texto; pegamos só o texto.
    partes = [b.text for b in msg.content if getattr(b, "type", None) == "text"]
    return "".join(partes).strip()


def stream_answer(query: str, context: Dict[str, Any]) -> Iterator[str]:
    """
    Igual ao generate_answer, mas ENTREGA O TEXTO EM PEDAÇOS conforme o Claude
    escreve (streaming). Serve ao endpoint /ask/stream: a tela mostra a resposta
    palavra a palavra em vez de esperar tudo ficar pronto.

    `text_stream` já entrega SÓ o texto final (ignora os blocos de "pensamento"
    do adaptive thinking), então não precisamos filtrar aqui.
    """
    prompt = _build_prompt(query, context)

    with _get_client().messages.stream(
        model=MODEL,
        max_tokens=1500,
        thinking={"type": "adaptive"},
        system=SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        for pedaco in stream.text_stream:
            yield pedaco
