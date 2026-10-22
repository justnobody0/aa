"""Quebra documentos em trechos citáveis, cada um com ID estável.

Cada frase ou item de uma seção vira um trecho (ex.: uma LA, uma cláusula, uma
dificuldade da ata). O ID tem o formato `<doc>#<n>` e é o que aparece como
evidência no relatório.

Os textos reais chegam do Drive com marcação (negrito, escapes, tabelas) e,
nos PDFs, com linhas quebradas no meio da frase. Por isso:
- a marcação é removida antes de quebrar;
- linhas seguidas são juntadas até a frase terminar (. ; : ! ?);
- cada linha de tabela é um trecho;
- "CLÁUSULA N", títulos em maiúsculas e títulos markdown abrem uma seção.
"""

from __future__ import annotations

import re

from ejota.domain import Documento, Projeto, Trecho

_TITULO_MD = re.compile(r"^#{1,6}\s+(.*)$")
_CLAUSULA = re.compile(r"^CL[ÁA]USULA\s+\d+\b.*$", re.IGNORECASE)
_LA = re.compile(r"^\s*(LA[-\s]?\d+)\s*[:.\-–]", re.IGNORECASE)
_FIM_DE_FRASE = re.compile(r"[.;:!?]$")
_MAX_TRECHO = 1200


def limpar(texto: str) -> str:
    anterior = None
    while anterior != texto:  # escapes do markdown podem vir aninhados (\\\[)
        anterior = texto
        texto = re.sub(r"\\([\\*_\[\]()#|\-.>&])", r"\1", texto)
    texto = texto.replace("**", "").replace("&#10;", " ")
    texto = re.sub(r"\[([^\]]+)\]\((?:https?|mailto):[^)]*\)", r"\1", texto)  # links: fica só o texto
    return texto


def _eh_titulo_maiusculo(linha: str) -> bool:
    letras = [c for c in linha if c.isalpha()]
    return 3 <= len(letras) and len(linha) <= 80 and all(c.isupper() for c in letras)


def _linha_de_tabela(linha: str) -> str | None:
    if not linha.startswith("|"):
        return None
    celulas = [c.strip(" #*") for c in linha.strip("|").split("|")]
    celulas = [c for c in celulas if c and not re.fullmatch(r":?-+:?", c)]
    return " | ".join(celulas) if celulas else ""


def trechos_do_documento(doc: Documento) -> list[Trecho]:
    if not doc.texto:
        return []
    trechos: list[Trecho] = []
    secao = "Início"
    buffer: list[str] = []

    def emitir(texto: str) -> None:
        texto = re.sub(r"\s+", " ", texto).strip().lstrip("-*● ").strip()
        if not texto:
            return
        rotulo = secao
        la = _LA.match(texto)
        if la:
            rotulo = f"{secao} › {la.group(1).upper().replace(' ', '-')}"
        trechos.append(
            Trecho(
                id=f"{doc.id}#{len(trechos) + 1}",
                documento_id=doc.id,
                tipo=doc.tipo,
                titulo_documento=doc.titulo,
                secao=rotulo,
                texto=texto,
                url=doc.url,
            )
        )

    def descarregar() -> None:
        if buffer:
            emitir(" ".join(buffer))
            buffer.clear()

    for bruta in limpar(doc.texto).splitlines():
        linha = bruta.strip()
        if not linha:
            continue
        titulo = _TITULO_MD.match(linha)
        if titulo or _CLAUSULA.match(linha) or (_eh_titulo_maiusculo(linha) and not buffer):
            descarregar()
            secao = (titulo.group(1) if titulo else linha).strip(" *#")
            continue
        tabela = _linha_de_tabela(linha)
        if tabela is not None:
            descarregar()
            emitir(tabela)
            continue
        buffer.append(linha)
        if _FIM_DE_FRASE.search(linha) or sum(map(len, buffer)) > _MAX_TRECHO:
            descarregar()
    descarregar()
    return trechos


def trechos_do_projeto(projeto: Projeto) -> list[Trecho]:
    return [t for doc in projeto.documentos for t in trechos_do_documento(doc)]
