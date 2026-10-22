"""Modelo de dados comum a todas as fontes (fictícia, ClickUp, Drive).

Preparado para fases futuras (grafo, formulário de necessidade, repertório de
consultores): `Consultor` e `Necessidade` existem, mas ainda não são usados.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum


class Status(str, Enum):
    A_FAZER = "a fazer"
    EM_ANDAMENTO = "em andamento"
    FINALIZADO = "finalizado"  # entregue pela EJ, aguardando validação do cliente
    VALIDADO = "validado"  # único status que fecha de fato a tarefa


class Categoria(str, Enum):
    ESCOPO = "escopo"
    CLIENTE = "cliente"
    EQUIPE = "equipe"
    PRAZO = "prazo mal estimado"
    CONTRATO = "contrato"
    OUTRA = "outra"


class Confianca(str, Enum):
    ALTA = "alta"
    MEDIA = "média"
    BAIXA = "baixa"
    SEM_EVIDENCIA = "sem evidência"


class TipoDocumento(str, Enum):
    ATA = "ATA de Projeto"
    TAP = "Termo de Abertura do Projeto"
    CONTRATO = "Contrato"
    PROPOSTA = "Proposta Comercial"
    DIAGNOSTICO = "Diagnóstico"
    PRECIFICACAO = "Precificação de Projeto"
    RELATORIO_MENSAL = "Relatório de Projetos"
    ENTREGAVEL = "Entregável"
    OUTRO = "Outro"


@dataclass
class MudancaStatus:
    status: Status
    em: datetime


@dataclass
class Tarefa:
    id: str
    nome: str
    lista: str  # etapa do projeto (lista do ClickUp)
    status: Status
    prazo: date | None
    responsaveis: list[str]
    criada_em: datetime
    fechada_em: datetime | None = None  # quando chegou em "validado"
    finalizada_em: datetime | None = None  # quando chegou em "finalizado"
    historico: list[MudancaStatus] = field(default_factory=list)
    url: str = ""


@dataclass
class Documento:
    id: str
    tipo: TipoDocumento
    titulo: str
    url: str
    texto: str | None  # None = não foi possível ler (ex.: PDF escaneado)
    modificado_em: datetime | None = None


@dataclass
class Trecho:
    """Pedaço citável de um documento. O `id` é estável e vai para o relatório."""

    id: str
    documento_id: str
    tipo: TipoDocumento
    titulo_documento: str
    secao: str
    texto: str
    url: str


@dataclass
class Projeto:
    codigo: str  # "EJ 26-901"
    cliente: str
    tarefas: list[Tarefa]
    documentos: list[Documento]
    url: str = ""

    @property
    def nome(self) -> str:
        return f"{self.codigo} | {self.cliente}"


@dataclass
class Evidencia:
    trecho_id: str
    citacao: str
    documento: str
    secao: str
    url: str


@dataclass
class Causa:
    categoria: Categoria
    explicacao: str
    evidencias: list[Evidencia]
    tarefas_relacionadas: list[str]
    confianca: Confianca
    principal: bool = False


# --- Fases futuras (não usadas no MVP) -------------------------------------


@dataclass
class Consultor:
    id: str
    nome: str
    competencias: list[str] = field(default_factory=list)
    projetos: list[str] = field(default_factory=list)


@dataclass
class Necessidade:
    id: str
    descricao: str
    projeto_codigo: str | None = None
