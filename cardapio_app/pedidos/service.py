from __future__ import annotations

from typing import Any

from .. import core


def get_solicitacao_by_id(*, solicitacao_id: str) -> dict[str, Any] | None:
    if not core.pg_enabled():
        return None
    try:
        rec = core.pg_store.get_solicitacao(solicitacao_id=str(solicitacao_id or "").strip())
    except Exception:
        rec = None
    return dict(rec) if isinstance(rec, dict) else None
