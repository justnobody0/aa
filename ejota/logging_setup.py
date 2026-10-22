"""Logs sem dados de clientes nem valores (LGPD).

Regra: o código só registra códigos de projeto (ex.: "EJ 26-901"), contagens e
tempos. Como rede de segurança, o filtro abaixo mascara valores em reais,
e-mails, CPF/CNPJ e o nome do cliente que vem depois de "EJ 26-XXX |".
"""

from __future__ import annotations

import logging
import re

_PATTERNS = [
    (re.compile(r"(EJ \d{2}-\d{3})\s*\|\s*[^,;)\n]+"), r"\1"),
    (re.compile(r"R\$\s?[\d.,]+"), "R$[oculto]"),
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"), "[email]"),
    (re.compile(r"\b\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}\b"), "[cnpj]"),
    (re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b"), "[cpf]"),
]


BIBLIOTECAS_SILENCIADAS = ("anthropic", "httpx", "httpx2", "httpcore", "httpcore2", "urllib3", "googleapiclient")


def sanitize(text: str) -> str:
    for pattern, repl in _PATTERNS:
        text = pattern.sub(repl, text)
    return text


class SanitizingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = sanitize(record.getMessage())
        record.args = ()
        return True


def setup_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    handler.addFilter(SanitizingFilter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
    # Bibliotecas de rede registram o corpo das requisições em DEBUG (incluindo o
    # dossiê enviado ao Claude). Ficam sempre em WARNING, qualquer que seja o nível.
    for nome in BIBLIOTECAS_SILENCIADAS:
        logging.getLogger(nome).setLevel(logging.WARNING)
