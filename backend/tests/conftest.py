"""
Configuração compartilhada dos testes.

Os testes são de INTEGRAÇÃO: usam o MongoDB de verdade (o mesmo do .env).
Se o banco estiver inacessível (ex.: sem rede), os testes são pulados
em vez de falhar — assim o `pytest` não quebra por causa de conexão.
"""
import pytest
from fastapi.testclient import TestClient

from app.core.db import ping
from app.main import app


@pytest.fixture(scope="session")
def client():
    try:
        ping()
    except Exception:  # noqa: BLE001
        pytest.skip("MongoDB inacessível — testes de integração pulados")
    return TestClient(app)
