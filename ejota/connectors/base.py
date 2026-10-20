"""Interface única para qualquer fonte de projetos.

A fonte fictícia, o ClickUp e o Drive entregam os mesmos objetos de domínio,
então o motor de atraso, a análise e o relatório não sabem de onde vêm os dados.
"""

from __future__ import annotations

from typing import Protocol

from ejota.domain import Projeto


class FonteDeProjetos(Protocol):
    def listar_projetos(self) -> list[Projeto]: ...
