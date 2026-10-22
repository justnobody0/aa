from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient

from ejota.auth import _falhas, gerar_hash
from ejota.config import Settings

HOJE = date(2026, 10, 20)
SENHA = "senha-de-teste-123"


@pytest.fixture
def settings() -> Settings:
    return Settings(
        _env_file=None,
        data_source="fake",
        analyzer="heuristica",
        reference_date=HOJE,
        username="diretor",
        password_hash=gerar_hash(SENHA),
        secret_key="chave-de-teste",
        cookie_secure=False,
    )


@pytest.fixture
def client(settings: Settings) -> TestClient:
    from ejota.main import criar_app

    _falhas.clear()
    return TestClient(criar_app(settings))


@pytest.fixture
def logado(client: TestClient) -> TestClient:
    r = client.post("/login", data={"usuario": "diretor", "senha": SENHA}, follow_redirects=False)
    assert r.status_code == 303
    return client
