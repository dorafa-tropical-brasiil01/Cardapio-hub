from __future__ import annotations

import mimetypes
import json
import os
import secrets
from typing import Any
from datetime import datetime

import psycopg2
import psycopg2.extras


_DB_READY = False


def is_enabled() -> bool:
    return bool(str(os.environ.get("DATABASE_URL") or "").strip())


def _conn():
    base_dsn = str(os.environ.get("DATABASE_URL") or "").strip()
    if not base_dsn:
        return psycopg2.connect("")

    # Railway pode fornecer URLs que aceitam SSL de forma diferente conforme o provedor.
    # Tentamos alguns modos sem registrar o DSN (evita vazar credenciais em logs).
    low = base_dsn.lower()
    candidates: list[str] = []
    if "sslmode=" in low:
        candidates.append(base_dsn)
    else:
        sep = "&" if "?" in base_dsn else "?"
        candidates.append(base_dsn + sep + "sslmode=require")
        candidates.append(base_dsn + sep + "sslmode=prefer")
        candidates.append(base_dsn + sep + "sslmode=disable")

    last_err: Exception | None = None
    for dsn in candidates:
        try:
            return psycopg2.connect(dsn)
        except Exception as e:
            last_err = e
            continue
    assert last_err is not None
    raise last_err


def _ensure_db_ready() -> None:
    global _DB_READY
    if _DB_READY:
        return
    init_db()
    _DB_READY = True


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

            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS promo_inscricoes (
                    sale_id BIGINT PRIMARY KEY,
                    campaign_name TEXT,
                    cliente_nome TEXT NOT NULL,
                    cliente_whatsapp TEXT NOT NULL,
                    produtos TEXT NOT NULL,
                    numero_sorteio TEXT NOT NULL,
                    token TEXT NOT NULL,
                    emitido_em TIMESTAMPTZ NOT NULL,
                    confirmado_em TIMESTAMPTZ,
                    pdv_installation_id TEXT
                )
                """
            )
            try:
                cur.execute("ALTER TABLE promo_inscricoes ADD COLUMN IF NOT EXISTS campaign_name TEXT")
            except Exception:
                pass
            cur.execute("CREATE INDEX IF NOT EXISTS idx_promo_inscricoes_emitido_em ON promo_inscricoes(emitido_em)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_promo_inscricoes_confirmado_em ON promo_inscricoes(confirmado_em)")
            try:
                cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_promo_inscricoes_token_unique ON promo_inscricoes(token)")
            except Exception:
                pass


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

    _ensure_db_ready()

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

    _ensure_db_ready()
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

    _ensure_db_ready()

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


def upsert_promo_inscricao_emitida(
    *,
    sale_id: int,
    campaign_name: str | None = None,
    cliente_nome: str,
    cliente_whatsapp: str,
    produtos: str,
    numero_sorteio: str,
    token: str,
    pdv_installation_id: str | None,
    emitido_em_iso: str | None = None,
) -> dict[str, Any]:
    if not is_enabled():
        raise RuntimeError("db_disabled")

    _ensure_db_ready()

    try:
        sid = int(sale_id)
    except Exception:
        raise ValueError("sale_id_invalido")

    nome = str(cliente_nome or "").strip()
    whatsapp = str(cliente_whatsapp or "").strip()
    prods = str(produtos or "").strip()
    lucky = str(numero_sorteio or "").strip()
    tok = str(token or "").strip()
    camp = str(campaign_name or "").strip() or None
    inst = str(pdv_installation_id or "").strip() or None

    if not nome or not whatsapp or not prods or not lucky or not tok:
        raise ValueError("campos_obrigatorios")

    emitido_em = emitido_em_iso
    if not emitido_em:
        emitido_em = datetime.now().isoformat(timespec="seconds")

    with _conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                INSERT INTO promo_inscricoes(
                    sale_id,
                    campaign_name,
                    cliente_nome,
                    cliente_whatsapp,
                    produtos,
                    numero_sorteio,
                    token,
                    emitido_em,
                    pdv_installation_id
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (sale_id) DO UPDATE SET
                    campaign_name=EXCLUDED.campaign_name,
                    cliente_nome=EXCLUDED.cliente_nome,
                    cliente_whatsapp=EXCLUDED.cliente_whatsapp,
                    produtos=EXCLUDED.produtos,
                    numero_sorteio=EXCLUDED.numero_sorteio,
                    token=EXCLUDED.token,
                    pdv_installation_id=EXCLUDED.pdv_installation_id
                RETURNING sale_id, campaign_name, cliente_nome, cliente_whatsapp, produtos, numero_sorteio, token, emitido_em, confirmado_em, pdv_installation_id
                """,
                (sid, camp, nome, whatsapp, prods, lucky, tok, emitido_em, inst),
            )
            row = cur.fetchone() or {}
            return dict(row)


