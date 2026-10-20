"""Fonte de dados fictícia, no mesmo formato que o ClickUp + Drive vão gerar."""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

from ejota.domain import Documento, MudancaStatus, Projeto, Status, Tarefa, TipoDocumento

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "fake"


class FonteFicticia:
    def __init__(self, data_dir: Path = DATA_DIR) -> None:
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
            url=f"#ficticio/clickup/{slug}",
        )

    def _tarefa(self, t: dict) -> Tarefa:
        historico = [MudancaStatus(Status(s), datetime.fromisoformat(em)) for s, em in t["historico"]]
        status = historico[-1].status if historico else Status.A_FAZER

        def ultima_entrada(alvo: Status) -> datetime | None:
            datas = [m.em for m in historico if m.status == alvo]
            return datas[-1] if datas else None

        return Tarefa(
            id=t["id"],
            nome=t["nome"],
            lista=t["lista"],
            status=status,
            prazo=date.fromisoformat(t["prazo"]) if t["prazo"] else None,
            responsaveis=t["responsaveis"],
            criada_em=datetime.fromisoformat(t["criada_em"]),
            fechada_em=ultima_entrada(Status.VALIDADO) if status == Status.VALIDADO else None,
            finalizada_em=ultima_entrada(Status.FINALIZADO),
            historico=historico,
            url=f"#ficticio/clickup/{t['id']}",
        )

    def _documento(self, d: dict) -> Documento:
        texto = None
        if d["arquivo"]:
            texto = (self.data_dir / "docs" / d["arquivo"]).read_text(encoding="utf-8")
        return Documento(
            id=d["id"],
            tipo=TipoDocumento[d["tipo"]],
            titulo=d["titulo"],
            url=f"#ficticio/drive/{d['id']}",
            texto=texto,
        )
