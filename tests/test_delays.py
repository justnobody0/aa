from __future__ import annotations

from datetime import date, datetime

from ejota.connectors.fake import FonteFicticia
from ejota.domain import MudancaStatus, Status, Tarefa
from ejota.engine.delays import Situacao, analisar_projeto, analisar_tarefa, eh_tarefa_de_teste, tempo_em_status
from tests.conftest import HOJE


def tarefa(status: Status, prazo: date | None, historico: list[tuple[Status, str]] = (), responsaveis=("X",)) -> Tarefa:
    hist = [MudancaStatus(s, datetime.fromisoformat(d)) for s, d in historico]
    ultima = lambda alvo: next((m.em for m in reversed(hist) if m.status == alvo), None)  # noqa: E731
    return Tarefa(
        id="t", nome="Tarefa", lista="Etapa", status=status, prazo=prazo, responsaveis=list(responsaveis),
        criada_em=datetime(2026, 9, 1, 9), fechada_em=ultima(Status.VALIDADO) if status == Status.VALIDADO else None,
        finalizada_em=ultima(Status.FINALIZADO), historico=hist,
    )


def test_tarefas_de_teste_sao_reconhecidas():
    for nome in ["Msg 1", "msg 28", "Msg28", "TESTE", " teste "]:
        assert eh_tarefa_de_teste(nome)
    for nome in ["Teste de usabilidade", "Mensagem ao cliente", "Msg final"]:
        assert not eh_tarefa_de_teste(nome)


def test_aberta_com_prazo_vencido_esta_atrasada():
    a = analisar_tarefa(tarefa(Status.EM_ANDAMENTO, date(2026, 10, 10), [(Status.EM_ANDAMENTO, "2026-09-02T09:00")]), HOJE)
    assert a.situacao == Situacao.ATRASADA_ABERTA
    assert a.dias_atraso == 10


def test_prazo_no_dia_de_hoje_nao_esta_atrasado():
    assert analisar_tarefa(tarefa(Status.A_FAZER, HOJE), HOJE).situacao == Situacao.EM_DIA


def test_validada_depois_do_prazo_conta_como_atraso():
    hist = [(Status.FINALIZADO, "2026-10-05T10:00"), (Status.VALIDADO, "2026-10-08T10:00")]
    a = analisar_tarefa(tarefa(Status.VALIDADO, date(2026, 10, 3), hist), HOJE)
    assert a.situacao == Situacao.ATRASADA_FECHADA
    assert a.dias_atraso == 5
    assert not a.atraso_na_validacao


def test_validacao_tardia_do_cliente_e_sinalizada():
    hist = [(Status.FINALIZADO, "2026-10-01T10:00"), (Status.VALIDADO, "2026-10-08T10:00")]
    a = analisar_tarefa(tarefa(Status.VALIDADO, date(2026, 10, 3), hist), HOJE)
    assert a.situacao == Situacao.ATRASADA_FECHADA
    assert a.atraso_na_validacao


def test_finalizado_no_prazo_e_aguardando_cliente_nao_atraso():
    a = analisar_tarefa(tarefa(Status.FINALIZADO, date(2026, 10, 5), [(Status.FINALIZADO, "2026-10-01T10:00")]), HOJE)
    assert a.situacao == Situacao.AGUARDANDO_CLIENTE
    assert not a.situacao.conta_como_atraso


def test_finalizado_depois_do_prazo_e_atraso():
    a = analisar_tarefa(tarefa(Status.FINALIZADO, date(2026, 10, 5), [(Status.FINALIZADO, "2026-10-09T10:00")]), HOJE)
    assert a.situacao == Situacao.ENTREGUE_COM_ATRASO
    assert a.dias_atraso == 4


def test_sem_prazo_e_lacuna_nao_erro():
    a = analisar_tarefa(tarefa(Status.EM_ANDAMENTO, None), HOJE)
    assert a.situacao == Situacao.SEM_PRAZO
    assert not a.situacao.conta_como_atraso


def test_tempo_em_status_soma_intervalos():
    hist = [(Status.EM_ANDAMENTO, "2026-09-03T09:00"), (Status.A_FAZER, "2026-09-05T09:00"),
            (Status.EM_ANDAMENTO, "2026-09-06T09:00"), (Status.VALIDADO, "2026-09-10T09:00")]
    t = tempo_em_status(tarefa(Status.VALIDADO, None, hist), datetime(2026, 10, 20))
    assert t["a fazer"] == 3.0  # 01→03 e 05→06
    assert t["em andamento"] == 6.0  # 03→05 e 06→10
    assert t["validado"] == 0.0


def test_projetos_ficticios():
    projetos = {p.codigo: analisar_projeto(p, HOJE) for p in FonteFicticia().listar_projetos()}
    p901 = projetos["EJ 26-901"]
    assert p901.tarefas_teste_ignoradas == 3
    assert p901.prazo_projeto == date(2026, 9, 30)
    assert p901.atrasado and p901.projeto_vencido
    assert not projetos["EJ 26-905"].atrasado
    assert len(projetos["EJ 26-902"].aguardando_cliente) == 1
    l906 = projetos["EJ 26-906"].lacunas
    assert l906.documentos_ilegiveis and l906.sem_prazo_do_projeto
    assert "ATA de Projeto" in l906.documentos_ausentes
