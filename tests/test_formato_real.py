"""Formato dos dados reais (ClickUp + Drive), com textos inventados."""

from __future__ import annotations

from datetime import date, datetime

from ejota.documents.chunker import trechos_do_documento
from ejota.domain import Documento, Projeto, Status, Tarefa, TipoDocumento
from ejota.engine.delays import Situacao, analisar_projeto, analisar_tarefa, prazo_do_projeto
from tests.conftest import HOJE

PDF = """CLÁUSULA 1 – DAS OBRIGAÇÕES

I. Disponibilizar, no prazo de até 2 (dois) dias úteis, todas as

informações necessárias, conforme solicitado pela CONTRATADA. Este prazo poderá ser

estendido em, no máximo, 10 dias úteis.

CLÁUSULA 2 – DO PRAZO

2.1. O contrato terá vigência de 100 dias úteis.
"""

ATA = """# **Lições Aprendidas (LAs)**

**LA1 – Dados: Cliente não enviou os números ( faturamento, custos, etc), o que atrasou a etapa.**

| \\*\\*Consultor Design:\\*\\* | \\*\\*\\\\\\[Nome do consultor marcado com @\\\\\\]\\*\\* |
"""


def _tarefa(status: Status, prazo: date | None, fechada: datetime | None = None, id_: str = "t") -> Tarefa:
    return Tarefa(id=id_, nome="Etapa", lista="L", status=status, prazo=prazo, responsaveis=[],
                  criada_em=datetime(2026, 9, 1), fechada_em=fechada, historico_completo=False)


def test_pdf_com_linhas_quebradas_vira_uma_frase_por_trecho():
    trechos = trechos_do_documento(Documento("c", TipoDocumento.CONTRATO, "Contrato", "#", PDF))
    textos = [t.texto for t in trechos]
    assert textos[0] == (
        "I. Disponibilizar, no prazo de até 2 (dois) dias úteis, todas as informações necessárias, "
        "conforme solicitado pela CONTRATADA. Este prazo poderá ser estendido em, no máximo, 10 dias úteis."
    )
    assert trechos[0].secao == "CLÁUSULA 1 – DAS OBRIGAÇÕES"
    assert trechos[-1].secao == "CLÁUSULA 2 – DO PRAZO"


def test_markdown_do_drive_e_limpo_e_la_rotulada():
    trechos = trechos_do_documento(Documento("a", TipoDocumento.ATA, "ATA", "#", ATA))
    assert trechos[0].secao.endswith("› LA1")
    assert "**" not in trechos[0].texto and "( faturamento, custos, etc)" in trechos[0].texto
    assert trechos[1].texto == "Consultor Design: | [Nome do consultor marcado com @]"


def test_status_padrao_do_clickup():
    assert Status.de_texto("to do") == Status.A_FAZER
    assert Status.de_texto("Validado") == Status.VALIDADO


def test_finalizado_sem_data_de_entrega_e_lacuna_e_nao_atraso():
    a = analisar_tarefa(_tarefa(Status.FINALIZADO, date(2026, 10, 1)), HOJE)
    assert a.situacao == Situacao.FINALIZADO_SEM_DATA
    assert not a.situacao.conta_como_atraso
    assert a.tempo_em_status == {}


def test_fechamento_em_lote_e_datas_incoerentes_do_tap():
    lote = datetime(2026, 9, 23, 20, 4, 10)
    tarefas = [
        _tarefa(Status.VALIDADO, date(2026, 9, 1), lote, "a"),
        _tarefa(Status.VALIDADO, date(2026, 9, 2), lote.replace(second=40), "b"),
        _tarefa(Status.VALIDADO, None, datetime(2026, 10, 1, 9), "c"),
    ]
    tap = Documento("tap", TipoDocumento.TAP, "TAP", "#",
                    "Observações: - Início: 16/06/2026- Previsão de fim: 04/01/2027\n"
                    "Observações: - Início: 16/06/2026- Previsão de fim: 26/01/2026")
    projeto = Projeto("EJ 26-999", "X", tarefas, [tap])
    assert prazo_do_projeto(projeto) == (date(2027, 1, 4), True)
    lacunas = analisar_projeto(projeto, HOJE).lacunas
    assert lacunas.fechamentos_em_lote == 2
    assert lacunas.datas_do_tap_incoerentes


def test_tarefa_com_codigo_de_outro_projeto():
    from ejota.engine.delays import codigo_divergente

    assert codigo_divergente("26-183 | 2. Mapeamento de Processos", "EJ 26-163")
    assert not codigo_divergente("26-163 | 1. Imersão", "EJ 26-163")
    assert not codigo_divergente("EJ 26- 169 | Imersão Design", "EJ 26-169")
    assert not codigo_divergente("Mapa Jornada do Aluno", "EJ 26-163")
