from __future__ import annotations

from ejota.analysis.pseudonym import Pseudonimizador
from ejota.analysis.service import analisar_causas
from ejota.analysis.verify import CausaProposta, verificar
from ejota.connectors.fake import FonteFicticia
from ejota.documents.chunker import trechos_do_documento
from ejota.domain import Categoria, Confianca, Documento, TipoDocumento, Trecho
from ejota.engine.delays import analisar_projeto
from tests.conftest import HOJE


def _trecho(id_: str, doc: str, texto: str) -> Trecho:
    return Trecho(id_, doc, TipoDocumento.ATA, doc, "Dificuldades", texto, "#")


def test_chunker_gera_ids_e_rotula_las():
    doc = Documento("d1", TipoDocumento.ATA, "ATA", "#", "# ATA\n## Lições Aprendidas\nLA-2: Faça X.\n\nOutra linha.")
    trechos = trechos_do_documento(doc)
    assert [t.id for t in trechos] == ["d1#1", "d1#2"]
    assert trechos[0].secao == "Lições Aprendidas › LA-2"


def test_citacao_inventada_e_descartada():
    trechos = [_trecho("a#1", "ATA", "O cliente atrasou o envio dos dados.")]
    propostas = [CausaProposta(Categoria.CLIENTE, "Cliente atrasou.", [("a#1", "o cliente nunca respondeu")], [])]
    [causa] = verificar(propostas, trechos, set())
    assert causa.evidencias == []
    assert causa.confianca == Confianca.SEM_EVIDENCIA
    assert causa.explicacao == "sem evidência"


def test_citacao_de_trecho_inexistente_e_descartada():
    propostas = [CausaProposta(Categoria.CLIENTE, "x", [("nao-existe#9", "qualquer")], [])]
    assert verificar(propostas, [], set())[0].confianca == Confianca.SEM_EVIDENCIA


def test_confianca_por_regra():
    trechos = [_trecho("a#1", "ATA", "O cliente atrasou o envio."), _trecho("c#1", "Contrato", "Prazo de 5 dias úteis.")]
    uma = CausaProposta(Categoria.CLIENTE, "x", [("a#1", "cliente atrasou")], [])
    duas_fontes = CausaProposta(Categoria.CLIENTE, "x", [("a#1", "cliente atrasou"), ("c#1", "5 dias úteis")], [])
    com_clickup = CausaProposta(Categoria.CLIENTE, "x", [("a#1", "cliente atrasou")], ["t1"])
    r = verificar([uma, duas_fontes, com_clickup], trechos, {"t1"})
    assert [c.confianca for c in r] == [Confianca.BAIXA, Confianca.ALTA, Confianca.MEDIA]


def test_pseudonimizacao_ida_e_volta():
    p = Pseudonimizador(["Padaria Aurora"])
    texto = "A Padaria Aurora pagou R$ 4.800,00; contato: dono@aurora.com.br"
    oculto = p.ocultar(texto)
    assert "Aurora" not in oculto and "4.800" not in oculto and "@" not in oculto
    assert "[CLIENTE_1]" in oculto and "[VALOR_1]" in oculto
    assert p.revelar(oculto) == texto


def test_heuristica_acerta_causas_dos_ficticios(settings):
    esperado = {
        "EJ 26-901": Categoria.ESCOPO,
        "EJ 26-902": Categoria.CLIENTE,
        "EJ 26-903": Categoria.EQUIPE,
        "EJ 26-904": Categoria.PRAZO,
        "EJ 26-906": Categoria.OUTRA,
    }
    for projeto in FonteFicticia().listar_projetos():
        analise = analisar_projeto(projeto, HOJE)
        if projeto.codigo not in esperado:
            assert not analise.atrasado
            continue
        resultado = analisar_causas(analise, settings)
        principal = next(c for c in resultado.causas if c.principal)
        assert principal.categoria == esperado[projeto.codigo], projeto.codigo
        if projeto.codigo == "EJ 26-906":
            assert principal.confianca == Confianca.SEM_EVIDENCIA
        else:
            assert principal.evidencias


def test_falha_do_claude_cai_para_heuristica(settings, monkeypatch):
    from ejota.analysis import claude

    def explode(*a, **k):
        raise RuntimeError("sem rede")

    monkeypatch.setattr(claude, "propor_causas", explode)
    settings.analyzer = "claude"
    projeto = FonteFicticia().listar_projetos()[0]
    resultado = analisar_causas(analisar_projeto(projeto, HOJE), settings)
    assert resultado.metodo.startswith("heurística")
    assert resultado.aviso


def test_claude_com_resposta_simulada_passa_pelo_verificador(settings, monkeypatch):
    """Simula a resposta do Claude sobre texto pseudonimizado, sem chamar a API."""
    from ejota.analysis import claude

    def falso(analise, trechos, pseudo, model):
        ocultos = claude.pseudo_trechos(trechos, pseudo)
        ata = next(t for t in ocultos if "identidade visual nova" in t.texto)
        return [
            CausaProposta(Categoria.ESCOPO, "Pedido extra de [CLIENTE_1].", [(ata.id, ata.texto)], ["t901-3"], True),
            CausaProposta(Categoria.EQUIPE, "Inventada.", [(ata.id, "texto que não existe")], [], False),
        ]

    monkeypatch.setattr(claude, "propor_causas", falso)
    settings.analyzer = "claude"
    projeto = next(p for p in FonteFicticia().listar_projetos() if p.codigo == "EJ 26-901")
    resultado = analisar_causas(analisar_projeto(projeto, HOJE), settings)
    escopo, equipe = resultado.causas
    assert escopo.principal and escopo.evidencias
    assert "Padaria Aurora" in escopo.explicacao  # marcador revertido na exibição
    assert equipe.confianca == Confianca.SEM_EVIDENCIA
