"""Motor de atraso: regras determinísticas, sem IA.

Regra de atraso (definida pela diretoria):
- prazo vencido e status diferente de "validado"; ou
- tarefa fechada ("validado") depois do prazo.

Ajuste combinado: "finalizado" significa que a EJ entregou e aguarda a
validação do cliente. Por isso, uma tarefa "finalizado" entregue dentro do
prazo NÃO conta como atraso da EJ; ela aparece à parte, como "aguardando
cliente". Se foi entregue depois do prazo, conta como atraso.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, time
from enum import Enum

from ejota.domain import Projeto, Status, Tarefa, TipoDocumento

_TESTE = re.compile(r"^\s*(msg\s*\d+|teste)\s*$", re.IGNORECASE)
_DATA = r"(\d{2})/(\d{2})/(\d{4})"
# Modelo simples ("Prazo final do projeto: dd/mm/aaaa") ou o TAP real da EJ, que
# tem uma "Previsão de fim" por frente do projeto.
_FIM_TAP = re.compile(r"(?:prazo final do projeto|previs[ãa]o de fim):\s*" + _DATA, re.IGNORECASE)
_INICIO_TAP = re.compile(r"in[íi]cio:\s*" + _DATA, re.IGNORECASE)

DOCUMENTOS_ESPERADOS = (TipoDocumento.TAP, TipoDocumento.ATA)


def eh_tarefa_de_teste(nome: str) -> bool:
    return bool(_TESTE.match(nome))


class Situacao(str, Enum):
    ATRASADA_ABERTA = "atrasada (aberta)"
    ATRASADA_FECHADA = "fechada com atraso"
    ENTREGUE_COM_ATRASO = "entregue com atraso, aguardando cliente"
    AGUARDANDO_CLIENTE = "entregue no prazo, aguardando validação do cliente"
    CONCLUIDA_NO_PRAZO = "concluída no prazo"
    EM_DIA = "em dia"
    SEM_PRAZO = "sem prazo (lacuna)"
    # "finalizado" sem a data da entrega: o ClickUp só registra a data de
    # fechamento ("validado"), então não dá para saber se foi entregue no prazo.
    FINALIZADO_SEM_DATA = "finalizado, data de entrega não registrada"

    @property
    def conta_como_atraso(self) -> bool:
        return self in (Situacao.ATRASADA_ABERTA, Situacao.ATRASADA_FECHADA, Situacao.ENTREGUE_COM_ATRASO)


@dataclass
class AnaliseTarefa:
    tarefa: Tarefa
    situacao: Situacao
    dias_atraso: int
    tempo_em_status: dict[str, float]  # dias em cada status
    # Fechada com atraso, mas a EJ tinha entregue ("finalizado") dentro do prazo:
    # o atraso ocorreu na validação do cliente.
    atraso_na_validacao: bool = False


@dataclass
class Lacunas:
    tarefas_sem_prazo: int = 0
    tarefas_sem_responsavel: int = 0
    documentos_ilegiveis: list[str] = field(default_factory=list)
    documentos_ausentes: list[str] = field(default_factory=list)
    sem_prazo_do_projeto: bool = False
    entregas_sem_data: int = 0
    # Tarefas fechadas no mesmo instante que outra: sinal de atualização em lote,
    # em que a data do ClickUp não é a data real da validação.
    fechamentos_em_lote: int = 0
    datas_do_tap_incoerentes: bool = False

    @property
    def total(self) -> int:
        return (
            self.tarefas_sem_prazo
            + self.tarefas_sem_responsavel
            + len(self.documentos_ilegiveis)
            + len(self.documentos_ausentes)
            + int(self.sem_prazo_do_projeto)
            + self.entregas_sem_data
            + self.fechamentos_em_lote
            + int(self.datas_do_tap_incoerentes)
        )


@dataclass
class AnaliseProjeto:
    projeto: Projeto
    tarefas: list[AnaliseTarefa]
    tarefas_teste_ignoradas: int
    prazo_projeto: date | None
    lacunas: Lacunas
    hoje: date

    @property
    def atrasadas(self) -> list[AnaliseTarefa]:
        return [t for t in self.tarefas if t.situacao.conta_como_atraso]

    @property
    def aguardando_cliente(self) -> list[AnaliseTarefa]:
        return [t for t in self.tarefas if t.situacao == Situacao.AGUARDANDO_CLIENTE]

    @property
    def concluidas(self) -> int:
        return sum(1 for t in self.tarefas if t.tarefa.status == Status.VALIDADO)

    @property
    def projeto_vencido(self) -> bool:
        return self.prazo_projeto is not None and self.concluidas < len(self.tarefas) and self.hoje > self.prazo_projeto

    @property
    def atrasado(self) -> bool:
        return bool(self.atrasadas) or self.projeto_vencido

    @property
    def maior_atraso_dias(self) -> int:
        return max((t.dias_atraso for t in self.atrasadas), default=0)

    @property
    def soma_dias_atraso(self) -> int:
        return sum(t.dias_atraso for t in self.atrasadas)


def _fim_do_dia(d: date) -> datetime:
    return datetime.combine(d, time.max)


def tempo_em_status(tarefa: Tarefa, agora: datetime) -> dict[str, float]:
    """Dias em cada status, a partir do histórico (começa em "a fazer" na criação).

    Vazio quando a fonte não tem o histórico de status.
    """
    if not tarefa.historico_completo:
        return {}
    marcos = [(Status.A_FAZER, tarefa.criada_em), *((m.status, m.em) for m in tarefa.historico)]
    tempos: dict[str, float] = {s.value: 0.0 for s in Status}
    for i, (status, inicio) in enumerate(marcos):
        if status == Status.VALIDADO:
            break
        fim = marcos[i + 1][1] if i + 1 < len(marcos) else agora
        tempos[status.value] += max((fim - inicio).total_seconds(), 0) / 86400
    return {k: round(v, 1) for k, v in tempos.items()}


def analisar_tarefa(tarefa: Tarefa, hoje: date) -> AnaliseTarefa:
    agora = _fim_do_dia(hoje)
    tempos = tempo_em_status(tarefa, agora)
    prazo = tarefa.prazo

    def resultado(situacao: Situacao, dias: int = 0, na_validacao: bool = False) -> AnaliseTarefa:
        return AnaliseTarefa(tarefa, situacao, max(dias, 0), tempos, na_validacao)

    if prazo is None:
        return resultado(Situacao.SEM_PRAZO)

    if tarefa.status == Status.VALIDADO:
        fechada = (tarefa.fechada_em or agora).date()
        if fechada > prazo:
            entregue_no_prazo = tarefa.finalizada_em is not None and tarefa.finalizada_em.date() <= prazo
            return resultado(Situacao.ATRASADA_FECHADA, (fechada - prazo).days, entregue_no_prazo)
        return resultado(Situacao.CONCLUIDA_NO_PRAZO)

    if tarefa.status == Status.FINALIZADO:
        if tarefa.finalizada_em is None:
            return resultado(Situacao.FINALIZADO_SEM_DATA if hoje > prazo else Situacao.EM_DIA)
        entregue = tarefa.finalizada_em.date()
        if entregue > prazo:
            return resultado(Situacao.ENTREGUE_COM_ATRASO, (entregue - prazo).days)
        if hoje > prazo:
            return resultado(Situacao.AGUARDANDO_CLIENTE)
        return resultado(Situacao.EM_DIA)

    if hoje > prazo:
        return resultado(Situacao.ATRASADA_ABERTA, (hoje - prazo).days)
    return resultado(Situacao.EM_DIA)


def _datas(regex: re.Pattern, texto: str) -> list[date]:
    datas = []
    for dia, mes, ano in regex.findall(texto):
        try:
            datas.append(date(int(ano), int(mes), int(dia)))
        except ValueError:
            continue
    return datas


def prazo_do_projeto(projeto: Projeto) -> tuple[date | None, bool]:
    """Prazo final pelo TAP (a maior "Previsão de fim") e se as datas são incoerentes.

    Incoerente = alguma previsão de fim anterior a alguma data de início.
    """
    for doc in projeto.documentos:
        if doc.tipo == TipoDocumento.TAP and doc.texto:
            fins = _datas(_FIM_TAP, doc.texto)
            if fins:
                inicios = _datas(_INICIO_TAP, doc.texto)
                incoerente = bool(inicios) and min(fins) < max(inicios)
                return max(fins), incoerente
    return None, False


def analisar_projeto(projeto: Projeto, hoje: date) -> AnaliseProjeto:
    reais = [t for t in projeto.tarefas if not eh_tarefa_de_teste(t.nome)]
    analises = [analisar_tarefa(t, hoje) for t in reais]
    prazo, tap_incoerente = prazo_do_projeto(projeto)
    fechamentos = Counter(t.fechada_em.replace(second=0, microsecond=0) for t in reais if t.fechada_em)

    tipos = {d.tipo for d in projeto.documentos if d.texto}
    lacunas = Lacunas(
        tarefas_sem_prazo=sum(1 for t in reais if t.prazo is None),
        tarefas_sem_responsavel=sum(1 for t in reais if not t.responsaveis),
        documentos_ilegiveis=[d.titulo for d in projeto.documentos if not d.texto],
        documentos_ausentes=[t.value for t in DOCUMENTOS_ESPERADOS if t not in tipos]
        + ([] if tipos & {TipoDocumento.CONTRATO, TipoDocumento.PROPOSTA} else ["Contrato ou Proposta Comercial"]),
        sem_prazo_do_projeto=prazo is None,
        entregas_sem_data=sum(1 for a in analises if a.situacao == Situacao.FINALIZADO_SEM_DATA),
        fechamentos_em_lote=sum(n for n in fechamentos.values() if n > 1),
        datas_do_tap_incoerentes=tap_incoerente,
    )
    return AnaliseProjeto(projeto, analises, len(projeto.tarefas) - len(reais), prazo, lacunas, hoje)
