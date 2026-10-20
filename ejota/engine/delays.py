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
from dataclasses import dataclass, field
from datetime import date, datetime, time
from enum import Enum

from ejota.domain import Projeto, Status, Tarefa, TipoDocumento

_TESTE = re.compile(r"^\s*(msg\s*\d+|teste)\s*$", re.IGNORECASE)
_PRAZO_TAP = re.compile(r"prazo final do projeto:\s*(\d{2})/(\d{2})/(\d{4})", re.IGNORECASE)

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

    @property
    def total(self) -> int:
        return (
            self.tarefas_sem_prazo
            + self.tarefas_sem_responsavel
            + len(self.documentos_ilegiveis)
            + len(self.documentos_ausentes)
            + int(self.sem_prazo_do_projeto)
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
    """Dias em cada status, a partir do histórico (começa em "a fazer" na criação)."""
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
        entregue = (tarefa.finalizada_em or agora).date()
        if entregue > prazo:
            return resultado(Situacao.ENTREGUE_COM_ATRASO, (entregue - prazo).days)
        if hoje > prazo:
            return resultado(Situacao.AGUARDANDO_CLIENTE)
        return resultado(Situacao.EM_DIA)

    if hoje > prazo:
        return resultado(Situacao.ATRASADA_ABERTA, (hoje - prazo).days)
    return resultado(Situacao.EM_DIA)


def prazo_do_projeto(projeto: Projeto) -> date | None:
    for doc in projeto.documentos:
        if doc.tipo == TipoDocumento.TAP and doc.texto:
            m = _PRAZO_TAP.search(doc.texto)
            if m:
                dia, mes, ano = map(int, m.groups())
                return date(ano, mes, dia)
    return None


def analisar_projeto(projeto: Projeto, hoje: date) -> AnaliseProjeto:
    reais = [t for t in projeto.tarefas if not eh_tarefa_de_teste(t.nome)]
    analises = [analisar_tarefa(t, hoje) for t in reais]
    prazo = prazo_do_projeto(projeto)

    tipos = {d.tipo for d in projeto.documentos if d.texto}
    lacunas = Lacunas(
        tarefas_sem_prazo=sum(1 for t in reais if t.prazo is None),
        tarefas_sem_responsavel=sum(1 for t in reais if not t.responsaveis),
        documentos_ilegiveis=[d.titulo for d in projeto.documentos if not d.texto],
        documentos_ausentes=[t.value for t in DOCUMENTOS_ESPERADOS if t not in tipos]
        + ([] if tipos & {TipoDocumento.CONTRATO, TipoDocumento.PROPOSTA} else ["Contrato ou Proposta Comercial"]),
        sem_prazo_do_projeto=prazo is None,
    )
    return AnaliseProjeto(projeto, analises, len(projeto.tarefas) - len(reais), prazo, lacunas, hoje)
