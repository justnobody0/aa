"""Configuração lida somente de variáveis de ambiente (nunca de segredos no código)."""

from __future__ import annotations

from datetime import date
from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="EJOTA_", env_file=".env", extra="ignore")

    # Fonte de dados: "fake" (fictícios) até haver autorização da diretoria.
    data_source: Literal["fake", "real"] = "fake"

    # Login de usuário único (o diretor).
    username: str = "diretor"
    password_hash: str = Field(default="", description="Hash argon2; gere com `python -m ejota.cli hash-password`")
    secret_key: str = Field(default="", description="Chave para assinar o cookie de sessão")
    session_max_age_s: int = 8 * 3600
    cookie_secure: bool = True

    # Análise de causa: "heuristica" roda sem IA; "claude" usa a API do Claude.
    analyzer: Literal["heuristica", "claude"] = "heuristica"
    anthropic_model: str = "claude-opus-5-5"

    # Data de referência do relatório (vazio = hoje). Útil para testes reprodutíveis.
    reference_date: date | None = None

    # Credenciais das fontes reais (usadas só a partir da Etapa 7).
    clickup_token: str = ""
    clickup_team_id: str = ""
    clickup_space_name: str = "Projetos"
    google_credentials_file: str = ""
    google_shared_drive_id: str = ""

    log_level: str = "INFO"

    @field_validator("password_hash", "secret_key", "clickup_token", mode="before")
    @classmethod
    def _sem_aspas(cls, v: str) -> str:
        # `docker run --env-file` mantém aspas literais; `docker compose` e .env local não.
        if isinstance(v, str) and len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"":
            return v[1:-1]
        return v

    def today(self) -> date:
        return self.reference_date or date.today()


@lru_cache
def get_settings() -> Settings:
    return Settings()
