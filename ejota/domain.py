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

    @classmethod
    def de_texto(cls, texto: str) -> Status:
        """Aceita também os nomes padrão do ClickUp que aparecem em listas antigas."""
        t = texto.strip().lower()
        return cls(_ALIASES_STATUS.get(t, t))


_ALIASES_STATUS = {"to do": "a fazer", "open": "a fazer", "in progress": "em andamento"}


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
    # False quando a fonte não guarda as mudanças de status (ClickUp sem o
    # ClickApp "Tempo em Status"): aí o tempo em cada status não é calculado.
    historico_completo: bool = True


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
class EtapaPrevista:
    nome: str
    area: str
    dias_uteis: int


@dataclass
class Contrato:
    """Cláusula 3 (valor e pagamento) e 2.1 (vigência) do Documento Contratual."""

    valor: float
    servico: str = ""  # objeto do contrato, ex.: "Plano de Marketing"
    parcelas: int | None = None
    dias_uteis: int | None = None
    assinaturas: str = ""  # como o rodapé de auditoria do PDF registra, ex.: "3 de 6"
    estimado: bool = False  # True = sem contrato no Drive; valor deduzido de outra fonte (ex.: nota fiscal)
    fonte: str = ""
    observacao: str = ""
    url: str = ""


@dataclass
class Comercial:
    """O lado comercial do projeto: o contrato (valor fechado) e a Planilha de
    Precificação (o que foi orçado: preço, dias úteis e etapas por área).

    O valor que conta como receita é o do contrato. O orçado serve para medir
    o desconto concedido e para ratear o valor entre as áreas.
    """

    preco_sem_margem: float | None = None  # None = sem planilha, ou planilha com erro (ex.: #REF!)
    preco_com_margem: float | None = None
    dias_uteis: int | None = None
    contrato: Contrato | None = None
    horas_consultores: float | None = None
    horas_gerente: float | None = None
    dificuldade: str | None = None
    porte: str | None = None
    etapas: list[EtapaPrevista] = field(default_factory=list)
    url: str = ""


@dataclass
class Projeto:
    codigo: str  # "EJ 26-901"
    cliente: str
    tarefas: list[Tarefa]
    documentos: list[Documento]
    url: str = ""
    comercial: Comercial | None = None  # None = sem planilha de precificação encontrada

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
