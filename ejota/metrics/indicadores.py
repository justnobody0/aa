"""Indicadores da carteira: entrega, projetos e comercial.

Tudo é calculado com regras fixas e explicáveis, a partir do motor de atraso
(ClickUp) e da Planilha de Precificação (Drive). Nenhum número é estimado:
quando falta dado, o indicador diz em quantos projetos ou tarefas ele se apoia.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from statistics import median

from ejota.engine.delays import AnaliseProjeto, AnaliseTarefa, Situacao

# Situações em que já dá para dizer se a tarefa cumpriu o prazo.
_AVALIAVEIS = {
    Situacao.ATRASADA_ABERTA,
    Situacao.ATRASADA_FECHADA,
    Situacao.ENTREGUE_COM_ATRASO,
    Situacao.AGUARDANDO_CLIENTE,
    Situacao.CONCLUIDA_NO_PRAZO,
}
_NO_PRAZO = {Situacao.AGUARDANDO_CLIENTE, Situacao.CONCLUIDA_NO_PRAZO}

_ATRASO_GRAVE_DIAS = 30


def area_da_lista(lista: str) -> str:
    """Área da EJ a partir do nome da lista do ClickUp ("Processos · Sprint 2" → "Processos")."""
    base = lista.split("·")[0].strip()
    base = re.sub(r"\s+e\s+Gest[ãa]o$", "", base)
    if base.lower().replace("-", " ") in ("tech dev", "web dev"):
        return "Tech-Dev"
    if base.lower() in ("etapas", "geral", ""):
        return "Geral"
    return base


def area_da_etapa(area: str) -> str:
    return "Tech-Dev" if area.lower().replace("-", " ") in ("tech dev", "web dev") else area


def _pct(parte: int | float, total: int | float) -> float | None:
    return round(100 * parte / total, 1) if total else None


@dataclass
class Entrega:
    tarefas: int
    validadas: int
    com_prazo: int
    com_responsavel: int
    avaliaveis: int
    no_prazo: int
    atrasadas: int
    atrasadas_abertas: int
    atraso_medio_dias: float | None
    atraso_mediano_dias: float | None

    @property
    def pontualidade(self) -> float | None:
        """% das tarefas avaliáveis que cumpriram o prazo."""
        return _pct(self.no_prazo, self.avaliaveis)

    @property
    def conclusao(self) -> float | None:
        return _pct(self.validadas, self.tarefas)

    @property
    def cobertura_prazo(self) -> float | None:
        return _pct(self.com_prazo, self.tarefas)

    @property
    def cobertura_responsavel(self) -> float | None:
        return _pct(self.com_responsavel, self.tarefas)


def calcular_entrega(tarefas: list[AnaliseTarefa]) -> Entrega:
    atrasadas = [t for t in tarefas if t.situacao.conta_como_atraso]
    dias = [t.dias_atraso for t in atrasadas]
    return Entrega(
        tarefas=len(tarefas),
        validadas=sum(1 for t in tarefas if t.tarefa.fechada_em is not None),
        com_prazo=sum(1 for t in tarefas if t.tarefa.prazo is not None),
        com_responsavel=sum(1 for t in tarefas if t.tarefa.responsaveis),
        avaliaveis=sum(1 for t in tarefas if t.situacao in _AVALIAVEIS),
        no_prazo=sum(1 for t in tarefas if t.situacao in _NO_PRAZO),
        atrasadas=len(atrasadas),
        atrasadas_abertas=sum(1 for t in atrasadas if t.situacao == Situacao.ATRASADA_ABERTA),
        atraso_medio_dias=round(sum(dias) / len(dias), 1) if dias else None,
        atraso_mediano_dias=float(median(dias)) if dias else None,
    )


class Saude:
    """Semáforo do projeto, por regra fixa (sem nota inventada)."""

    VERMELHO = "vermelho"  # atraso de 30+ dias ou prazo do projeto vencido
    AMARELO = "amarelo"  # algum atraso, ou sem nenhum prazo para medir
    VERDE = "verde"


def saude_do_projeto(a: AnaliseProjeto) -> tuple[str, str]:
    if a.maior_atraso_dias >= _ATRASO_GRAVE_DIAS:
        return Saude.VERMELHO, f"atraso de {a.maior_atraso_dias} dias"
    if a.projeto_vencido:
        return Saude.VERMELHO, "prazo do projeto (TAP) vencido"
    if a.atrasadas:
        return Saude.AMARELO, f"{len(a.atrasadas)} tarefa(s) com atraso"
    if not any(t.tarefa.prazo for t in a.tarefas):
        return Saude.AMARELO, "nenhuma tarefa com prazo: atraso não mensurável"
    return Saude.VERDE, "sem atraso"


@dataclass
class IndicadorProjeto:
    analise: AnaliseProjeto
    entrega: Entrega
    saude: str
    motivo_saude: str
    valor_orcado: float | None
    dias_uteis_previstos: int | None
    areas: list[str]

    @property
    def codigo(self) -> str:
        return self.analise.projeto.codigo

    @property
    def slug(self) -> str:
        return self.codigo.replace(" ", "-").lower()

    @property
    def valor_por_dia_util(self) -> float | None:
        if self.valor_orcado and self.dias_uteis_previstos:
            return round(self.valor_orcado / self.dias_uteis_previstos, 2)
        return None


@dataclass
class IndicadorArea:
    area: str
    projetos: int
    entrega: Entrega
    dias_uteis_previstos: int
    valor_orcado: float  # rateado pelos dias úteis previstos de cada etapa


@dataclass
class Comercial:
    projetos: int
    com_precificacao: int
    com_preco: int
    carteira: float  # soma do preço com margem de negociação
    carteira_sem_margem: float
    ticket_medio: float | None
    ticket_mediano: float | None
    valor_por_dia_util: float | None  # média ponderada da carteira
    valor_por_hora_consultor: float | None
    valor_em_atraso: float  # orçamento dos projetos com atraso
    por_dificuldade: list[tuple[str, int]] = field(default_factory=list)
    por_porte: list[tuple[str, int]] = field(default_factory=list)

    @property
    def pct_em_atraso(self) -> float | None:
        return _pct(self.valor_em_atraso, self.carteira)


@dataclass
class Metricas:
    entrega: Entrega
    projetos: list[IndicadorProjeto]
    areas: list[IndicadorArea]
    comercial: Comercial
    causas: list[tuple[str, int]]  # todas as causas com evidência, não só a principal

    @property
    def por_saude(self) -> dict[str, int]:
        c = Counter(p.saude for p in self.projetos)
        return {s: c.get(s, 0) for s in (Saude.VERMELHO, Saude.AMARELO, Saude.VERDE)}


def calcular_metricas(analises: list[AnaliseProjeto], causas_por_projeto: dict[str, list] | None = None) -> Metricas:
    causas_por_projeto = causas_por_projeto or {}
    todas = [t for a in analises for t in a.tarefas]

    projetos: list[IndicadorProjeto] = []
    for a in analises:
        com = a.projeto.comercial
        areas = sorted({area_da_etapa(e.area) for e in com.etapas} if com and com.etapas else set())
        if not areas:
            areas = sorted({area_da_lista(t.tarefa.lista) for t in a.tarefas} - {"Geral"})
        saude, motivo = saude_do_projeto(a)
        projetos.append(IndicadorProjeto(
            analise=a,
            entrega=calcular_entrega(a.tarefas),
            saude=saude,
            motivo_saude=motivo,
            valor_orcado=com.preco_com_margem if com else None,
            dias_uteis_previstos=com.dias_uteis if com else None,
            areas=areas,
        ))

    return Metricas(
        entrega=calcular_entrega(todas),
        projetos=projetos,
        areas=_por_area(analises),
        comercial=_comercial(projetos),
        causas=_causas(causas_por_projeto),
    )


def _por_area(analises: list[AnaliseProjeto]) -> list[IndicadorArea]:
    tarefas: dict[str, list[AnaliseTarefa]] = defaultdict(list)
    projetos: dict[str, set[str]] = defaultdict(set)
    dias: Counter[str] = Counter()
    valor: defaultdict[str, float] = defaultdict(float)
    for a in analises:
        for t in a.tarefas:
            area = area_da_lista(t.tarefa.lista)
            tarefas[area].append(t)
            projetos[area].add(a.projeto.codigo)
        com = a.projeto.comercial
        if com and com.etapas:
            total = sum(e.dias_uteis for e in com.etapas) or 1
            for e in com.etapas:
                area = area_da_etapa(e.area)
                dias[area] += e.dias_uteis
                projetos[area].add(a.projeto.codigo)
                if com.preco_com_margem:
                    valor[area] += com.preco_com_margem * e.dias_uteis / total
    areas = [
        IndicadorArea(area, len(projetos[area]), calcular_entrega(tarefas.get(area, [])), dias[area], round(valor[area], 2))
        for area in projetos
    ]
    return sorted(areas, key=lambda x: (-x.valor_orcado, -x.entrega.tarefas, x.area))


def _comercial(projetos: list[IndicadorProjeto]) -> Comercial:
    com_planilha = [p for p in projetos if p.analise.projeto.comercial]
    com_preco = [p for p in com_planilha if p.valor_orcado]
    valores = [p.valor_orcado for p in com_preco]
    carteira = sum(valores)
    dias = sum(p.dias_uteis_previstos or 0 for p in com_preco)
    horas = sum(p.analise.projeto.comercial.horas_consultores or 0 for p in com_preco)
    dificuldade = Counter(p.analise.projeto.comercial.dificuldade or "não informada" for p in com_planilha)
    porte = Counter(p.analise.projeto.comercial.porte or "não informado" for p in com_planilha)
    return Comercial(
        projetos=len(projetos),
        com_precificacao=len(com_planilha),
        com_preco=len(com_preco),
        carteira=round(carteira, 2),
        carteira_sem_margem=round(sum(p.analise.projeto.comercial.preco_sem_margem or 0 for p in com_preco), 2),
        ticket_medio=round(carteira / len(valores), 2) if valores else None,
        ticket_mediano=round(median(valores), 2) if valores else None,
        valor_por_dia_util=round(carteira / dias, 2) if dias else None,
        valor_por_hora_consultor=round(carteira / horas, 2) if horas else None,
        valor_em_atraso=round(sum(p.valor_orcado for p in com_preco if p.analise.atrasado), 2),
        por_dificuldade=dificuldade.most_common(),
        por_porte=porte.most_common(),
    )


def _causas(causas_por_projeto: dict[str, list]) -> list[tuple[str, int]]:
    c = Counter(causa.categoria.value for causas in causas_por_projeto.values() for causa in causas if causa.evidencias)
    return c.most_common()
