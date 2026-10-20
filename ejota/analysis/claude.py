"""Analisador com a API do Claude.

- Recebe apenas os trechos e tarefas daquele projeto, já pseudonimizados.
- Responde em JSON validado por schema (structured outputs).
- O resultado passa depois pelo verificador de citações (verify.py), então uma
  citação inventada é descartada e a causa vira "sem evidência".
"""

from __future__ import annotations

import json
import logging

from ejota.analysis.pseudonym import Pseudonimizador
from ejota.analysis.verify import CausaProposta
from ejota.domain import Categoria, Trecho
from ejota.engine.delays import AnaliseProjeto

log = logging.getLogger(__name__)

SYSTEM = """Você é analista de projetos de uma empresa júnior de consultoria (Ejota, PUC-Rio).
Sua tarefa: explicar POR QUE um projeto atrasou, usando SOMENTE os trechos de documentos fornecidos.

Regras obrigatórias:
- Toda causa deve citar ao menos um trecho pelo seu id e copiar a citação LITERALMENTE do texto do trecho.
- Não use conhecimento externo e não suponha fatos. Se nenhum trecho sustenta uma causa, não a inclua.
- Se nada nos trechos explica o atraso, devolva uma única causa de categoria "outra" com citacoes vazias.
- Categorias: escopo, cliente, equipe, prazo mal estimado, contrato, outra.
  "contrato" = cláusula que falhou ou brecha deixada no contrato/proposta.
- Marque exatamente uma causa como principal.
- Tarefas "entregue no prazo, aguardando validação do cliente" não são atraso da EJ, mas podem indicar causa "cliente".
- Marcadores como [CLIENTE_1] ou [VALOR_1] substituem dados sensíveis; mantenha-os como estão.
- Escreva em português, de forma objetiva, para o diretor de projetos."""

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["causas"],
    "properties": {
        "causas": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["categoria", "explicacao", "principal", "citacoes", "tarefas_relacionadas"],
                "properties": {
                    "categoria": {"type": "string", "enum": [c.value for c in Categoria]},
                    "explicacao": {"type": "string"},
                    "principal": {"type": "boolean"},
                    "citacoes": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["trecho_id", "citacao"],
                            "properties": {"trecho_id": {"type": "string"}, "citacao": {"type": "string"}},
                        },
                    },
                    "tarefas_relacionadas": {"type": "array", "items": {"type": "string"}},
                },
            },
        }
    },
}


class RecusaDoModelo(RuntimeError):
    pass


def montar_dossie(analise: AnaliseProjeto, trechos: list[Trecho], pseudo: Pseudonimizador) -> str:
    tarefas = []
    for a in analise.tarefas:
        t = a.tarefa
        tarefas.append(
            {
                "id": t.id,
                "nome": pseudo.ocultar(t.nome),
                "etapa": pseudo.ocultar(t.lista),
                "status": t.status.value,
                "prazo": t.prazo.isoformat() if t.prazo else None,
                "situacao": a.situacao.value,
                "dias_atraso": a.dias_atraso,
                "dias_em_cada_status": a.tempo_em_status,
                "tem_responsavel": bool(t.responsaveis),
            }
        )
    docs = [
        {"id": tr.id, "documento": pseudo.ocultar(tr.titulo_documento), "secao": pseudo.ocultar(tr.secao), "texto": pseudo.ocultar(tr.texto)}
        for tr in trechos
    ]
    dossie = {
        "projeto": analise.projeto.codigo,
        "data_de_referencia": analise.hoje.isoformat(),
        "prazo_do_projeto": analise.prazo_projeto.isoformat() if analise.prazo_projeto else None,
        "tarefas": tarefas,
        "trechos": docs,
    }
    return json.dumps(dossie, ensure_ascii=False, indent=1)


def pseudo_trechos(trechos: list[Trecho], pseudo: Pseudonimizador) -> list[Trecho]:
    return [
        Trecho(t.id, t.documento_id, t.tipo, pseudo.ocultar(t.titulo_documento), pseudo.ocultar(t.secao), pseudo.ocultar(t.texto), t.url)
        for t in trechos
    ]


def propor_causas(analise: AnaliseProjeto, trechos: list[Trecho], pseudo: Pseudonimizador, model: str) -> list[CausaProposta]:
    import anthropic  # dependência opcional (extra "ia")

    client = anthropic.Anthropic()  # lê ANTHROPIC_API_KEY do ambiente
    response = client.messages.create(
        model=model,
        max_tokens=16000,
        system=SYSTEM,
        output_config={"effort": "high", "format": {"type": "json_schema", "schema": SCHEMA}},
        messages=[{"role": "user", "content": "Dossiê do projeto (JSON):\n" + montar_dossie(analise, trechos, pseudo)}],
        # Se o modelo recusar por política, a API tenta de novo em outro modelo.
        extra_headers={"anthropic-beta": "server-side-fallback-2026-07-01"},
        extra_body={"fallbacks": "default"},
    )
    if response.stop_reason == "refusal":
        raise RecusaDoModelo("o modelo recusou a análise")
    log.info("Claude analisou %s (entrada=%s, saída=%s tokens)", analise.projeto.codigo,
             response.usage.input_tokens, response.usage.output_tokens)

    texto = next(b.text for b in response.content if b.type == "text")
    dados = json.loads(texto)
    return [
        CausaProposta(
            categoria=Categoria(c["categoria"]),
            explicacao=c["explicacao"],
            citacoes=[(x["trecho_id"], x["citacao"]) for x in c["citacoes"]],
            tarefas_relacionadas=c["tarefas_relacionadas"],
            principal=c["principal"],
        )
        for c in dados["causas"]
    ]
