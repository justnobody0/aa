"""Aplicação web: login + relatório + exportação."""

from __future__ import annotations

import logging
import secrets
import threading
from pathlib import Path

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from ejota import auth
from ejota.config import Settings, get_settings
from ejota.logging_setup import setup_logging
from ejota.report.builder import Relatorio, exportar_csv, gerar_relatorio

BASE = Path(__file__).resolve().parent
log = logging.getLogger("ejota")


class Exigelogin(Exception):
    pass


def criar_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    setup_logging(settings.log_level)

    secret = settings.secret_key
    if not secret:
        secret = secrets.token_urlsafe(48)
        log.warning("EJOTA_SECRET_KEY não definida: usando chave temporária (sessões caem ao reiniciar).")
    if not settings.password_hash:
        log.warning("EJOTA_PASSWORD_HASH não definida: ninguém consegue entrar. Gere com `python -m ejota.cli hash-password`.")

    app = FastAPI(title="Rede neural da Ejota", docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(
        SessionMiddleware,
        secret_key=secret,
        session_cookie="ejota_sessao",
        max_age=settings.session_max_age_s,
        same_site="strict",
        https_only=settings.cookie_secure,
    )
    app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")
    templates = Jinja2Templates(directory=BASE / "templates")

    cache: dict[str, Relatorio] = {}
    trava = threading.Lock()

    def relatorio_atual(forcar: bool = False) -> Relatorio:
        with trava:
            if forcar or "atual" not in cache:
                cache["atual"] = gerar_relatorio(settings)
            return cache["atual"]

    def exigir_login(request: Request) -> str:
        usuario = auth.usuario_logado(request)
        if not usuario:
            raise Exigelogin()
        return usuario

    @app.exception_handler(Exigelogin)
    async def _redirecionar_login(request: Request, exc: Exigelogin):
        return RedirectResponse("/login", status_code=303)

    @app.middleware("http")
    async def _cabecalhos_seguranca(request: Request, call_next):
        resp = await call_next(request)
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["Referrer-Policy"] = "no-referrer"
        resp.headers["Cache-Control"] = "no-store"
        resp.headers["Content-Security-Policy"] = "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'"
        return resp

    @app.get("/saude", response_class=PlainTextResponse)
    def saude() -> str:
        return "ok"

    @app.get("/login", response_class=HTMLResponse)
    def login_form(request: Request):
        return templates.TemplateResponse(request, "login.html", {"erro": None, "sem_senha": not settings.password_hash})

    @app.post("/login", response_class=HTMLResponse)
    def login(request: Request, usuario: str = Form(...), senha: str = Form(...)):
        ip = request.client.host if request.client else "?"
        if auth.verificar_login(settings, ip, usuario, senha):
            request.session.clear()
            request.session["usuario"] = usuario
            log.info("Login bem-sucedido")
            return RedirectResponse("/", status_code=303)
        log.warning("Falha de login")
        erro = "Muitas tentativas. Aguarde 5 minutos." if auth.bloqueado(ip) else "Usuário ou senha inválidos."
        ctx = {"erro": erro, "sem_senha": not settings.password_hash}
        return templates.TemplateResponse(request, "login.html", ctx, status_code=401)

    @app.post("/logout")
    def logout(request: Request):
        request.session.clear()
        return RedirectResponse("/login", status_code=303)

    @app.get("/", response_class=HTMLResponse)
    def visao_geral(request: Request, _: str = Depends(exigir_login)):
        return templates.TemplateResponse(request, "overview.html", {"r": relatorio_atual()})

    @app.post("/atualizar")
    def atualizar(_: str = Depends(exigir_login)):
        relatorio_atual(forcar=True)
        return RedirectResponse("/", status_code=303)

    @app.get("/projeto/{slug}", response_class=HTMLResponse)
    def detalhe(request: Request, slug: str, _: str = Depends(exigir_login)):
        r = relatorio_atual()
        p = r.projeto(slug)
        if not p:
            raise HTTPException(404, "Projeto não encontrado")
        return templates.TemplateResponse(request, "project.html", {"r": r, "p": p})

    @app.get("/exportar/relatorio.html", response_class=HTMLResponse)
    def exportar_html(request: Request, _: str = Depends(exigir_login)):
        r = relatorio_atual()
        css = (BASE / "static" / "style.css").read_text(encoding="utf-8")
        resp = templates.TemplateResponse(request, "export.html", {"r": r, "css": css})
        nome = f"relatorio-atrasos-{r.data_referencia.isoformat()}.html"
        resp.headers["Content-Disposition"] = f'attachment; filename="{nome}"'
        return resp

    @app.get("/exportar/relatorio.csv")
    def exportar_csv_rota(_: str = Depends(exigir_login)):
        r = relatorio_atual()
        nome = f"relatorio-atrasos-{r.data_referencia.isoformat()}.csv"
        # BOM para o Excel abrir acentos corretamente.
        return Response(
            "﻿" + exportar_csv(r),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{nome}"'},
        )

    return app


app = criar_app()
