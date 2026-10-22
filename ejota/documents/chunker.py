"""Quebra documentos em trechos citáveis, cada um com ID estável.

Cada linha não vazia de uma seção vira um trecho (ex.: uma LA, uma cláusula,
uma dificuldade da ata). O ID tem o formato `<doc>#<n>` e é o que aparece
como evidência no relatório.
"""

from __future__ import annotations

import re

from ejota.domain import Documento, Projeto, Trecho

_TITULO = re.compile(r"^#{1,6}\s+(.*)$")
_LA = re.compile(r"^\s*(LA[-\s]?\d+)\s*[:.\-–]", re.IGNORECASE)


def trechos_do_documento(doc: Documento) -> list[Trecho]:
    if not doc.texto:
        return []
    trechos: list[Trecho] = []
    secao = "Início"
    for linha in doc.texto.splitlines():
        linha = linha.strip()
        if not linha:
            continue
        titulo = _TITULO.match(linha)
        if titulo:
            secao = titulo.group(1).strip()
            continue
        rotulo = secao
        la = _LA.match(linha)
        if la:
            rotulo = f"{secao} › {la.group(1).upper().replace(' ', '-')}"
        n = len(trechos) + 1
        trechos.append(
            Trecho(
                id=f"{doc.id}#{n}",
                documento_id=doc.id,
                tipo=doc.tipo,
                titulo_documento=doc.titulo,
                secao=rotulo,
                texto=linha.lstrip("-* ").strip(),
                url=doc.url,
            )
        )
    return trechos


def trechos_do_projeto(projeto: Projeto) -> list[Trecho]:
    return [t for doc in projeto.documentos for t in trechos_do_documento(doc)]
