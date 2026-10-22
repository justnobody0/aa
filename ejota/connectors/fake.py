"""Fontes de dados em arquivo, no mesmo formato que o ClickUp + Drive vão gerar.

- `FonteFicticia`: os projetos fictícios que vêm com o código.
- `FonteArquivo`: um snapshot local (ex.: dados reais exportados), apontado por
  EJOTA_SNAPSHOT_DIR. Snapshots reais nunca vão para o git.

Formato de `projects.json`: veja `data/fake/projects.json`. Campos opcionais
para dados reais: `status`, `fechada_em`, `finalizada_em`, `url` (tarefa,
projeto e documento) e `historico_completo`.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

from ejota.domain import Documento, MudancaStatus, Projeto, Status, Tarefa, TipoDocumento

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "fake"


def _dt(valor: str | None) -> datetime | None:
    return datetime.fromisoformat(valor) if valor else None


class FonteArquivo:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir

    def listar_projetos(self) -> list[Projeto]:
        raw = json.loads((self.data_dir / "projects.json").read_text(encoding="utf-8"))
        return [self._projeto(p) for p in raw["projetos"]]

    def _projeto(self, p: dict) -> Projeto:
        slug = p["codigo"].replace(" ", "-").lower()
        return Projeto(
            codigo=p["codigo"],
            cliente=p["cliente"],
            tarefas=[self._tarefa(t) for t in p["tarefas"]],
            documentos=[self._documento(d) for d in p["documentos"]],
            url=p.get("url") or f"#ficticio/clickup/{slug}",
        )

    def _tarefa(self, t: dict) -> Tarefa:
        historico = [MudancaStatus(Status.de_texto(s), datetime.fromisoformat(em)) for s, em in t.get("historico", [])]
        if "status" in t:
            status = Status.de_texto(t["status"])
        else:
            status = historico[-1].status if historico else Status.A_FAZER

        def ultima_entrada(alvo: Status) -> datetime | None:
            datas = [m.em for m in historico if m.status == alvo]
            return datas[-1] if datas else None

        fechada = _dt(t.get("fechada_em")) or ultima_entrada(Status.VALIDADO)
        return Tarefa(
            id=t["id"],
            nome=t["nome"],
            lista=t["lista"],
            status=status,
            prazo=date.fromisoformat(t["prazo"]) if t["prazo"] else None,
            responsaveis=t["responsaveis"],
            criada_em=datetime.fromisoformat(t["criada_em"]),
            fechada_em=fechada if status == Status.VALIDADO else None,
            finalizada_em=_dt(t.get("finalizada_em")) or ultima_entrada(Status.FINALIZADO),
            historico=historico,
            url=t.get("url") or f"#ficticio/clickup/{t['id']}",
            historico_completo=t.get("historico_completo", True),
        )

    def _documento(self, d: dict) -> Documento:
        texto = None
        if d["arquivo"]:
            texto = (self.data_dir / "docs" / d["arquivo"]).read_text(encoding="utf-8")
        return Documento(
            id=d["id"],
            tipo=TipoDocumento[d["tipo"]],
            titulo=d["titulo"],
            url=d.get("url") or f"#ficticio/drive/{d['id']}",
            texto=texto,
        )


class FonteFicticia(FonteArquivo):
    def __init__(self, data_dir: Path = DATA_DIR) -> None:
        super().__init__(data_dir)
