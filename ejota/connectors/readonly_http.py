"""Cliente HTTP que só aceita leitura.

Os conectores reais (ClickUp, Drive) vão usar este cliente. Qualquer tentativa
de POST/PUT/PATCH/DELETE levanta erro antes de sair da máquina.
"""

from __future__ import annotations

import httpx

METODOS_PERMITIDOS = frozenset({"GET", "HEAD", "OPTIONS"})


class EscritaBloqueada(RuntimeError):
    pass


def _bloquear_escrita(request: httpx.Request) -> None:
    if request.method.upper() not in METODOS_PERMITIDOS:
        raise EscritaBloqueada(f"Método {request.method} bloqueado: o sistema é somente leitura.")


def cliente_somente_leitura(base_url: str, headers: dict[str, str] | None = None, **kwargs) -> httpx.Client:
    return httpx.Client(
        base_url=base_url,
        headers=headers or {},
        event_hooks={"request": [_bloquear_escrita]},
        timeout=kwargs.pop("timeout", 30.0),
        **kwargs,
    )
