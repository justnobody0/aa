"""Utilitários de linha de comando.

    python -m ejota.cli hash-password      # gera EJOTA_PASSWORD_HASH
    python -m ejota.cli secret-key         # gera EJOTA_SECRET_KEY
    python -m ejota.cli relatorio-csv      # imprime o relatório em CSV
    python -m ejota.cli configurar-local   # cria .env com senha aleatória (1ª execução)
"""

from __future__ import annotations

import getpass
import os
import secrets
import sys
from pathlib import Path

from ejota.auth import gerar_hash
from ejota.config import get_settings


def configurar_local(env: Path, arquivo_senha: Path) -> int:
    """Primeira execução (ex.: Codespaces): gera senha aleatória e grava só o hash no .env.

    A senha fica em `.senha-local` (fora do git) para o diretor ler uma vez.
    Se o .env já tem senha, não muda nada.
    """
    if env.exists() and "EJOTA_PASSWORD_HASH='$" in env.read_text(encoding="utf-8"):
        print("Login já configurado (.env).")
        return 0
    senha = secrets.token_urlsafe(12)
    env.write_text(
        "EJOTA_DATA_SOURCE=fake\n"
        "EJOTA_USERNAME=diretor\n"
        f"EJOTA_PASSWORD_HASH='{gerar_hash(senha)}'\n"
        f"EJOTA_SECRET_KEY={secrets.token_urlsafe(48)}\n"
        "EJOTA_COOKIE_SECURE=true\n",
        encoding="utf-8",
    )
    arquivo_senha.write_text(senha + "\n", encoding="utf-8")
    for arquivo in (env, arquivo_senha):
        os.chmod(arquivo, 0o600)
    print(f"Login criado. Usuário: diretor | Senha: {senha} (guardada em {arquivo_senha})")
    return 0


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
    if comando == "configurar-local":
        return configurar_local(Path(".env"), Path(".senha-local"))
    if comando == "relatorio-csv":
        from ejota.report.builder import exportar_csv, gerar_relatorio

        print(exportar_csv(gerar_relatorio(get_settings())))
        return 0
    print(__doc__)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
