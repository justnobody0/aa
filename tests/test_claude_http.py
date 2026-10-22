"""A chamada real ao SDK da Anthropic, contra um servidor HTTP falso local.

Confere o que sai da máquina (pseudonimizado, com saída estruturada e
fallback) e o tratamento da resposta, sem chave real nem custo.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from ejota.analysis.service import analisar_causas
from ejota.connectors.fake import FonteFicticia
from ejota.domain import Categoria
from ejota.engine.delays import analisar_projeto
from tests.conftest import HOJE

pytest.importorskip("anthropic")


def _servidor(resposta: dict):
    recebido: dict = {}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            corpo = self.rfile.read(int(self.headers["content-length"]))
            recebido["path"] = self.path
            recebido["headers"] = dict(self.headers)
            recebido["body"] = json.loads(corpo)
            dados = json.dumps(resposta).encode()
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(dados)))
            self.end_headers()
            self.wfile.write(dados)

        def log_message(self, *args):
            pass

    srv = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, recebido


def _mensagem(conteudo: list, stop_reason: str = "end_turn") -> dict:
    return {
        "id": "msg_teste", "type": "message", "role": "assistant", "model": "claude-opus-5-5",
        "content": conteudo, "stop_reason": stop_reason, "stop_sequence": None,
        "usage": {"input_tokens": 10, "output_tokens": 5},
    }


@pytest.fixture
def projeto_901():
    projeto = next(p for p in FonteFicticia().listar_projetos() if p.codigo == "EJ 26-901")
    return analisar_projeto(projeto, HOJE)


def _configurar(monkeypatch, settings, srv):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "chave-falsa")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", f"http://127.0.0.1:{srv.server_port}")
    settings.analyzer = "claude"


def test_requisicao_e_resposta_do_claude(monkeypatch, settings, projeto_901):
    from ejota.analysis.claude import pseudo_trechos
    from ejota.analysis.pseudonym import Pseudonimizador
    from ejota.documents.chunker import trechos_do_projeto

    pseudo = Pseudonimizador([projeto_901.projeto.cliente])
    ata = next(t for t in pseudo_trechos(trechos_do_projeto(projeto_901.projeto), pseudo) if "identidade visual nova" in t.texto)
    causas = {"causas": [{
        "categoria": "escopo", "explicacao": "Pedido extra de [CLIENTE_1].", "principal": True,
        "citacoes": [{"trecho_id": ata.id, "citacao": ata.texto}], "tarefas_relacionadas": ["t901-3"],
    }]}
    srv, recebido = _servidor(_mensagem([{"type": "text", "text": json.dumps(causas)}]))
    try:
        _configurar(monkeypatch, settings, srv)
        resultado = analisar_causas(projeto_901, settings)
    finally:
        srv.shutdown()

    corpo = recebido["body"]
    assert recebido["path"] == "/v1/messages"
    assert corpo["model"] == "claude-opus-5-5"
    assert corpo["output_config"]["format"]["type"] == "json_schema"
    assert corpo["fallbacks"] == "default"
    assert "server-side-fallback-2026-07-01" in recebido["headers"].get("anthropic-beta", "")
    enviado = json.dumps(corpo, ensure_ascii=False)
    assert "Padaria Aurora" not in enviado and "4.800" not in enviado  # pseudonimizado
    assert "[CLIENTE_1]" in enviado

    assert resultado.metodo.startswith("Claude")
    [causa] = resultado.causas
    assert causa.categoria == Categoria.ESCOPO and causa.evidencias
    assert "Padaria Aurora" in causa.explicacao  # revertido só na exibição


def test_recusa_do_modelo_cai_para_heuristica(monkeypatch, settings, projeto_901):
    srv, _ = _servidor(_mensagem([], stop_reason="refusal"))
    try:
        _configurar(monkeypatch, settings, srv)
        resultado = analisar_causas(projeto_901, settings)
    finally:
        srv.shutdown()
    assert resultado.metodo.startswith("heurística") and resultado.aviso
