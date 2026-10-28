"""Indicadores da carteira: entrega, projetos e comercial.

Tudo é calculado com regras fixas e explicáveis, a partir do motor de atraso
(ClickUp), do contrato e da Planilha de Precificação (Drive). Nenhum número é estimado:
quando falta dado, o indicador diz em quantos projetos ou tarefas ele se apoia.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from statistics import median

from ejota.domain import Contrato
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


_AREAS_DO_SERVICO = (
    (re.compile(r"marketing|branding|m[íi]dias|pitch|comercial|pesquisa", re.I), "Marketing"),
    (re.compile(r"processos|voluntariado|gest[ãa]o de pessoas", re.I), "Processos"),
    (re.compile(r"financ", re.I), "Finanças"),
    (re.compile(r"\bsite\b|web|agente|\bIA\b|automa", re.I), "Tech-Dev"),
    (re.compile(r"audiovisual|s[ée]rie|v[íi]deo", re.I), "Audiovisual"),
    (re.compile(r"design|identidade visual", re.I), "Design"),
)

# Acima disso a planilha não cobre o que foi contratado (ex.: orçou só uma das frentes).
_LIMITE_CONTRATO_SOBRE_ORCADO = 1.5


def areas_do_servico(servico: str) -> set[str]:
    return {area for padrao, area in _AREAS_DO_SERVICO if padrao.search(servico)}


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
    valor_contratado: float | None  # cláusula 3 do contrato (ou estimativa marcada)
    valor_orcado: float | None  # preço com margem da Planilha de Precificação
    dias_uteis_previstos: int | None  # vigência do contrato; sem contrato, a da planilha
    areas: list[str]

    @property
    def codigo(self) -> str:
        return self.analise.projeto.codigo

    @property
    def slug(self) -> str:
        return self.codigo.replace(" ", "-").lower()

    @property
    def contrato(self) -> Contrato | None:
        com = self.analise.projeto.comercial
        return com.contrato if com else None

    @property
    def valor_por_dia_util(self) -> float | None:
        if self.valor_contratado and self.dias_uteis_previstos:
            return round(self.valor_contratado / self.dias_uteis_previstos, 2)
        return None

    @property
    def orcamento_incompleto(self) -> bool:
        """O contrato vale bem mais que o orçado: a planilha não cobre todo o escopo."""
        return bool(self.valor_contratado and self.valor_orcado
                    and self.valor_contratado > _LIMITE_CONTRATO_SOBRE_ORCADO * self.valor_orcado)

    @property
    def desconto(self) -> float | None:
        """% abaixo do preço orçado com margem (negativo = fechado acima do orçado)."""
        if self.valor_contratado and self.valor_orcado and not self.orcamento_incompleto:
            return round(100 * (1 - self.valor_contratado / self.valor_orcado), 1)
        return None


@dataclass
class IndicadorArea:
    area: str
    projetos: int
    entrega: Entrega
    dias_uteis_previstos: int
    valor: float  # valor contratado rateado entre as áreas do projeto


@dataclass
class Comercial:
    projetos: int
    com_contrato: int
    estimados: int  # sem contrato no Drive; valor deduzido de outra fonte
    carteira: float  # soma dos valores de contrato
    ticket_medio: float | None
    ticket_mediano: float | None
    valor_por_dia_util: float | None  # carteira ÷ dias úteis de vigência
    desconto_medio: float | None  # contratado vs. orçado com margem, nos projetos com os dois
    projetos_com_desconto: int
    valor_em_atraso: float
    assinaturas_pendentes: list[str] = field(default_factory=list)
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


def areas_do_projeto(a: AnaliseProjeto) -> list[str]:
    """Áreas que atuam no projeto: listas do ClickUp + etapas da precificação + objeto do contrato."""
    areas = {area_da_lista(t.tarefa.lista) for t in a.tarefas} - {"Geral"}
    com = a.projeto.comercial
    if com:
        areas |= {area_da_etapa(e.area) for e in com.etapas}
        if com.contrato:  # o objeto do contrato diz quais frentes foram vendidas
            areas |= areas_do_servico(com.contrato.servico)
    return sorted(areas)


def calcular_metricas(analises: list[AnaliseProjeto], causas_por_projeto: dict[str, list] | None = None) -> Metricas:
    causas_por_projeto = causas_por_projeto or {}
    todas = [t for a in analises for t in a.tarefas]

    projetos: list[IndicadorProjeto] = []
    for a in analises:
        com = a.projeto.comercial
        contrato = com.contrato if com else None
        saude, motivo = saude_do_projeto(a)
        projetos.append(IndicadorProjeto(
            analise=a,
            entrega=calcular_entrega(a.tarefas),
            saude=saude,
            motivo_saude=motivo,
            valor_contratado=contrato.valor if contrato else None,
            valor_orcado=com.preco_com_margem if com else None,
            dias_uteis_previstos=(contrato.dias_uteis if contrato and contrato.dias_uteis else None) or (com.dias_uteis if com else None),
            areas=areas_do_projeto(a),
        ))

    return Metricas(
        entrega=calcular_entrega(todas),
        projetos=projetos,
        areas=_por_area(projetos),
        comercial=_comercial(projetos),
        causas=_causas(causas_por_projeto),
    )


def _rateio(p: IndicadorProjeto) -> dict[str, float]:
    """Peso de cada área no projeto: dias úteis das etapas da precificação; sem
    etapas, partes iguais entre as áreas do ClickUp."""
    com = p.analise.projeto.comercial
    if com and com.etapas:
        dias: Counter[str] = Counter()
        for e in com.etapas:
            dias[area_da_etapa(e.area)] += e.dias_uteis
        total = sum(dias.values()) or 1
        pesos = {a: d / total for a, d in dias.items()}
        faltando = [a for a in p.areas if a not in pesos]
        if faltando:  # área com tarefas no ClickUp que a planilha não orçou: recebe uma fatia igual
            fatia = 1 / (len(pesos) + len(faltando))
            pesos = {a: w * (1 - fatia * len(faltando)) for a, w in pesos.items()} | {a: fatia for a in faltando}
        return pesos
    return {a: 1 / len(p.areas) for a in p.areas} if p.areas else {}


def _por_area(projetos: list[IndicadorProjeto]) -> list[IndicadorArea]:
    tarefas: dict[str, list[AnaliseTarefa]] = defaultdict(list)
    codigos: dict[str, set[str]] = defaultdict(set)
    dias: Counter[str] = Counter()
    valor: defaultdict[str, float] = defaultdict(float)
    for p in projetos:
        a = p.analise
        for t in a.tarefas:
            area = area_da_lista(t.tarefa.lista)
            tarefas[area].append(t)
            codigos[area].add(p.codigo)
        com = a.projeto.comercial
        for e in com.etapas if com else []:
            dias[area_da_etapa(e.area)] += e.dias_uteis
        for area, peso in _rateio(p).items():
            codigos[area].add(p.codigo)
            valor[area] += (p.valor_contratado or 0) * peso
    areas = [
        IndicadorArea(area, len(codigos[area]), calcular_entrega(tarefas.get(area, [])), dias[area], round(valor[area], 2))
        for area in codigos
    ]
    return sorted(areas, key=lambda x: (-x.valor, -x.entrega.tarefas, x.area))


_ASSINATURAS = re.compile(r"(\d+)\s*de\s*(\d+)")


def _comercial(projetos: list[IndicadorProjeto]) -> Comercial:
    com_valor = [p for p in projetos if p.valor_contratado]
    valores = [p.valor_contratado for p in com_valor]
    carteira = sum(valores)
    dias = sum(p.dias_uteis_previstos or 0 for p in com_valor if p.dias_uteis_previstos)
    ambos = [p for p in com_valor if p.desconto is not None]
    orcado = sum(p.valor_orcado for p in ambos)
    pendentes = []
    for p in com_valor:
        m = _ASSINATURAS.search(p.contrato.assinaturas)
        if m and int(m.group(1)) < int(m.group(2)):
            pendentes.append(f"{p.codigo.replace('EJ ', '')} ({m.group(0)})")
    porte = Counter(p.analise.projeto.comercial.porte for p in projetos if p.analise.projeto.comercial and p.analise.projeto.comercial.porte)
    return Comercial(
        projetos=len(projetos),
        com_contrato=sum(1 for p in com_valor if not p.contrato.estimado),
        estimados=sum(1 for p in com_valor if p.contrato.estimado),
        carteira=round(carteira, 2),
        ticket_medio=round(carteira / len(valores), 2) if valores else None,
        ticket_mediano=round(median(valores), 2) if valores else None,
        valor_por_dia_util=round(carteira / dias, 2) if dias else None,
        desconto_medio=round(100 * (1 - sum(p.valor_contratado for p in ambos) / orcado), 1) if orcado else None,
        projetos_com_desconto=len(ambos),
        valor_em_atraso=round(sum(p.valor_contratado for p in com_valor if p.analise.atrasado), 2),
        assinaturas_pendentes=pendentes,
        por_porte=porte.most_common(),
    )


def _causas(causas_por_projeto: dict[str, list]) -> list[tuple[str, int]]:
    c = Counter(causa.categoria.value for causas in causas_por_projeto.values() for causa in causas if causa.evidencias)
    return c.most_common()
