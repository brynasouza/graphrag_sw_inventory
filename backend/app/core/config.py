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


# Instância única, importada em todo o projeto: `from app.core.config import settings`
settings = Settings()
