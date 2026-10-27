from __future__ import annotations

import logging

import httpx
import pytest

from ejota.connectors.readonly_http import EscritaBloqueada, cliente_somente_leitura
from ejota.logging_setup import sanitize


def test_paginas_exigem_login(client):
    for url in ["/", "/projeto/ej-26-901", "/exportar/relatorio.csv", "/exportar/relatorio.html"]:
        r = client.get(url, follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"] == "/login", url


def test_saude_sem_login(client):
    assert client.get("/saude").text == "ok"


def test_login_errado_e_bloqueio(client):
    for _ in range(5):
        assert client.post("/login", data={"usuario": "diretor", "senha": "errada"}).status_code == 401
    r = client.post("/login", data={"usuario": "diretor", "senha": "senha-de-teste-123"})
    assert r.status_code == 401 and "Muitas tentativas" in r.text


def test_metricas_rede_e_atrasos(logado):
    m = logado.get("/")
    assert m.status_code == 200 and "Pontualidade".lower() in m.text.lower() and "carteira orçada" in m.text
    assert "fictícios" in m.text and "Padaria Aurora" in m.text
    rede = logado.get("/rede")
    assert rede.status_code == 200 and 'id="dados-rede"' in rede.text and "area:Processos" in rede.text
    assert logado.get("/static/rede.js").status_code == 200
    r = logado.get("/atrasos")
    assert r.status_code == 200
    assert "Por que os projetos atrasaram" in r.text and "fictícios" in r.text
    assert "Padaria Aurora" in r.text
    d = logado.get("/projeto/ej-26-902")
    assert "Causa principal: cliente" in d.text
    assert "4.2 A CONTRATANTE deverá fornecer" in d.text
    assert logado.get("/projeto/nao-existe").status_code == 404


def test_exportacoes(logado):
    csv = logado.get("/exportar/relatorio.csv")
    assert csv.headers["content-type"].startswith("text/csv")
    assert "EJ 26-904" in csv.text and "prazo mal estimado" in csv.text
    html = logado.get("/exportar/relatorio.html")
    assert "attachment" in html.headers["content-disposition"]
    assert "<style>" in html.text and "Relatório de atrasos" in html.text


def test_logout(logado):
    logado.post("/logout")
    assert logado.get("/", follow_redirects=False).status_code == 303


def test_cliente_http_bloqueia_escrita():
    transport = httpx.MockTransport(lambda req: httpx.Response(200, json={}))
    with cliente_somente_leitura("https://api.exemplo", transport=transport) as c:
        assert c.get("/x").status_code == 200
        for metodo in ["POST", "PUT", "PATCH", "DELETE"]:
            with pytest.raises(EscritaBloqueada):
                c.request(metodo, "/x")


def test_logs_sem_dados_de_cliente():
    limpo = sanitize("Valor R$ 4.800,00 (a@b.com). Projeto EJ 26-901 | Padaria Aurora atrasou")
    assert limpo == "Valor R$[oculto] ([email]). Projeto EJ 26-901"
    from ejota.logging_setup import SanitizingFilter

    rec = logging.LogRecord("x", logging.INFO, "", 0, "cliente %s", ("EJ 26-902 | Clínica Horizonte",), None)
    SanitizingFilter().filter(rec)
    assert "Clínica" not in rec.getMessage()


def test_hash_entre_aspas_e_aceito():
    from ejota.config import Settings

    assert Settings(_env_file=None, password_hash="'$argon2id$abc'").password_hash == "$argon2id$abc"


def test_bibliotecas_de_rede_nao_logam_corpo_em_debug():
    from ejota.logging_setup import BIBLIOTECAS_SILENCIADAS, setup_logging

    setup_logging("DEBUG")
    for nome in BIBLIOTECAS_SILENCIADAS:
        assert not logging.getLogger(nome).isEnabledFor(logging.DEBUG), nome


def test_cookie_copiado_nao_vale_depois_do_logout(logado):
    copiado = logado.cookies.get("ejota_sessao")
    logado.post("/logout")
    logado.cookies.set("ejota_sessao", copiado)
    assert logado.get("/", follow_redirects=False).status_code == 303


def test_configurar_local_cria_login_uma_vez(tmp_path):
    from argon2 import PasswordHasher

    from ejota.cli import configurar_local
    from ejota.config import Settings

    env, senha_arq = tmp_path / ".env", tmp_path / ".senha-local"
    assert configurar_local(env, senha_arq) == 0
    senha = senha_arq.read_text().strip()
    cfg = Settings(_env_file=str(env))
    assert PasswordHasher().verify(cfg.password_hash, senha)
    assert cfg.secret_key and cfg.cookie_secure
    assert oct(env.stat().st_mode)[-3:] == "600"
    antes = env.read_text()
    configurar_local(env, senha_arq)  # segunda vez não troca a senha
    assert env.read_text() == antes


def test_exportar_painel_autocontido(logado):
    r = logado.get("/exportar/painel.html")
    assert r.status_code == 200 and "attachment" in r.headers["content-disposition"]
    assert 'id="dados-rede"' in r.text and "carteira orçada" in r.text and "<style>" in r.text
    assert "/static/" not in r.text
    assert "&#34;" not in r.text.split("</style>")[0]  # CSS sem escape de HTML
