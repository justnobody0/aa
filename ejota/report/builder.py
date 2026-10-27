"""Monta o relatório: junta motor de atraso + análise de causa + comparação."""

from __future__ import annotations

import csv
import io
import logging
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime

from ejota.analysis.service import ResultadoCausas, analisar_causas
from ejota.config import Settings
from ejota.connectors import get_source
from ejota.domain import Categoria, Causa, Status
from ejota.engine.delays import AnaliseProjeto, analisar_projeto
from ejota.metrics.indicadores import Metricas, calcular_metricas
from ejota.metrics.rede import Rede, montar_rede

log = logging.getLogger(__name__)


@dataclass
class RelatorioProjeto:
    analise: AnaliseProjeto
    causas: ResultadoCausas | None  # None quando o projeto não está atrasado

    @property
    def codigo(self) -> str:
        return self.analise.projeto.codigo

    @property
    def slug(self) -> str:
        return self.codigo.replace(" ", "-").lower()

    @property
    def causa_principal(self) -> Causa | None:
        if not self.causas:
            return None
        return next((c for c in self.causas.causas if c.principal), None)

    @property
    def tempo_medio_status(self) -> dict[str, float]:
        """Média de dias em cada status, nas tarefas atrasadas do projeto."""
        atrasadas = [a for a in self.analise.atrasadas if a.tempo_em_status]
        if not atrasadas:
            return {}
        return {
            s.value: round(sum(a.tempo_em_status[s.value] for a in atrasadas) / len(atrasadas), 1)
            for s in Status
            if s != Status.VALIDADO
        }


@dataclass
class Relatorio:
    gerado_em: datetime
    data_referencia: date
    fonte: str
    projetos: list[RelatorioProjeto]
    tarefas_teste_ignoradas: int = 0
    causas_por_categoria: list[tuple[str, int]] = field(default_factory=list)
    metricas: Metricas | None = None
    rede: Rede | None = None

    @property
    def atrasados(self) -> list[RelatorioProjeto]:
        return [p for p in self.projetos if p.analise.atrasado]

    @property
    def total_tarefas_atrasadas(self) -> int:
        return sum(len(p.analise.atrasadas) for p in self.projetos)

    @property
    def total_aguardando_cliente(self) -> int:
        return sum(len(p.analise.aguardando_cliente) for p in self.projetos)

    @property
    def total_lacunas(self) -> int:
        return sum(p.analise.lacunas.total for p in self.projetos)

    def projeto(self, slug: str) -> RelatorioProjeto | None:
        return next((p for p in self.projetos if p.slug == slug), None)


def gerar_relatorio(settings: Settings) -> Relatorio:
    hoje = settings.today()
    projetos = get_source(settings).listar_projetos()
    itens: list[RelatorioProjeto] = []
    for projeto in projetos:
        analise = analisar_projeto(projeto, hoje)
        causas = analisar_causas(analise, settings) if analise.atrasado else None
        itens.append(RelatorioProjeto(analise, causas))

    itens.sort(key=lambda p: (not p.analise.atrasado, -p.analise.soma_dias_atraso, p.codigo))
    contagem = Counter(p.causa_principal.categoria.value for p in itens if p.causa_principal)
    por_categoria = [(c.value, contagem.get(c.value, 0)) for c in Categoria]
    causas = {p.codigo: p.causas.causas for p in itens if p.causas}
    metricas = calcular_metricas([p.analise for p in itens], causas)
    log.info("Relatório gerado: %d projetos, %d atrasados", len(itens), sum(p.analise.atrasado for p in itens))
    return Relatorio(
        gerado_em=datetime.now(),
        data_referencia=hoje,
        fonte="dados fictícios" if settings.data_source == "fake" else "ClickUp + Google Drive",
        projetos=itens,
        tarefas_teste_ignoradas=sum(p.analise.tarefas_teste_ignoradas for p in itens),
        causas_por_categoria=por_categoria,
        metricas=metricas,
        rede=montar_rede(metricas, causas),
    )


class _CsvSeguro:
    """Evita injeção de fórmulas ao abrir o CSV no Excel/Sheets."""

    def __init__(self, buf: io.StringIO) -> None:
        self._w = csv.writer(buf, delimiter=";")

    def writerow(self, row: list) -> None:
        self._w.writerow(["'" + c if isinstance(c, str) and c and c[0] in "=+-@" else c for c in row])


def exportar_csv(relatorio: Relatorio) -> str:
    """Uma linha por causa (ou por projeto, se não estiver atrasado)."""
    buf = io.StringIO()
    w = _CsvSeguro(buf)
    w.writerow([
        "projeto", "atrasado", "tarefas", "tarefas_atrasadas", "aguardando_cliente", "maior_atraso_dias",
        "prazo_projeto", "categoria", "principal", "confianca", "explicacao", "evidencias", "lacunas",
    ])
    for p in relatorio.projetos:
        a = p.analise
        base = [
            a.projeto.nome, "sim" if a.atrasado else "não", len(a.tarefas), len(a.atrasadas),
            len(a.aguardando_cliente), a.maior_atraso_dias, a.prazo_projeto.isoformat() if a.prazo_projeto else "",
        ]
        causas = p.causas.causas if p.causas else []
        if not causas:
            w.writerow(base + ["", "", "", "", "", a.lacunas.total])
            continue
        for c in causas:
            evid = " | ".join(f'{e.documento} [{e.secao}]: "{e.citacao}"' for e in c.evidencias) or "sem evidência"
            w.writerow(base + [c.categoria.value, "sim" if c.principal else "não", c.confianca.value, c.explicacao, evid, a.lacunas.total])
    return buf.getvalue()
