"""Utilitários de linha de comando.

    python -m ejota.cli hash-password      # gera EJOTA_PASSWORD_HASH
    python -m ejota.cli secret-key         # gera EJOTA_SECRET_KEY
    python -m ejota.cli relatorio-csv      # imprime o relatório em CSV
"""

from __future__ import annotations

import getpass
import secrets
import sys

from ejota.auth import gerar_hash
from ejota.config import get_settings


def main(argv: list[str]) -> int:
    comando = argv[0] if argv else ""
    if comando == "hash-password":
        senha = getpass.getpass("Senha do diretor: ")
        if len(senha) < 12:
            print("Use pelo menos 12 caracteres.", file=sys.stderr)
            return 1
        if senha != getpass.getpass("Repita: "):
            print("As senhas não conferem.", file=sys.stderr)
            return 1
        print(gerar_hash(senha))
        return 0
    if comando == "secret-key":
        print(secrets.token_urlsafe(48))
        return 0
    if comando == "relatorio-csv":
        from ejota.report.builder import exportar_csv, gerar_relatorio

        print(exportar_csv(gerar_relatorio(get_settings())))
        return 0
    print(__doc__)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
