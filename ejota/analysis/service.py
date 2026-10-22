"""Orquestra a análise de causa de um projeto atrasado."""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace

from ejota.analysis import heuristic
from ejota.analysis.pseudonym import Pseudonimizador
from ejota.analysis.verify import verificar
from ejota.config import Settings
from ejota.documents.chunker import trechos_do_projeto
from ejota.domain import Causa, Evidencia
from ejota.engine.delays import AnaliseProjeto

log = logging.getLogger(__name__)


@dataclass
class ResultadoCausas:
    causas: list[Causa]
    metodo: str  # "heurística (sem IA)" ou "Claude (<modelo>)"
    aviso: str = ""


def analisar_causas(analise: AnaliseProjeto, settings: Settings) -> ResultadoCausas:
    trechos = trechos_do_projeto(analise.projeto)
    ids_atrasadas = {a.tarefa.id for a in analise.atrasadas}

    if settings.analyzer == "arquivo":
        return _de_arquivo(analise, trechos, ids_atrasadas, settings)
    if settings.analyzer == "claude":
        try:
            return _com_claude(analise, trechos, ids_atrasadas, settings)
        except Exception as exc:  # noqa: BLE001 — falha da IA não pode derrubar o relatório
            log.warning("Falha na análise com Claude em %s: %s", analise.projeto.codigo, type(exc).__name__)
            resultado = _heuristica(analise, trechos, ids_atrasadas)
            resultado.aviso = "A análise com IA falhou; exibindo a heurística."
            return resultado
    return _heuristica(analise, trechos, ids_atrasadas)


def _heuristica(analise, trechos, ids_atrasadas) -> ResultadoCausas:
    propostas = heuristic.propor_causas(analise, trechos)
    return ResultadoCausas(_ordenar(verificar(propostas, trechos, ids_atrasadas)), "heurística (sem IA)")


def _de_arquivo(analise, trechos, ids_atrasadas, settings: Settings) -> ResultadoCausas:
    """Causas propostas fora do sistema (ex.: análise feita pelo Claude numa sessão),
    gravadas em `causas_propostas.json` no snapshot. Passam pelo mesmo verificador."""
    import json
    from pathlib import Path

    from ejota.analysis.verify import CausaProposta
    from ejota.domain import Categoria

    caminho = Path(settings.snapshot_dir) / "causas_propostas.json"
    dados = json.loads(caminho.read_text(encoding="utf-8")) if caminho.exists() else {}
    bruto = dados.get(analise.projeto.codigo)
    if not bruto:
        resultado = _heuristica(analise, trechos, ids_atrasadas)
        resultado.aviso = "Sem análise registrada para este projeto; exibindo a heurística."
        return resultado
    propostas = [
        CausaProposta(
            categoria=Categoria(c["categoria"]),
            explicacao=c["explicacao"],
            citacoes=[(x["trecho_id"], x["citacao"]) for x in c["citacoes"]],
            tarefas_relacionadas=c.get("tarefas_relacionadas", []),
            principal=c.get("principal", False),
        )
        for c in bruto["causas"]
    ]
    return ResultadoCausas(_ordenar(verificar(propostas, trechos, ids_atrasadas)), bruto.get("metodo", "análise registrada"))


def _com_claude(analise, trechos, ids_atrasadas, settings: Settings) -> ResultadoCausas:
    from ejota.analysis import claude

    pseudo = Pseudonimizador([analise.projeto.cliente])
    trechos_ocultos = claude.pseudo_trechos(trechos, pseudo)
    propostas = claude.propor_causas(analise, trechos, pseudo, settings.anthropic_model)
    causas = verificar(propostas, trechos_ocultos, ids_atrasadas)
    revelar = pseudo.revelar
    causas = [
        replace(
            c,
            explicacao=revelar(c.explicacao),
            evidencias=[Evidencia(e.trecho_id, revelar(e.citacao), revelar(e.documento), revelar(e.secao), e.url) for e in c.evidencias],
        )
        for c in causas
    ]
    return ResultadoCausas(_ordenar(causas), f"Claude ({settings.anthropic_model})")


def _ordenar(causas: list[Causa]) -> list[Causa]:
    # Causa principal sem evidência perde o posto para a melhor causa com evidência.
    if causas and not any(c.principal and c.evidencias for c in causas):
        com_evidencia = [c for c in causas if c.evidencias]
        for c in causas:
            c.principal = False
        (com_evidencia or causas)[0].principal = True
    return sorted(causas, key=lambda c: (not c.principal, not c.evidencias))
