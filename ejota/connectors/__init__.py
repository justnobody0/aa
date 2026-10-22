from __future__ import annotations

from ejota.config import Settings
from ejota.connectors.base import FonteDeProjetos


def get_source(settings: Settings) -> FonteDeProjetos:
    if settings.data_source == "fake":
        from ejota.connectors.fake import FonteFicticia

        return FonteFicticia()
    if settings.data_source == "snapshot":
        from pathlib import Path

        from ejota.connectors.fake import FonteArquivo

        if not settings.snapshot_dir:
            raise ValueError("EJOTA_SNAPSHOT_DIR não definido.")
        return FonteArquivo(Path(settings.snapshot_dir))
    # Conectores reais entram na Etapa 7, só após autorização da diretoria.
    raise NotImplementedError("Fonte 'real' ainda não habilitada (Etapa 7).")
