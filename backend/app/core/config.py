"""
Configuração central da aplicação.

Lê as variáveis do arquivo .env de forma validada. Se uma variável
obrigatória estiver faltando, a aplicação avisa logo na inicialização,
em vez de quebrar mais tarde de forma confusa.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Onde procurar as variáveis: no arquivo .env na raiz do projeto.
    # (o backend roda a partir da pasta backend/, então subimos um nível)
    model_config = SettingsConfigDict(
        env_file=("../.env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Banco de dados ---
    mongodb_uri: str = "mongodb://localhost:27017"
    mongodb_db: str = "graphrag"

    # --- IA (opcionais até as etapas 5 e 6) ---
    anthropic_api_key: str = ""
    voyage_api_key: str = ""

    # --- Geração da resposta (Claude) ---
    # Modelo e comportamento da redação. Ficam configuráveis (não hardcoded) para
    # trocar velocidade x sofisticação sem tocar no código:
    #   - claude_model: Sonnet é bem mais rápido que Opus e ótimo para respostas
    #     curtas ancoradas nos fatos que o grafo já entrega.
    #   - claude_thinking: quando False, o modelo NÃO raciocina antes de escrever,
    #     então a primeira palavra do streaming aparece mais cedo (melhor sensação
    #     de velocidade). Os fatos já vêm prontos, então o ganho de ligar é baixo.
    #   - claude_max_tokens: teto do tamanho da resposta.
    claude_model: str = "claude-sonnet-5"
    claude_thinking: bool = False
    claude_max_tokens: int = 1500

    # --- Pré-aquecimento do cache no startup ---
    # Ao subir o backend, dispara (em segundo plano) as perguntas fixas da demo
    # para o cache de retrieval nascer cheio — a primeira pergunta da demo já
    # responde rápido. Desligue em desenvolvimento para não gastar cota da Voyage
    # a cada restart.
    warmup_cache_on_startup: bool = True


# Instância única, importada em todo o projeto: `from app.core.config import settings`
settings = Settings()
