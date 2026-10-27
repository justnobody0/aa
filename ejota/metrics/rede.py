"""A rede da Ejota: um grafo que liga projetos às áreas, causas, perfis de
cliente e lacunas de dados. Cada nó carrega suas próprias métricas.

É um grafo de conhecimento calculado a partir dos dados, não um modelo
treinado: as ligações vêm do ClickUp, da precificação e das causas com
evidência, e por isso podem ser conferidas uma a uma.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from ejota.metrics.indicadores import IndicadorProjeto, Metricas, area_da_lista


@dataclass
class No:
    id: str
    tipo: str  # projeto | area | causa | perfil | lacuna
    rotulo: str
    peso: float = 1.0  # tamanho na tela
    grupo: str = ""  # cor: saúde do projeto, ou o próprio tipo
    metricas: dict[str, str] = field(default_factory=dict)
    link: str = ""


@dataclass
class Aresta:
    origem: str
    destino: str
    rotulo: str
    peso: float = 1.0


@dataclass
class Rede:
    nos: list[No]
    arestas: list[Aresta]

    def para_json(self) -> dict:
        return {
            # métricas como lista de pares: o `tojson` do Jinja ordena chaves de dicionário.
            "nos": [{**vars(n), "metricas": list(n.metricas.items())} for n in self.nos],
            "arestas": [vars(a) for a in self.arestas],
        }


def _moeda(v: float | None) -> str:
    if v is None:
        return "—"
    return "R$ " + f"{v:,.0f}".replace(",", ".")


def _pct(v: float | None) -> str:
    return "—" if v is None else f"{v:.0f}%"


def montar_rede(m: Metricas, causas_por_projeto: dict[str, list] | None = None) -> Rede:
    causas_por_projeto = causas_por_projeto or {}
    nos: dict[str, No] = {}
    arestas: list[Aresta] = []
    ligados: dict[str, set[str]] = defaultdict(set)  # nó → projetos ligados

    def ligar(proj: IndicadorProjeto, alvo: No, rotulo: str, peso: float = 1.0) -> None:
        nos.setdefault(alvo.id, alvo)
        arestas.append(Aresta(proj.codigo, alvo.id, rotulo, peso))
        ligados[alvo.id].add(proj.codigo)

    por_codigo = {p.codigo: p for p in m.projetos}
    for p in m.projetos:
        a = p.analise
        nos[p.codigo] = No(
            id=p.codigo,
            tipo="projeto",
            rotulo=a.projeto.codigo.replace("EJ ", ""),
            peso=max(p.valor_orcado or 0, 1500) / 1500,
            grupo=p.saude,
            link=f"/projeto/{p.slug}",
            metricas={
                "Cliente": a.projeto.cliente,
                "Saúde": f"{p.saude} ({p.motivo_saude})",
                "Tarefas": str(p.entrega.tarefas),
                "Concluídas": _pct(p.entrega.conclusao),
                "Pontualidade": _pct(p.entrega.pontualidade),
                "Com atraso": str(p.entrega.atrasadas),
                "Maior atraso": f"{a.maior_atraso_dias} dias",
                "Valor orçado": _moeda(p.valor_orcado),
                "Dias úteis previstos": str(p.dias_uteis_previstos or "—"),
            },
        )

        tarefas_por_area: dict[str, int] = defaultdict(int)
        for t in a.tarefas:
            tarefas_por_area[area_da_lista(t.tarefa.lista)] += 1
        for area in p.areas:
            ligar(p, No(f"area:{area}", "area", area, grupo="area"), "área", 1 + tarefas_por_area.get(area, 0) / 5)

        for causa in causas_por_projeto.get(p.codigo, []):
            if not causa.evidencias:
                continue
            cat = causa.categoria.value
            ligar(p, No(f"causa:{cat}", "causa", f"causa: {cat}", grupo="causa"),
                  "causa principal" if causa.principal else "causa", 2 if causa.principal else 1)

        com = a.projeto.comercial
        if com and com.porte:
            ligar(p, No(f"perfil:{com.porte}", "perfil", com.porte, grupo="perfil"), "porte do cliente")

        lac = a.lacunas
        if not any(t.tarefa.prazo for t in a.tarefas):
            ligar(p, No("lacuna:sem-prazo", "lacuna", "sem prazo no ClickUp", grupo="lacuna"), "lacuna")
        if not com:
            ligar(p, No("lacuna:sem-precificacao", "lacuna", "sem precificação", grupo="lacuna"), "lacuna")
        elif com.preco_com_margem is None:
            ligar(p, No("lacuna:preco-com-erro", "lacuna", "precificação com erro", grupo="lacuna"), "lacuna")
        if lac.fechamentos_em_lote:
            ligar(p, No("lacuna:lote", "lacuna", "fechamento em lote", grupo="lacuna"), "lacuna")
        if lac.codigo_divergente:
            ligar(p, No("lacuna:codigo", "lacuna", "código de outro projeto", grupo="lacuna"), "lacuna")

    areas = {x.area: x for x in m.areas}
    for no_id, codigos in ligados.items():
        no = nos[no_id]
        projs = [por_codigo[c] for c in codigos]
        atrasados = sum(1 for p in projs if p.analise.atrasado)
        valor = sum(p.valor_orcado or 0 for p in projs)
        no.peso = 1 + len(projs) / 2
        no.metricas = {
            "Projetos ligados": str(len(projs)),
            "Com atraso": f"{atrasados} ({_pct(100 * atrasados / len(projs))})",
            "Valor orçado ligado": _moeda(valor),
            "Projetos": ", ".join(sorted(c.replace("EJ ", "") for c in codigos)),
        }
        if no.tipo == "area" and no.rotulo in areas:
            ia = areas[no.rotulo]
            no.metricas["Tarefas"] = str(ia.entrega.tarefas)
            no.metricas["Pontualidade"] = _pct(ia.entrega.pontualidade)
            no.metricas["Dias úteis orçados"] = str(ia.dias_uteis_previstos)

    return Rede(list(nos.values()), arestas)
