"""Verificador de citações e regra de confiança.

Nenhuma causa chega ao relatório sem passar por aqui:
1. Cada citação precisa existir LITERALMENTE no trecho citado (após normalizar
   espaços e caixa). Citação inventada é descartada.
2. Causa sem nenhuma citação válida vira "sem evidência".
3. A confiança é calculada por regra, não declarada pela IA:
   - alta:  evidências em 2+ documentos diferentes
   - média: evidência em 1 documento, com 2+ trechos ou apoiada pelo ClickUp
   - baixa: um único trecho, sem apoio do ClickUp
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ejota.domain import Categoria, Causa, Confianca, Evidencia, Trecho


def _normalizar(texto: str) -> str:
    texto = texto.replace("“", '"').replace("”", '"').replace("’", "'")
    return re.sub(r"\s+", " ", texto).strip().strip('."').lower()


@dataclass
class CausaProposta:
    """Causa como vem do analisador (heurístico ou Claude), antes de verificar."""

    categoria: Categoria
    explicacao: str
    citacoes: list[tuple[str, str]]  # (id_trecho, citação literal)
    tarefas_relacionadas: list[str]
    principal: bool = False


def verificar(propostas: list[CausaProposta], trechos: list[Trecho], ids_tarefas_atrasadas: set[str]) -> list[Causa]:
    por_id = {t.id: t for t in trechos}
    causas: list[Causa] = []
    for p in propostas:
        evidencias: list[Evidencia] = []
        for trecho_id, citacao in p.citacoes:
            trecho = por_id.get(trecho_id)
            if not trecho or not citacao.strip():
                continue
            if _normalizar(citacao) not in _normalizar(trecho.texto):
                continue
            if any(e.trecho_id == trecho_id for e in evidencias):
                continue
            evidencias.append(Evidencia(trecho_id, citacao.strip(), trecho.titulo_documento, trecho.secao, trecho.url))

        tarefas = [t for t in p.tarefas_relacionadas if t in ids_tarefas_atrasadas]
        causas.append(
            Causa(
                categoria=p.categoria,
                explicacao=p.explicacao if evidencias else "sem evidência",
                evidencias=evidencias,
                tarefas_relacionadas=tarefas,
                confianca=calcular_confianca(evidencias, bool(tarefas)),
                principal=p.principal,
            )
        )
    return causas


def calcular_confianca(evidencias: list[Evidencia], apoio_clickup: bool) -> Confianca:
    if not evidencias:
        return Confianca.SEM_EVIDENCIA
    documentos = {e.documento for e in evidencias}
    if len(documentos) >= 2:
        return Confianca.ALTA
    if len(evidencias) >= 2 or apoio_clickup:
        return Confianca.MEDIA
    return Confianca.BAIXA
