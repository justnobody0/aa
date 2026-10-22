"""Login de usuário único (o diretor), com limite de tentativas."""

from __future__ import annotations

import hmac
import secrets
import time
from collections import defaultdict

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Request

from ejota.config import Settings

_hasher = PasswordHasher()

MAX_TENTATIVAS = 5
BLOQUEIO_S = 300
_falhas: dict[str, list[float]] = defaultdict(list)


def gerar_hash(senha: str) -> str:
    return _hasher.hash(senha)


def bloqueado(ip: str) -> bool:
    agora = time.monotonic()
    _falhas[ip] = [t for t in _falhas[ip] if agora - t < BLOQUEIO_S]
    return len(_falhas[ip]) >= MAX_TENTATIVAS


def verificar_login(settings: Settings, ip: str, usuario: str, senha: str) -> bool:
    if bloqueado(ip) or not settings.password_hash:
        return False
    usuario_ok = hmac.compare_digest(usuario.encode(), settings.username.encode())
    try:
        senha_ok = _hasher.verify(settings.password_hash, senha)
    except (VerificationError, InvalidHashError):
        senha_ok = False
    if usuario_ok and senha_ok:
        _falhas.pop(ip, None)
        return True
    _falhas[ip].append(time.monotonic())
    return False


# Sessões ativas ficam no servidor: o cookie só carrega um identificador
# aleatório. Assim o logout revoga a sessão de verdade (um cookie copiado deixa
# de valer). Reiniciar o servidor encerra todas as sessões.
_sessoes_ativas: set[str] = set()


def abrir_sessao(request: Request, usuario: str) -> None:
    request.session.clear()
    sid = secrets.token_urlsafe(32)
    _sessoes_ativas.add(sid)
    request.session.update({"usuario": usuario, "sid": sid})


def encerrar_sessao(request: Request) -> None:
    _sessoes_ativas.discard(request.session.get("sid", ""))
    request.session.clear()


def usuario_logado(request: Request) -> str | None:
    if request.session.get("sid") not in _sessoes_ativas:
        return None
    return request.session.get("usuario")
