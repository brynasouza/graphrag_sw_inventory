"""
Conexão com o MongoDB Atlas.

Criamos UM cliente (pool de conexões) e o reaproveitamos em toda a
aplicação. Abrir uma conexão nova a cada consulta seria lento e caro.

A conexão é "preguiçosa": o cliente só é criado no primeiro uso. Assim,
se a URI estiver errada, o erro aparece de forma amigável no endpoint
/health, e não como um crash na inicialização da aplicação.
"""
from typing import Optional

from pymongo import MongoClient
from pymongo.database import Database

from app.core.config import settings

_client: Optional[MongoClient] = None


def get_client() -> MongoClient:
    """Cria (na primeira vez) e devolve o cliente único do MongoDB."""
    global _client
    if _client is None:
        # Timeouts curtos: se o Atlas estiver fora do ar, a falha aparece em
        # ~5s (com mensagem clara na tela) em vez de congelar os 30s do default
        # do pymongo — o que numa demo pareceria travamento.
        _client = MongoClient(
            settings.mongodb_uri,
            serverSelectionTimeoutMS=5000,
            connectTimeoutMS=5000,
        )
    return _client


def get_db() -> Database:
    """Devolve o banco de dados configurado no .env."""
    return get_client()[settings.mongodb_db]


def ping() -> bool:
    """
    Testa se a conexão com o Atlas está de pé.
    Retorna True se o banco responde ao comando 'ping'.
    """
    get_client().admin.command("ping")
    return True
