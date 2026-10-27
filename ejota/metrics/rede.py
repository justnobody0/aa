"""A rede da Ejota: as áreas da EJ são os nós centrais, numa linha horizontal
(Marketing no centro), e cada projeto é um nó menor ligado a todas as áreas
em que atua. A ligação com a área onde está a maior parte do trabalho é a
principal.

Ao clicar num projeto aparece tudo o que o sistema sabe dele: saúde, números,
causas de atraso com a citação da ATA ou do contrato, documentos e lacunas.
É um grafo calculado a partir dos dados, não um modelo treinado.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

from ejota.domain import Causa, Documento
from ejota.engine.delays import AnaliseProjeto
from ejota.metrics.indicadores import IndicadorArea, IndicadorProjeto, Metricas, area_da_lista

AREA_CENTRAL = "Marketing"
SEM_AREA = "Geral"
_ORDEM_SAUDE = {"vermelho": 0, "amarelo": 1, "verde": 2}
_MAX_CITACAO = 220


@dataclass
class CausaNaBolha:
    categoria: str
    confianca: str
    principal: bool
    resumo: str  # primeira frase da explicação
    citacao: str  # primeira evidência, encurtada
    fonte: str  # "ATA de Projeto · LA1"
    url: str


@dataclass
class Bolha:
    indicador: IndicadorProjeto
    area: str  # área principal: onde está a maior parte das tarefas (ou dos dias orçados)
    outras_areas: list[str]
    causas: list[CausaNaBolha]
    documentos: list[Documento]
    lacunas: list[str]

    @property
    def analise(self) -> AnaliseProjeto:
        return self.indicador.analise

    @property
    def id(self) -> str:
        return self.indicador.slug


@dataclass
class Hub:
    area: str
    indicador: IndicadorArea | None
    acima: list[Bolha] = field(default_factory=list)  # a primeira é a mais próxima da área
    abaixo: list[Bolha] = field(default_factory=list)
    secundarios: int = 0  # projetos em que a área atua sem ser a principal

    @property
    def id(self) -> str:
        return "area-" + re.sub(r"[^a-z0-9]+", "-", self.area.lower()).strip("-")

    @property
    def bolhas(self) -> list[Bolha]:
        return self.acima + self.abaixo

    @property
    def largura(self) -> int:
        """Colunas de bolhas: áreas com muitos projetos ganham duas, para o mapa não ficar alto demais."""
        return 2 if len(self.bolhas) > 4 else 1


@dataclass
class Rede:
    hubs: list[Hub]  # da esquerda para a direita

    @property
    def bolhas(self) -> list[Bolha]:
        return [b for h in self.hubs for b in h.bolhas]

    def para_json(self) -> dict:
        """Dados do grafo para o navegador (o detalhe de cada projeto vai no HTML)."""
        ids = {h.area: h.id for h in self.hubs}
        return {
            "areas": [{"id": h.id, "rotulo": "Sem área" if h.area == SEM_AREA else h.area,
                       "central": h.area == AREA_CENTRAL, "projetos": len(h.bolhas) + h.secundarios} for h in self.hubs],
            "projetos": [{"id": b.id, "rotulo": b.indicador.codigo.replace("EJ ", ""), "saude": b.indicador.saude,
                          "valor": b.indicador.valor_orcado or 0,
                          "areas": [ids[b.area]] + [ids[a] for a in b.outras_areas if a in ids]} for b in self.bolhas],
        }

    def ligacoes(self) -> list[tuple[str, str, bool]]:
        """(bolha, área, principal?) para desenhar as linhas."""
        ids = {h.area: h.id for h in self.hubs}
        out = []
        for b in self.bolhas:
            out.append((b.id, ids[b.area], True))
            out += [(b.id, ids[a], False) for a in b.outras_areas if a in ids]
        return out


def _primeira_frase(texto: str) -> str:
    m = re.match(r"(.+?[.!?])(\s|$)", texto.strip())
    return m.group(1) if m else texto.strip()


def _encurtar(texto: str, limite: int = _MAX_CITACAO) -> str:
    if len(texto) <= limite:
        return texto
    return texto[:limite].rsplit(" ", 1)[0].rstrip(",;:") + "…"


def _causas(causas: list[Causa]) -> list[CausaNaBolha]:
    ordenadas = sorted(causas, key=lambda c: not c.principal)
    out = []
    for c in ordenadas:
        ev = c.evidencias[0] if c.evidencias else None
        out.append(CausaNaBolha(
            categoria=c.categoria.value,
            confianca=c.confianca.value,
            principal=c.principal,
            resumo=_primeira_frase(c.explicacao),
            citacao=_encurtar(ev.citacao) if ev else "",
            fonte=f"{ev.documento} · {ev.secao}" if ev else "sem evidência",
            url=ev.url if ev else "",
        ))
    return out


def _lacunas(p: IndicadorProjeto) -> list[str]:
    a, lac = p.analise, p.analise.lacunas
    com = a.projeto.comercial
    out = []
    if not any(t.tarefa.prazo for t in a.tarefas):
        out.append("nenhuma tarefa com prazo")
    elif lac.tarefas_sem_prazo:
        out.append(f"{lac.tarefas_sem_prazo} tarefa(s) sem prazo")
    if lac.tarefas_sem_responsavel:
        out.append(f"{lac.tarefas_sem_responsavel} sem responsável")
    if not com:
        out.append("sem precificação")
    elif com.preco_com_margem is None:
        out.append("precificação com erro")
    if lac.documentos_ausentes:
        nomes = {"Termo de Abertura do Projeto": "TAP", "ATA de Projeto": "ATA", "Contrato ou Proposta Comercial": "contrato"}
        out.append("faltam: " + ", ".join(nomes.get(d, d) for d in lac.documentos_ausentes))
    if lac.fechamentos_em_lote:
        out.append(f"{lac.fechamentos_em_lote} fechadas em lote")
    if lac.datas_do_tap_incoerentes:
        out.append("datas do TAP incoerentes")
    if lac.codigo_divergente:
        out.append(f"{len(lac.codigo_divergente)} tarefa(s) com código de outro projeto")
    return out


def _area_principal(p: IndicadorProjeto) -> str:
    tarefas = Counter(area_da_lista(t.tarefa.lista) for t in p.analise.tarefas)
    tarefas.pop(SEM_AREA, None)
    if tarefas:
        return tarefas.most_common(1)[0][0]
    com = p.analise.projeto.comercial
    if com and com.etapas:
        dias: Counter[str] = Counter()
        for e in com.etapas:
            dias[e.area if e.area.lower().replace("-", " ") not in ("tech dev", "web dev") else "Tech-Dev"] += e.dias_uteis
        return dias.most_common(1)[0][0]
    return p.areas[0] if p.areas else SEM_AREA


def _ordem_centro(areas: list[str]) -> list[str]:
    """A primeira área fica no centro; as demais se alternam à direita e à esquerda."""
    esquerda: list[str] = []
    direita: list[str] = []
    for i, a in enumerate(areas[1:]):
        (direita if i % 2 == 0 else esquerda).append(a)
    return esquerda[::-1] + areas[:1] + direita


def montar_rede(m: Metricas, causas_por_projeto: dict[str, list[Causa]] | None = None) -> Rede:
    causas_por_projeto = causas_por_projeto or {}
    bolhas: list[Bolha] = []
    for p in m.projetos:
        area = _area_principal(p)
        bolhas.append(Bolha(
            indicador=p,
            area=area,
            outras_areas=[a for a in p.areas if a != area],
            causas=_causas(causas_por_projeto.get(p.codigo, [])),
            documentos=[d for d in p.analise.projeto.documentos if d.texto and d.url.startswith("http")],
            lacunas=_lacunas(p),
        ))

    por_area = Counter(b.area for b in bolhas)
    indicadores = {a.area: a for a in m.areas}
    nomes = sorted(set(por_area) | {a for b in bolhas for a in b.outras_areas} | ({AREA_CENTRAL} & set(indicadores)),
                   key=lambda a: (a != AREA_CENTRAL, a == SEM_AREA, -por_area[a], a))
    sem_area = [a for a in nomes if a == SEM_AREA]
    ordem = _ordem_centro([a for a in nomes if a != SEM_AREA]) + sem_area

    hubs = {a: Hub(a, indicadores.get(a)) for a in ordem}
    for area in ordem:
        doa = sorted((b for b in bolhas if b.area == area),
                     key=lambda b: (_ORDEM_SAUDE[b.indicador.saude], -b.analise.maior_atraso_dias, b.indicador.codigo))
        for i, b in enumerate(doa):
            (hubs[area].acima if i % 2 == 0 else hubs[area].abaixo).append(b)
    for b in bolhas:
        for a in b.outras_areas:
            hubs[a].secundarios += 1
    return Rede([hubs[a] for a in ordem])
