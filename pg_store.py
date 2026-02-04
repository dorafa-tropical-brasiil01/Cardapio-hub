from __future__ import annotations

import mimetypes
import json
import os
import secrets
from typing import Any

import psycopg2
import psycopg2.extras


def is_enabled() -> bool:
    return bool(str(os.environ.get("DATABASE_URL") or "").strip())


def _conn():
    return psycopg2.connect(str(os.environ.get("DATABASE_URL") or "").strip())


def init_db() -> None:
    if not is_enabled():
        return

    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS cardapio_solicitacoes (
                    id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    mesa INTEGER,
                    criado_em TIMESTAMPTZ,
                    record JSONB NOT NULL
                )
                """
            )
            cur.execute("CREATE INDEX IF NOT EXISTS idx_cardapio_solicitacoes_status ON cardapio_solicitacoes(status)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_cardapio_solicitacoes_mesa ON cardapio_solicitacoes(mesa)")
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS cardapio_mesas (
                    mesa INTEGER PRIMARY KEY,
                    token TEXT NOT NULL
                )
                """
            )

            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS cardapio_catalogo_publicado (
                    id TEXT PRIMARY KEY,
                    atualizado_em TIMESTAMPTZ,
                    record JSONB NOT NULL
                )
                """
            )

            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS cardapio_assets (
                    path TEXT PRIMARY KEY,
                    content BYTEA NOT NULL,
                    content_type TEXT,
                    atualizado_em TIMESTAMPTZ
                )
                """
            )
            cur.execute("CREATE INDEX IF NOT EXISTS idx_cardapio_assets_updated ON cardapio_assets(atualizado_em)")


def ensure_default_mesas(*, max_mesas: int = 30) -> None:
    if not is_enabled():
        return

    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM cardapio_mesas")
            count = int(cur.fetchone()[0] or 0)
            if count > 0:
                return
            for mesa in range(1, int(max_mesas) + 1):
                token_str = secrets.token_urlsafe(24)
                cur.execute(
                    "INSERT INTO cardapio_mesas(mesa, token) VALUES (%s, %s) ON CONFLICT (mesa) DO NOTHING",
                    (int(mesa), str(token_str)),
                )


def get_table_token_map() -> dict[int, str]:
    if not is_enabled():
        return {}

    out: dict[int, str] = {}
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT mesa, token FROM cardapio_mesas ORDER BY mesa")
            for mesa, token in cur.fetchall():
                try:
                    out[int(mesa)] = str(token)
                except Exception:
                    continue
    return out


def save_solicitacao(*, record: dict[str, Any]) -> None:
    if not is_enabled():
        return

    sid = str(record.get("id") or "").strip()
    status = str(record.get("status") or "").strip().upper() or "PENDENTE"
    mesa = record.get("mesa")
    try:
        mesa_i = int(mesa) if mesa is not None else None
    except Exception:
        mesa_i = None
    criado_em = record.get("criado_em")
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO cardapio_solicitacoes(id, status, mesa, criado_em, record)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    status=EXCLUDED.status,
                    mesa=EXCLUDED.mesa,
                    criado_em=EXCLUDED.criado_em,
                    record=EXCLUDED.record
                """,
                (
                    sid,
                    status,
                    mesa_i,
                    criado_em,
                    psycopg2.extras.Json(record),
                ),
            )


def get_solicitacao(*, solicitacao_id: str) -> dict[str, Any] | None:
    if not is_enabled():
        return None

    sid = str(solicitacao_id or "").strip()
    if not sid:
        return None

    with _conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT record FROM cardapio_solicitacoes WHERE id=%s", (sid,))
            row = cur.fetchone()
            if not row:
                return None
            rec = row.get("record")
            return dict(rec) if isinstance(rec, dict) else None


def save_asset(*, path: str, content: bytes, content_type: str | None = None) -> None:
    if not is_enabled():
        return
    p = str(path or "").strip()
    if not p:
        return
    if not isinstance(content, (bytes, bytearray)):
        return

    ct = str(content_type or "").strip() or None
    if ct is None:
        ct_guess, _ = mimetypes.guess_type(p)
        ct = str(ct_guess).strip() if ct_guess else None

    updated_em = __import__("datetime").datetime.now().isoformat(timespec="seconds")
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO cardapio_assets(path, content, content_type, atualizado_em)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (path) DO UPDATE SET
                    content=EXCLUDED.content,
                    content_type=EXCLUDED.content_type,
                    atualizado_em=EXCLUDED.atualizado_em
                """,
                (
                    p,
                    psycopg2.Binary(bytes(content)),
                    ct,
                    updated_em,
                ),
            )


def get_asset(*, path: str) -> tuple[bytes, str | None] | None:
    if not is_enabled():
        return None
    p = str(path or "").strip()
    if not p:
        return None

    with _conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT content, content_type FROM cardapio_assets WHERE path=%s", (p,))
            row = cur.fetchone()
            if not row:
                return None
            content = row.get("content")
            ct = row.get("content_type")
            if content is None:
                return None
            return (bytes(content), (str(ct).strip() if ct else None))


def list_by_status(*, status: str) -> list[dict[str, Any]]:
    if not is_enabled():
        return []

    st = str(status or "").strip().upper() or "PENDENTE"
    with _conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT record FROM cardapio_solicitacoes WHERE status=%s ORDER BY criado_em DESC NULLS LAST",
                (st,),
            )
            out: list[dict[str, Any]] = []
            for row in cur.fetchall() or []:
                rec = row.get("record")
                if isinstance(rec, dict):
                    out.append(dict(rec))
            return out


def save_catalogo_publicado(*, record: dict[str, Any]) -> None:
    if not is_enabled():
        return
    if not isinstance(record, dict):
        return

    updated_em = __import__("datetime").datetime.now().isoformat(timespec="seconds")
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO cardapio_catalogo_publicado(id, atualizado_em, record)
                VALUES (%s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    atualizado_em=EXCLUDED.atualizado_em,
                    record=EXCLUDED.record
                """,
                (
                    "published",
                    updated_em,
                    psycopg2.extras.Json(record),
                ),
            )


def get_catalogo_publicado() -> dict[str, Any] | None:
    if not is_enabled():
        return None

    with _conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT record FROM cardapio_catalogo_publicado WHERE id=%s", ("published",))
            row = cur.fetchone()
            if not row:
                return None
            rec = row.get("record")
            return dict(rec) if isinstance(rec, dict) else None


def update_solicitacao_status(*, solicitacao_id: str, pdv_status: str) -> None:
    if not is_enabled():
        return

    sid = str(solicitacao_id or "").strip()
    if not sid:
        return
    st = str(pdv_status or "").strip().upper()
    if not st:
        return

    rec = get_solicitacao(solicitacao_id=sid)
    if not isinstance(rec, dict):
        raise KeyError("nao_encontrado")

    rec["pdv_status"] = st
    rec["pdv_status_em"] = __import__("datetime").datetime.now().isoformat(timespec="seconds")
    save_solicitacao(record=rec)
