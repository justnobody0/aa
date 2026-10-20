"""Analisador heurístico (sem IA).

Serve para rodar o sistema sem chave de API e como linha de base para comparar
com o Claude. Procura palavras-chave por categoria nos trechos dos documentos.
Uma categoria só entra se houver ao menos um trecho da ATA (dificuldade ou LA)
apontando para ela; os demais documentos reforçam a evidência.
"""

from __future__ import annotations

import re
import unicodedata

from ejota.analysis.verify import CausaProposta
from ejota.domain import Categoria, TipoDocumento, Trecho
from ejota.engine.delays import AnaliseProjeto

PALAVRAS: dict[Categoria, tuple[str, ...]] = {
    Categoria.ESCOPO: ("escopo", "nova demanda", "novas demandas", "pedido extra", "nao estao incluidos", "identidade visual nova"),
    Categoria.CLIENTE: (
        "solicitados ao cliente", "cliente remarcou", "contratante devera fornecer", "atrasos da contratante",
        "cliente atrasar", "responsavel do cliente",
    ),
    Categoria.EQUIPE: ("saiu da", "saida", "periodo de provas", "disponibilidade da equipe", "sem responsavel", "cobertura"),
    Categoria.PRAZO: ("estimativa", "estimadas", "do previsto", "subestim", "historico de projetos", "horas previstas"),
    Categoria.CONTRATO: ("comum acordo", "nao foi especificado", "nao foi formalizada", "sem aditivo", "prorrogam"),
}

EXPLICACOES: dict[Categoria, str] = {
    Categoria.ESCOPO: "O escopo cresceu durante o projeto com demandas que não estavam previstas na proposta.",
    Categoria.CLIENTE: "O cliente atrasou o envio de informações ou as validações, o que travou etapas dependentes.",
    Categoria.EQUIPE: "A equipe perdeu capacidade (saída de membro, provas ou tarefas sem responsável).",
    Categoria.PRAZO: "O esforço real da etapa ficou bem acima do estimado na precificação.",
    Categoria.CONTRATO: "O contrato ou a proposta deixou uma brecha (ou uma cláusula não foi aplicada), sem proteger o prazo.",
}


def _norm(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return sem_acento.lower()


def _palavras_relevantes(texto: str) -> set[str]:
    return {p for p in re.findall(r"[a-z]{5,}", _norm(texto))}


def propor_causas(analise: AnaliseProjeto, trechos: list[Trecho]) -> list[CausaProposta]:
    atrasadas = analise.atrasadas
    relevantes = [t for t in trechos if t.tipo != TipoDocumento.TAP]

    candidatas: list[tuple[tuple[int, int, int], CausaProposta]] = []
    for categoria, palavras in PALAVRAS.items():
        achados = [t for t in relevantes if any(p in _norm(t.texto) for p in palavras)]
        if not any(t.tipo == TipoDocumento.ATA for t in achados):
            continue
        # A ATA (registro do problema) vem primeiro; contrato/proposta reforçam.
        da_ata = [t for t in achados if t.tipo == TipoDocumento.ATA]
        achados = da_ata[:3] + [t for t in achados if t.tipo != TipoDocumento.ATA][:2]

        tarefas: set[str] = set()
        vocab = _palavras_relevantes(" ".join(t.texto for t in achados if t.tipo == TipoDocumento.ATA))
        for a in atrasadas:
            if _palavras_relevantes(a.tarefa.nome) & vocab:
                tarefas.add(a.tarefa.id)
            if categoria == Categoria.CLIENTE and a.atraso_na_validacao:
                tarefas.add(a.tarefa.id)
            if categoria == Categoria.EQUIPE and not a.tarefa.responsaveis:
                tarefas.add(a.tarefa.id)

        proposta = CausaProposta(
            categoria=categoria,
            explicacao=EXPLICACOES[categoria],
            citacoes=[(t.id, t.texto) for t in achados],
            tarefas_relacionadas=sorted(tarefas),
        )
        # Principal = mais registros diretos na ATA; depois, mais documentos de apoio.
        peso = (len(da_ata), len({t.documento_id for t in achados}), len(achados) + len(tarefas))
        candidatas.append((peso, proposta))

    if not candidatas:
        return [CausaProposta(Categoria.OUTRA, "sem evidência", [], [a.tarefa.id for a in atrasadas])]

    candidatas.sort(key=lambda c: c[0], reverse=True)
    candidatas[0][1].principal = True
    return [c[1] for c in candidatas]