def get_promo_inscricao_by_sale_id(*, sale_id: int) -> dict[str, Any] | None:
    if not is_enabled():
        return None

    try:
        sid = int(sale_id)
    except Exception:
        return None

    with _conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT sale_id, campaign_name, cliente_nome, cliente_whatsapp, produtos, numero_sorteio, token, emitido_em, confirmado_em, pdv_installation_id
                FROM promo_inscricoes
                WHERE sale_id=%s
                """,
                (sid,),
            )
            row = cur.fetchone()
            return dict(row) if row else None


def get_promo_inscricao_by_token(*, token: str) -> dict[str, Any] | None:
    if not is_enabled():
        return None

    tok = str(token or "").strip()
    if not tok:
        return None

    with _conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT sale_id, campaign_name, cliente_nome, cliente_whatsapp, produtos, numero_sorteio, token, emitido_em, confirmado_em, pdv_installation_id
                FROM promo_inscricoes
                WHERE token=%s
                """,
                (tok,),
            )
            row = cur.fetchone()
            return dict(row) if row else None


def confirm_promo_inscricao(*, sale_id: int) -> dict[str, Any] | None:
    if not is_enabled():
        return None

    try:
        sid = int(sale_id)
    except Exception:
        return None

    with _conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT sale_id, campaign_name, cliente_nome, cliente_whatsapp, produtos, numero_sorteio, token, emitido_em, confirmado_em, pdv_installation_id
                FROM promo_inscricoes
                WHERE sale_id=%s
                """,
                (sid,),
            )
            existing = cur.fetchone()
            if not existing:
                return None

            already_confirmed = existing.get("confirmado_em") is not None
            if already_confirmed:
                out = dict(existing)
                out["already_confirmed"] = True
                return out

            confirmed_at = datetime.now().isoformat(timespec="seconds")
            cur.execute(
                """
                UPDATE promo_inscricoes
                SET confirmado_em = %s
                WHERE sale_id=%s
                RETURNING sale_id, campaign_name, cliente_nome, cliente_whatsapp, produtos, numero_sorteio, token, emitido_em, confirmado_em, pdv_installation_id
                """,
                (confirmed_at, sid),
            )
            row = cur.fetchone()
            out = dict(row) if row else dict(existing)
            out["already_confirmed"] = False
            return out


def list_promo_inscricoes_periodo(*, ini: str, fim: str) -> list[dict[str, Any]]:
    if not is_enabled():
        return []

    ini_s = str(ini or "").strip()
    fim_s = str(fim or "").strip()
    if not ini_s or not fim_s:
        return []

    with _conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT sale_id, campaign_name, cliente_nome, cliente_whatsapp, produtos, numero_sorteio, token, emitido_em, confirmado_em, pdv_installation_id
                FROM promo_inscricoes
                WHERE emitido_em >= %s::timestamptz
                  AND emitido_em < (%s::timestamptz + INTERVAL '1 day')
                ORDER BY emitido_em DESC
                """,
                (ini_s, fim_s),
            )
            return [dict(r) for r in (cur.fetchall() or [])]
