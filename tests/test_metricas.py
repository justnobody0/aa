"""Indicadores e rede: contas com números conferíveis à mão."""

from __future__ import annotations

from datetime import date, datetime

from ejota.domain import Comercial, Contrato, EtapaPrevista, Projeto, Status, Tarefa
from ejota.engine.delays import analisar_projeto
from ejota.metrics.indicadores import Saude, area_da_lista, calcular_metricas
from ejota.metrics.rede import montar_rede
from tests.conftest import HOJE


def _t(id_: str, lista: str, status: Status, prazo: date | None, fechada: datetime | None = None) -> Tarefa:
    return Tarefa(id=id_, nome=id_, lista=lista, status=status, prazo=prazo, responsaveis=["x"] if prazo else [],
                  criada_em=datetime(2026, 8, 1), fechada_em=fechada, historico_completo=False)


def _projetos():
    a = Projeto("EJ 26-001", "A", [
        _t("a1", "Processos · Sprint 1", Status.VALIDADO, date(2026, 9, 1), datetime(2026, 8, 30)),  # no prazo
        _t("a2", "Processos · Sprint 2", Status.EM_ANDAMENTO, date(2026, 9, 10)),  # 40 dias de atraso
        _t("a3", "Marketing", Status.A_FAZER, date(2026, 11, 1)),  # em dia, não avaliável
    ], [], comercial=Comercial(10000.0, 11000.0, 40, Contrato(8800.0, dias_uteis=44, assinaturas="3 de 6"),
                               porte="Micro empresa",
                               etapas=[EtapaPrevista("Imersão", "Processos", 10), EtapaPrevista("Plano", "Marketing", 30)]))
    b = Projeto("EJ 26-002", "B", [_t("b1", "Etapas", Status.A_FAZER, None)], [])
    c = Projeto("EJ 26-003", "C", [_t("c1", "Tech Dev", Status.VALIDADO, date(2026, 10, 1), datetime(2026, 10, 5))], [],
                comercial=Comercial(None, None, 30, Contrato(3000.0, estimado=True, fonte="nota fiscal"), porte="Micro empresa"))
    return [analisar_projeto(p, HOJE) for p in (a, b, c)]


def test_area_da_lista():
    assert area_da_lista("Finanças · Oraclum") == "Finanças"
    assert area_da_lista("Processos e Gestão") == "Processos"
    assert area_da_lista("Tech Dev") == area_da_lista("Tech-Dev") == "Tech-Dev"
    assert area_da_lista("Etapas") == "Geral"


def test_entrega_e_saude():
    m = calcular_metricas(_projetos())
    e = m.entrega
    assert (e.tarefas, e.avaliaveis, e.no_prazo, e.atrasadas) == (5, 3, 1, 2)
    assert e.pontualidade == 33.3 and e.cobertura_prazo == 80.0
    saude = {p.codigo: p.saude for p in m.projetos}
    assert saude == {"EJ 26-001": Saude.VERMELHO, "EJ 26-002": Saude.AMARELO, "EJ 26-003": Saude.AMARELO}


def test_comercial_usa_valor_do_contrato_e_rateia_por_area():
    m = calcular_metricas(_projetos())
    c = m.comercial
    assert (c.com_contrato, c.estimados, c.carteira) == (1, 1, 11800.0)
    assert c.desconto_medio == 20.0  # 8.800 contratado sobre 11.000 orçado
    assert c.assinaturas_pendentes == ["26-001 (3 de 6)"]
    assert c.valor_em_atraso == 11800.0  # 26-003 também atrasou (fechada depois do prazo)
    p1 = next(p for p in m.projetos if p.codigo == "EJ 26-001")
    assert p1.dias_uteis_previstos == 44 and p1.valor_por_dia_util == 200.0 and p1.desconto == 20.0
    areas = {a.area: a for a in m.areas}
    assert areas["Processos"].valor == 2200.0 and areas["Marketing"].valor == 6600.0
    assert areas["Tech-Dev"].valor == 3000.0  # sem etapas na precificação: tudo para a área do ClickUp
    assert areas["Processos"].entrega.atrasadas == 1


def test_areas_somam_clickup_e_precificacao():
    a = analisar_projeto(Projeto("EJ 26-010", "X", [_t("x1", "Finanças · Oraclum", Status.A_FAZER, None),
                                                     _t("x2", "Processos · Sprint 1", Status.A_FAZER, None)], [],
                                 comercial=Comercial(etapas=[EtapaPrevista("E1", "Finanças", 10)])), HOJE)
    p = calcular_metricas([a]).projetos[0]
    assert p.areas == ["Finanças", "Processos"]


def test_rede_marketing_no_centro_e_bolhas_por_area():
    m = calcular_metricas(_projetos())
    rede = montar_rede(m)
    nomes = [h.area for h in rede.hubs]
    assert nomes[len([a for a in nomes if a != "Geral"]) // 2] == "Marketing"
    assert nomes[-1] == "Geral"  # projeto sem área fica na ponta
    bolha = {b.indicador.codigo: b for b in rede.bolhas}
    assert bolha["EJ 26-001"].area == "Processos" and bolha["EJ 26-001"].outras_areas == ["Marketing"]
    assert bolha["EJ 26-003"].area == "Tech-Dev"
    assert "nenhuma tarefa com prazo" in bolha["EJ 26-002"].lacunas
    assert "sem precificação" in bolha["EJ 26-003"].lacunas and "valor estimado (nota fiscal)" in bolha["EJ 26-003"].lacunas
    assert "contrato com 3 de 6 assinaturas" in bolha["EJ 26-001"].lacunas
    assert "sem contrato no Drive" in bolha["EJ 26-002"].lacunas
    ligs = rede.ligacoes()
    assert ("ej-26-001", "area-processos", True) in ligs and ("ej-26-001", "area-marketing", False) in ligs


def test_area_pelo_objeto_do_contrato_e_orcamento_incompleto():
    a = analisar_projeto(Projeto("EJ 26-011", "X", [_t("y1", "Etapas", Status.A_FAZER, None)], [],
                                 comercial=Comercial(1000.0, 1000.0, 20, Contrato(5000.0, servico="Plano de Marketing"))), HOJE)
    p = calcular_metricas([a]).projetos[0]
    assert p.areas == ["Marketing"]
    assert p.orcamento_incompleto and p.desconto is None
