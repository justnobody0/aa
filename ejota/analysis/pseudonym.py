"""Pseudonimização antes de enviar dados à API do Claude (LGPD: minimização).

Nome do cliente, valores em reais, e-mails, CPF/CNPJ e telefones são trocados
por marcadores. O mapa fica só na memória local e é usado para desfazer a troca
na exibição.
"""

from __future__ import annotations

import re

_REGRAS = [
    ("VALOR", re.compile(r"R\$\s?[\d.]+(?:,\d{2})?")),
    ("EMAIL", re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")),
    ("CNPJ", re.compile(r"\b\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}\b")),
    ("CPF", re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b")),
    ("TELEFONE", re.compile(r"\(?\b\d{2}\)?\s?9?\d{4}-?\d{4}\b")),
]


class Pseudonimizador:
    def __init__(self, nomes_sensiveis: list[str]) -> None:
        self._mapa: dict[str, str] = {}
        self._reverso: dict[str, str] = {}
        self._nomes = sorted({n for n in nomes_sensiveis if n}, key=len, reverse=True)

    def _marcador(self, tipo: str, original: str) -> str:
        if original not in self._reverso:
            n = sum(1 for m in self._mapa if m.startswith(f"[{tipo}_")) + 1
            marcador = f"[{tipo}_{n}]"
            self._mapa[marcador] = original
            self._reverso[original] = marcador
        return self._reverso[original]

    def ocultar(self, texto: str) -> str:
        for nome in self._nomes:
            texto = re.sub(re.escape(nome), lambda m: self._marcador("CLIENTE", m.group(0)), texto, flags=re.IGNORECASE)
        for tipo, regex in _REGRAS:
            texto = regex.sub(lambda m, t=tipo: self._marcador(t, m.group(0)), texto)
        return texto

    def revelar(self, texto: str) -> str:
        for marcador, original in self._mapa.items():
            texto = texto.replace(marcador, original)
        return texto
