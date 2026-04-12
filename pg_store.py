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

            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS ops_users (
                    id BIGSERIAL PRIMARY KEY,
                    username TEXT NOT NULL,
                    role TEXT NOT NULL,
                    nome TEXT,
                    telefone TEXT,
                    telegram TEXT,
                    endereco TEXT,
                    pix TEXT,
                    ativo BOOLEAN NOT NULL DEFAULT TRUE,
                    password_salt TEXT NOT NULL,
                    password_hash TEXT NOT NULL,
                    criado_em TIMESTAMPTZ NOT NULL,
                    atualizado_em TIMESTAMPTZ
                )
                """
            )
            try:
                cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_ops_users_username_unique ON ops_users(username)")
            except Exception:
                pass

            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS kds_orders (
                    solicitacao_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    created_em TIMESTAMPTZ NOT NULL,
                    started_em TIMESTAMPTZ,
                    done_em TIMESTAMPTZ,
                    ops_user_id BIGINT
                )
                """
            )
            cur.execute("CREATE INDEX IF NOT EXISTS idx_kds_orders_status_created ON kds_orders(status, created_em)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_kds_orders_done_em ON kds_orders(done_em)")

            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS kds_current_selection (
                    ops_user_id BIGINT PRIMARY KEY,
                    solicitacao_id TEXT NOT NULL,
                    selected_em TIMESTAMPTZ NOT NULL
                )
                """
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_kds_current_selection_selected_em ON kds_current_selection(selected_em)"
            )

            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS log_runs (
                    id BIGSERIAL PRIMARY KEY,
                    ops_user_id BIGINT NOT NULL,
                    status TEXT NOT NULL,
                    created_em TIMESTAMPTZ NOT NULL,
                    started_em TIMESTAMPTZ,
                    finished_em TIMESTAMPTZ
                )
                """
            )
            cur.execute("CREATE INDEX IF NOT EXISTS idx_log_runs_user_status ON log_runs(ops_user_id, status)")

            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS log_run_items (
                    run_id BIGINT NOT NULL REFERENCES log_runs(id) ON DELETE CASCADE,
                    solicitacao_id TEXT NOT NULL,
                    added_em TIMESTAMPTZ NOT NULL,
                    delivered_em TIMESTAMPTZ,
                    PRIMARY KEY (run_id, solicitacao_id)
                )
                """
            )
            cur.execute("CREATE INDEX IF NOT EXISTS idx_log_run_items_solicitacao ON log_run_items(solicitacao_id)")

            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS log_order_flags (
                    solicitacao_id TEXT PRIMARY KEY,
                    flag TEXT NOT NULL,
                    flagged_em TIMESTAMPTZ NOT NULL,
                    ops_user_id BIGINT,
                    note TEXT
                )
                """
            )
            cur.execute("CREATE INDEX IF NOT EXISTS idx_log_order_flags_flag ON log_order_flags(flag)")

            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS log_order_events (
                    id BIGSERIAL PRIMARY KEY,
                    solicitacao_id TEXT NOT NULL,
                    event TEXT NOT NULL,
                    created_em TIMESTAMPTZ NOT NULL,
                    ops_user_id BIGINT,
                    note TEXT
                )
                """
            )
            cur.execute("CREATE INDEX IF NOT EXISTS idx_log_order_events_solicitacao ON log_order_events(solicitacao_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_log_order_events_event ON log_order_events(event)")


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


def create_ops_user(
    *,
    username: str,
    role: str,
    nome: str | None,
    telefone: str | None,
    telegram: str | None,
    endereco: str | None,
    pix: str | None,
    password_salt: str,
    password_hash: str,
) -> dict[str, Any] | None:
    if not is_enabled():
        return None

    _ensure_db_ready()

    u = str(username or "").strip().lower()
    r = str(role or "").strip().upper()
    if not u or not r:
        return None
    if not password_salt or not password_hash:
        return None

    now = datetime.now().isoformat(timespec="seconds")

    with _conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                INSERT INTO ops_users(
                    username, role, nome, telefone, telegram, endereco, pix,
                    ativo, password_salt, password_hash, criado_em, atualizado_em
                )
                VALUES (%s,%s,%s,%s,%s,%s,%s,TRUE,%s,%s,%s,NULL)
                RETURNING *
                """,
                (
                    u,
                    r,
                    nome,
                    telefone,
                    telegram,
                    endereco,
                    pix,
                    str(password_salt),
                    str(password_hash),
                    now,
                ),
            )
            row = cur.fetchone()
            return dict(row) if row else None


def get_ops_user_by_username(*, username: str) -> dict[str, Any] | None:
    if not is_enabled():
        return None

    _ensure_db_ready()

    u = str(username or "").strip().lower()
    if not u:
        return None

    with _conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM ops_users WHERE username=%s", (u,))
            row = cur.fetchone()
            return dict(row) if row else None


def list_ops_users_by_role(*, role: str) -> list[dict[str, Any]]:
    if not is_enabled():
        return []
    _ensure_db_ready()
    r = str(role or "").strip().upper()
    if not r:
        return []
    with _conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT *
                FROM ops_users
                WHERE role=%s AND ativo=TRUE
                ORDER BY id ASC
                """,
                (r,),
            )
            return [dict(x) for x in (cur.fetchall() or [])]


def kds_summary_by_user_periodo(*, ini: str, fim: str) -> list[dict[str, Any]]:
    if not is_enabled():
        return []
    _ensure_db_ready()
    ini_s = str(ini or "").strip()
    fim_s = str(fim or "").strip()
    if not ini_s or not fim_s:
        return []

    with _conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT
                    k.ops_user_id,
                    u.username AS ops_username,
                    u.nome AS ops_nome,
                    COUNT(*)::bigint AS pedidos,
                    AVG(EXTRACT(EPOCH FROM (k.done_em - k.started_em)))::bigint AS avg_preparo_seconds,
                    MIN(EXTRACT(EPOCH FROM (k.done_em - k.started_em)))::bigint AS min_preparo_seconds,
                    MAX(EXTRACT(EPOCH FROM (k.done_em - k.started_em)))::bigint AS max_preparo_seconds,
                    AVG(EXTRACT(EPOCH FROM (k.done_em - k.created_em)))::bigint AS avg_total_seconds
                FROM kds_orders k
                LEFT JOIN ops_users u ON u.id=k.ops_user_id
                WHERE k.status='PRONTO'
                  AND k.done_em IS NOT NULL
                  AND k.started_em IS NOT NULL
                  AND k.ops_user_id IS NOT NULL
                  AND k.done_em >= %s::timestamptz
                  AND k.done_em < (%s::timestamptz + INTERVAL '1 day')
                GROUP BY k.ops_user_id, u.username, u.nome
                ORDER BY avg_preparo_seconds ASC NULLS LAST, pedidos DESC
                """,
                (ini_s, fim_s),
            )
            return [dict(x) for x in (cur.fetchall() or [])]


def logistica_summary_by_user_periodo(*, ini: str, fim: str) -> list[dict[str, Any]]:
    if not is_enabled():
        return []
    _ensure_db_ready()
    ini_s = str(ini or "").strip()
    fim_s = str(fim or "").strip()
    if not ini_s or not fim_s:
        return []

    with _conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT
                    r.ops_user_id,
                    u.username AS ops_username,
                    u.nome AS ops_nome,
                    COUNT(*)::bigint AS corridas,
                    AVG(EXTRACT(EPOCH FROM (r.finished_em - r.started_em)))::bigint AS avg_corrida_seconds,
                    MIN(EXTRACT(EPOCH FROM (r.finished_em - r.started_em)))::bigint AS min_corrida_seconds,
                    MAX(EXTRACT(EPOCH FROM (r.finished_em - r.started_em)))::bigint AS max_corrida_seconds,
                    AVG(it.itens)::numeric(10,2) AS avg_itens
                FROM log_runs r
                LEFT JOIN ops_users u ON u.id=r.ops_user_id
                LEFT JOIN (
                    SELECT run_id, COUNT(*)::bigint AS itens
                    FROM log_run_items
                    GROUP BY run_id
                ) it ON it.run_id=r.id
                WHERE r.status='FINALIZADA'
                  AND r.finished_em IS NOT NULL
                  AND r.started_em IS NOT NULL
                  AND r.ops_user_id IS NOT NULL
                  AND r.finished_em >= %s::timestamptz
                  AND r.finished_em < (%s::timestamptz + INTERVAL '1 day')
                GROUP BY r.ops_user_id, u.username, u.nome
                ORDER BY avg_corrida_seconds ASC NULLS LAST, corridas DESC
                """,
                (ini_s, fim_s),
            )
            return [dict(x) for x in (cur.fetchall() or [])]


def update_ops_user(
    *,
    username: str,
    role: str | None = None,
    nome: str | None = None,
    telefone: str | None = None,
    telegram: str | None = None,
    endereco: str | None = None,
    pix: str | None = None,
    ativo: bool | None = None,
    password_salt: str | None = None,
    password_hash: str | None = None,
) -> dict[str, Any] | None:
    if not is_enabled():
        return None

    _ensure_db_ready()

    u = str(username or "").strip().lower()
    if not u:
        return None

    now = datetime.now().isoformat(timespec="seconds")
    cols: list[str] = []
    vals: list[Any] = []

    if role is not None:
        cols.append("role=%s")
        vals.append(str(role or "").strip().upper())
    if nome is not None:
        cols.append("nome=%s")
        vals.append(nome)
    if telefone is not None:
        cols.append("telefone=%s")
        vals.append(telefone)
    if telegram is not None:
        cols.append("telegram=%s")
        vals.append(telegram)
    if endereco is not None:
        cols.append("endereco=%s")
        vals.append(endereco)
    if pix is not None:
        cols.append("pix=%s")
        vals.append(pix)
    if ativo is not None:
        cols.append("ativo=%s")
        vals.append(bool(ativo))
    if password_salt is not None and password_hash is not None:
        cols.append("password_salt=%s")
        vals.append(str(password_salt))
        cols.append("password_hash=%s")
        vals.append(str(password_hash))

    cols.append("atualizado_em=%s")
    vals.append(now)

    if len(cols) == 0:
        return get_ops_user_by_username(username=u)

    vals.append(u)
    q = "UPDATE ops_users SET " + ", ".join(cols) + " WHERE username=%s RETURNING *"
    with _conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(q, tuple(vals))
            row = cur.fetchone()
            return dict(row) if row else None


def upsert_ops_user(
    *,
    username: str,
    role: str,
    nome: str | None,
    telefone: str | None,
    telegram: str | None,
    endereco: str | None,
    pix: str | None,
    ativo: bool = True,
    password_salt: str | None = None,
    password_hash: str | None = None,
) -> dict[str, Any] | None:
    if not is_enabled():
        return None

    _ensure_db_ready()

    u = str(username or "").strip().lower()
    r = str(role or "").strip().upper()
    if not u or not r:
        return None

    existing = get_ops_user_by_username(username=u)
    if isinstance(existing, dict) and int(existing.get("id") or 0) > 0:
        return update_ops_user(
            username=u,
            role=r,
            nome=nome,
            telefone=telefone,
            telegram=telegram,
            endereco=endereco,
            pix=pix,
            ativo=ativo,
            password_salt=password_salt,
            password_hash=password_hash,
        )

    if password_salt is None or password_hash is None:
        return None

    return create_ops_user(
        username=u,
        role=r,
        nome=nome,
        telefone=telefone,
        telegram=telegram,
        endereco=endereco,
        pix=pix,
        password_salt=password_salt,
        password_hash=password_hash,
    )


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def kds_ensure_order_row(*, solicitacao_id: str) -> None:
    if not is_enabled():
        return
    _ensure_db_ready()
    sid = str(solicitacao_id or "").strip()
    if not sid:
        return
    created = datetime.now().isoformat(timespec="seconds")
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO kds_orders(solicitacao_id, status, created_em)
                VALUES (%s, %s, %s)
                ON CONFLICT (solicitacao_id) DO NOTHING
                """,
                (sid, "AGUARDANDO", created),
            )


def kds_get_current_for_user(*, ops_user_id: int) -> dict[str, Any] | None:
    if not is_enabled():
        return None
    _ensure_db_ready()
    uid = int(ops_user_id)
    with _conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # 1) Seleção manual (sem iniciar preparo): se existir e ainda estiver AGUARDANDO, vira o "pedido atual"
            cur.execute(
                """
                SELECT k.*
                FROM kds_current_selection s
                JOIN kds_orders k ON k.solicitacao_id=s.solicitacao_id
                WHERE s.ops_user_id=%s
                  AND k.status='AGUARDANDO'
                ORDER BY s.selected_em DESC
                LIMIT 1
                """,
                (uid,),
            )
            sel = cur.fetchone()
            if sel:
                return dict(sel)

            cur.execute(
                """
                SELECT *
                FROM kds_orders
                WHERE status='EM_PREPARO' AND ops_user_id=%s
                ORDER BY started_em ASC NULLS LAST
                LIMIT 1
                """,
                (uid,),
            )
            row = cur.fetchone()
            if row:
                return dict(row)

            # IMPORTANTE: não selecionar automaticamente o próximo pedido.
            # O fluxo operacional do KDS pode exigir seleção manual (ex.: quando o operador conclui um pedido,
            # ele escolhe conscientemente o próximo na fila). Assim evitamos "auto-pegar" pedidos.
            return None


def kds_start_order(*, solicitacao_id: str, ops_user_id: int) -> None:
    if not is_enabled():
        return
    _ensure_db_ready()
    sid = str(solicitacao_id or "").strip()
    if not sid:
        return
    uid = int(ops_user_id)
    kds_ensure_order_row(solicitacao_id=sid)
    started = _now_iso()
    with _conn() as conn:
        with conn.cursor() as cur:
            # quando inicia preparo, a seleção manual perde sentido
            cur.execute("DELETE FROM kds_current_selection WHERE ops_user_id=%s", (uid,))
            cur.execute(
                """
                UPDATE kds_orders
                SET status='EM_PREPARO', started_em=%s, ops_user_id=%s
                WHERE solicitacao_id=%s
                """,
                (started, uid, sid),
            )


def kds_mark_done(*, solicitacao_id: str, ops_user_id: int) -> None:
    if not is_enabled():
        return
    _ensure_db_ready()
    sid = str(solicitacao_id or "").strip()
    if not sid:
        return
    uid = int(ops_user_id)
    kds_ensure_order_row(solicitacao_id=sid)
    done = _now_iso()
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM kds_current_selection WHERE ops_user_id=%s", (uid,))
            cur.execute(
                """
                UPDATE kds_orders
                SET status='PRONTO', done_em=%s, ops_user_id=%s
                WHERE solicitacao_id=%s
                """,
                (done, uid, sid),
            )


def kds_set_current_selection(*, ops_user_id: int, solicitacao_id: str) -> None:
    if not is_enabled():
        return
    _ensure_db_ready()
    uid = int(ops_user_id)
    sid = str(solicitacao_id or "").strip()
    if not uid or not sid:
        return
    selected = _now_iso()
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO kds_current_selection(ops_user_id, solicitacao_id, selected_em)
                VALUES (%s,%s,%s)
                ON CONFLICT (ops_user_id)
                DO UPDATE SET solicitacao_id=EXCLUDED.solicitacao_id, selected_em=EXCLUDED.selected_em
                """,
                (uid, sid, selected),
            )


def kds_clear_current_selection(*, ops_user_id: int) -> None:
    if not is_enabled():
        return
    _ensure_db_ready()
    uid = int(ops_user_id)
    if not uid:
        return
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM kds_current_selection WHERE ops_user_id=%s", (uid,))


def kds_stats_today() -> dict[str, int]:
    if not is_enabled():
        return {"pendentes": 0, "concluidos": 0}
    _ensure_db_ready()
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM kds_orders WHERE status IN ('AGUARDANDO','EM_PREPARO')")
            pend = int(cur.fetchone()[0] or 0)
            cur.execute("SELECT COUNT(*) FROM kds_orders WHERE status='PRONTO' AND done_em::date = CURRENT_DATE")
            done = int(cur.fetchone()[0] or 0)
            return {"pendentes": pend, "concluidos": done}


def kds_list_queue_ids(*, limit: int = 50) -> list[str]:
    if not is_enabled():
        return []
    _ensure_db_ready()
    lim = int(limit) if int(limit) > 0 else 50
    lim = min(lim, 200)
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT solicitacao_id
                FROM kds_orders
                WHERE status='AGUARDANDO'
                ORDER BY created_em ASC
                LIMIT %s
                """,
                (lim,),
            )
            return [str(r[0]) for r in (cur.fetchall() or []) if r and str(r[0] or "").strip()]


def kds_bump_queue_order(*, solicitacao_id: str) -> None:
    if not is_enabled():
        return
    _ensure_db_ready()
    sid = str(solicitacao_id or "").strip()
    if not sid:
        return
    bumped = _now_iso()
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE kds_orders
                SET created_em=%s
                WHERE solicitacao_id=%s AND status='AGUARDANDO'
                """,
                (bumped, sid),
            )


def logistica_list_ready_order_ids() -> list[str]:
    if not is_enabled():
        return []
    _ensure_db_ready()
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT k.solicitacao_id
                FROM kds_orders k
                WHERE k.status='PRONTO'
                  AND NOT EXISTS (
                    SELECT 1
                    FROM log_run_items i
                    JOIN log_runs r ON r.id=i.run_id
                    WHERE i.solicitacao_id=k.solicitacao_id
                      AND r.status IN ('MONTANDO','EM_ANDAMENTO')
                  )
                  AND NOT EXISTS (
                    SELECT 1
                    FROM log_run_items i2
                    WHERE i2.solicitacao_id=k.solicitacao_id
                      AND i2.delivered_em IS NOT NULL
                  )
                ORDER BY k.done_em ASC NULLS LAST
                LIMIT 200
                """
            )
            return [str(r[0]) for r in (cur.fetchall() or []) if r and str(r[0] or "").strip()]


def logistica_list_ready_orders() -> list[dict[str, Any]]:
    if not is_enabled():
        return []
    _ensure_db_ready()
    with _conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT
                    k.solicitacao_id,
                    COALESCE(f.flag,'') AS flag
                FROM kds_orders k
                LEFT JOIN log_order_flags f ON f.solicitacao_id=k.solicitacao_id
                WHERE k.status='PRONTO'
                  AND NOT EXISTS (
                    SELECT 1
                    FROM log_run_items i
                    JOIN log_runs r ON r.id=i.run_id
                    WHERE i.solicitacao_id=k.solicitacao_id
                      AND r.status IN ('MONTANDO','EM_ANDAMENTO')
                  )
                  AND NOT EXISTS (
                    SELECT 1
                    FROM log_run_items i2
                    WHERE i2.solicitacao_id=k.solicitacao_id
                      AND i2.delivered_em IS NOT NULL
                  )
                ORDER BY k.done_em ASC NULLS LAST
                LIMIT 200
                """
            )
            return [dict(r) for r in (cur.fetchall() or [])]


def logistica_flag_signal(*, ops_user_id: int, solicitacao_id: str, note: str | None = None) -> None:
    if not is_enabled():
        return
    _ensure_db_ready()
    uid = int(ops_user_id)
    sid = str(solicitacao_id or "").strip()
    if not sid:
        return
    now = _now_iso()
    nt = str(note or "").strip() or None
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO log_order_flags(solicitacao_id, flag, flagged_em, ops_user_id, note)
                VALUES (%s,'SINALIZADO',%s,%s,%s)
                ON CONFLICT (solicitacao_id)
                DO UPDATE SET flag='SINALIZADO', flagged_em=EXCLUDED.flagged_em, ops_user_id=EXCLUDED.ops_user_id, note=EXCLUDED.note
                """,
                (sid, now, uid or None, nt),
            )


def logistica_flag_clear(*, ops_user_id: int, solicitacao_id: str, note: str | None = None) -> None:
    if not is_enabled():
        return
    _ensure_db_ready()
    uid = int(ops_user_id)
    sid = str(solicitacao_id or "").strip()
    if not sid:
        return
    nt = str(note or "").strip() or None
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM log_order_flags WHERE solicitacao_id=%s", (sid,))
    logistica_event_add(ops_user_id=uid, solicitacao_id=sid, event="DESINALIZADO", note=nt)


def logistica_flags_get_map(*, solicitacao_ids: list[str]) -> dict[str, str]:
    if not is_enabled():
        return {}
    _ensure_db_ready()
    sids = [str(x or "").strip() for x in (solicitacao_ids or [])]
    sids = [x for x in sids if x]
    if not sids:
        return {}
    with _conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT solicitacao_id, COALESCE(flag,'') AS flag
                FROM log_order_flags
                WHERE solicitacao_id = ANY(%s)
                """,
                (sids,),
            )
            rows = cur.fetchall() or []
    out: dict[str, str] = {}
    for r in rows:
        if not isinstance(r, dict):
            continue
        sid = str(r.get("solicitacao_id") or "").strip()
        fl = str(r.get("flag") or "").strip().upper()
        if sid and fl:
            out[sid] = fl
    return out


def logistica_event_add(*, ops_user_id: int, solicitacao_id: str, event: str, note: str | None = None) -> None:
    if not is_enabled():
        return
    _ensure_db_ready()
    uid = int(ops_user_id)
    sid = str(solicitacao_id or "").strip()
    ev = str(event or "").strip().upper()
    if not sid or not ev:
        return
    now = _now_iso()
    nt = str(note or "").strip() or None
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO log_order_events(solicitacao_id, event, created_em, ops_user_id, note)
                VALUES (%s,%s,%s,%s,%s)
                """,
                (sid, ev, now, uid or None, nt),
            )


def logistica_cancel_definitivo(*, ops_user_id: int, solicitacao_id: str, note: str | None = None) -> None:
    if not is_enabled():
        return
    _ensure_db_ready()
    uid = int(ops_user_id)
    sid = str(solicitacao_id or "").strip()
    if not sid:
        return
    now = _now_iso()
    nt = str(note or "").strip() or None
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM log_run_items WHERE solicitacao_id=%s", (sid,))
            cur.execute("DELETE FROM log_order_flags WHERE solicitacao_id=%s", (sid,))
            cur.execute(
                """
                UPDATE kds_orders
                SET status='CANCELADO', done_em=%s
                WHERE solicitacao_id=%s
                """,
                (now, sid),
            )
    logistica_event_add(ops_user_id=uid, solicitacao_id=sid, event="CANCELADO", note=nt)


def logistica_get_or_create_draft_run(*, ops_user_id: int) -> dict[str, Any]:
    if not is_enabled():
        return {"items": []}
    _ensure_db_ready()
    uid = int(ops_user_id)
    with _conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # Preferir corrida ativa (EM_ANDAMENTO) sobre rascunho (MONTANDO).
            cur.execute(
                """
                SELECT * FROM log_runs
                WHERE ops_user_id=%s AND status IN ('EM_ANDAMENTO','MONTANDO')
                ORDER BY (status='EM_ANDAMENTO') DESC, created_em DESC
                LIMIT 1
                """,
                (uid,),
            )
            run = cur.fetchone()

            # Só cria uma nova corrida se o usuário não tiver nenhuma ativa/rascunho.
            if not run:
                now = _now_iso()
                cur.execute(
                    """
                    INSERT INTO log_runs(ops_user_id, status, created_em)
                    VALUES (%s,'MONTANDO',%s)
                    RETURNING *
                    """,
                    (uid, now),
                )
                run = cur.fetchone()

            run_id = int(run.get("id") or 0)
            cur.execute(
                """
                SELECT solicitacao_id, added_em, delivered_em
                FROM log_run_items
                WHERE run_id=%s
                ORDER BY added_em ASC
                """,
                (run_id,),
            )
            items = [dict(r) for r in (cur.fetchall() or [])]
            out = dict(run)
            out["items"] = items
            return out


def logistica_run_add_order(*, ops_user_id: int, solicitacao_id: str) -> dict[str, Any]:
    if not is_enabled():
        return {"items": []}
    _ensure_db_ready()
    uid = int(ops_user_id)
    sid = str(solicitacao_id or "").strip()
    if not sid:
        return logistica_get_or_create_draft_run(ops_user_id=uid)

    run = logistica_get_or_create_draft_run(ops_user_id=uid)
    run_id = int(run.get("id") or 0)
    run_status = str(run.get("status") or "").strip().upper()
    if run_status != "MONTANDO":
        raise RuntimeError("corrida_em_andamento")

    # Só aceita pedidos que estejam PRONTO no KDS.
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT status FROM kds_orders WHERE solicitacao_id=%s", (sid,))
            row = cur.fetchone()
            st = str(row[0] if row else "").strip().upper()
            if st != "PRONTO":
                raise RuntimeError("pedido_nao_pronto")

            cur.execute("SELECT flag FROM log_order_flags WHERE solicitacao_id=%s", (sid,))
            frow = cur.fetchone()
            fl = str(frow[0] if frow else "").strip().upper()
            if fl == "SINALIZADO":
                raise RuntimeError("pedido_sinalizado")

            # Impede o mesmo pedido em outra corrida ativa.
            cur.execute(
                """
                SELECT 1
                FROM log_run_items i
                JOIN log_runs r ON r.id=i.run_id
                WHERE i.solicitacao_id=%s
                  AND r.status IN ('MONTANDO','EM_ANDAMENTO')
                  AND r.ops_user_id <> %s
                LIMIT 1
                """,
                (sid, uid),
            )
            if cur.fetchone():
                raise RuntimeError("pedido_em_outra_corrida")

    added = _now_iso()
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO log_run_items(run_id, solicitacao_id, added_em)
                VALUES (%s,%s,%s)
                ON CONFLICT (run_id, solicitacao_id) DO NOTHING
                """,
                (run_id, sid, added),
            )
    return logistica_get_or_create_draft_run(ops_user_id=uid)


def logistica_run_new_draft(*, ops_user_id: int) -> dict[str, Any]:
    if not is_enabled():
        return {"items": []}
    _ensure_db_ready()
    uid = int(ops_user_id)
    now = _now_iso()
    with _conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # Não permite criar nova corrida se já existir uma em andamento.
            cur.execute(
                """
                SELECT id
                FROM log_runs
                WHERE ops_user_id=%s AND status='EM_ANDAMENTO'
                ORDER BY started_em DESC NULLS LAST
                LIMIT 1
                """,
                (uid,),
            )
            if cur.fetchone():
                raise RuntimeError("corrida_em_andamento")

            # Reutiliza a corrida MONTANDO mais recente, limpando os itens.
            cur.execute(
                """
                SELECT id
                FROM log_runs
                WHERE ops_user_id=%s AND status='MONTANDO'
                ORDER BY created_em DESC
                LIMIT 1
                """,
                (uid,),
            )
            row = cur.fetchone()
            if row and row.get("id"):
                run_id = int(row.get("id") or 0)
                cur.execute("DELETE FROM log_run_items WHERE run_id=%s", (run_id,))
                cur.execute(
                    "UPDATE log_runs SET created_em=%s, started_em=NULL, finished_em=NULL WHERE id=%s AND ops_user_id=%s",
                    (now, run_id, uid),
                )
            else:
                cur.execute(
                    """
                    INSERT INTO log_runs(ops_user_id, status, created_em)
                    VALUES (%s,'MONTANDO',%s)
                    RETURNING id
                    """,
                    (uid, now),
                )

    return logistica_get_or_create_draft_run(ops_user_id=uid)


def logistica_run_remove_order(*, ops_user_id: int, solicitacao_id: str) -> dict[str, Any]:
    if not is_enabled():
        return {"items": []}
    _ensure_db_ready()
    uid = int(ops_user_id)
    sid = str(solicitacao_id or "").strip()
    run = logistica_get_or_create_draft_run(ops_user_id=uid)
    run_id = int(run.get("id") or 0)
    run_status = str(run.get("status") or "").strip().upper()
    if not run_id or not sid:
        return run
    if run_status != "MONTANDO":
        raise RuntimeError("corrida_em_andamento_use_devolver")
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM log_run_items WHERE run_id=%s AND solicitacao_id=%s", (run_id, sid))
    return logistica_get_or_create_draft_run(ops_user_id=uid)


def logistica_run_return_order(*, ops_user_id: int, solicitacao_id: str) -> dict[str, Any]:
    if not is_enabled():
        return {"items": []}
    _ensure_db_ready()
    uid = int(ops_user_id)
    sid = str(solicitacao_id or "").strip()
    run = logistica_get_or_create_draft_run(ops_user_id=uid)
    run_id = int(run.get("id") or 0)
    run_status = str(run.get("status") or "").strip().upper()
    if not run_id or not sid:
        return run
    if run_status != "EM_ANDAMENTO":
        raise RuntimeError("corrida_nao_em_andamento")
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM log_run_items WHERE run_id=%s AND solicitacao_id=%s AND delivered_em IS NULL", (run_id, sid))

            # Se a corrida ficou vazia, finaliza automaticamente para destravar o fluxo
            # (principalmente quando o frontend não exibe botões de rodapé).
            cur.execute("SELECT COUNT(*) FROM log_run_items WHERE run_id=%s", (run_id,))
            remaining = int((cur.fetchone() or [0])[0] or 0)
            if remaining == 0:
                finished = _now_iso()
                cur.execute(
                    "UPDATE log_runs SET status='FINALIZADA', finished_em=%s WHERE id=%s AND ops_user_id=%s",
                    (finished, run_id, uid),
                )
    return logistica_get_or_create_draft_run(ops_user_id=uid)


def logistica_run_mark_delivered(*, ops_user_id: int, solicitacao_id: str) -> dict[str, Any]:
    if not is_enabled():
        return {"items": []}
    _ensure_db_ready()
    uid = int(ops_user_id)
    sid = str(solicitacao_id or "").strip()
    run = logistica_get_or_create_draft_run(ops_user_id=uid)
    run_id = int(run.get("id") or 0)
    run_status = str(run.get("status") or "").strip().upper()
    if not run_id or not sid:
        return run
    if run_status != "EM_ANDAMENTO":
        raise RuntimeError("corrida_nao_em_andamento")

    delivered = _now_iso()
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE log_run_items
                SET delivered_em=%s
                WHERE run_id=%s
                  AND solicitacao_id=%s
                  AND delivered_em IS NULL
                """,
                (delivered, run_id, sid),
            )
            if (cur.rowcount or 0) == 0:
                # Ou já estava entregue, ou não existe na corrida.
                raise RuntimeError("pedido_nao_encontrado_ou_ja_entregue")

    return logistica_get_or_create_draft_run(ops_user_id=uid)


def logistica_run_start(*, ops_user_id: int) -> dict[str, Any]:
    if not is_enabled():
        return {"items": []}
    _ensure_db_ready()
    uid = int(ops_user_id)
    run = logistica_get_or_create_draft_run(ops_user_id=uid)
    run_id = int(run.get("id") or 0)
    run_status = str(run.get("status") or "").strip().upper()
    if not run_id:
        return run
    if run_status != "MONTANDO":
        raise RuntimeError("corrida_em_andamento")
    items = run.get("items")
    if not isinstance(items, list) or len(items) == 0:
        raise RuntimeError("corrida_sem_pedidos")
    started = _now_iso()
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE log_runs SET status='EM_ANDAMENTO', started_em=%s WHERE id=%s AND ops_user_id=%s",
                (started, run_id, uid),
            )
    return logistica_get_or_create_draft_run(ops_user_id=uid)


def logistica_run_finish(*, ops_user_id: int) -> dict[str, Any]:
    if not is_enabled():
        raise RuntimeError("pg_disabled")
    _ensure_db_ready()
    uid = int(ops_user_id)
    run = logistica_get_or_create_draft_run(ops_user_id=uid)
    run_id = int(run.get("id") or 0)
    run_status = str(run.get("status") or "").strip().upper()
    if not run_id:
        return run
    if run_status != "EM_ANDAMENTO":
        raise RuntimeError("corrida_nao_iniciada")
    finished = _now_iso()
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE log_runs SET status='FINALIZADA', finished_em=%s WHERE id=%s AND ops_user_id=%s",
                (finished, run_id, uid),
            )
    return {"ok": True, "id": run_id}


def kds_list_done_periodo(*, ini: str, fim: str) -> list[dict[str, Any]]:
    if not is_enabled():
        return []
    _ensure_db_ready()
    ini_s = str(ini or "").strip()
    fim_s = str(fim or "").strip()
    if not ini_s or not fim_s:
        return []

    with _conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT
                    solicitacao_id,
                    ops_user_id,
                    u.username AS ops_username,
                    u.nome AS ops_nome,
                    status,
                    created_em,
                    started_em,
                    done_em,
                    EXTRACT(EPOCH FROM (done_em - started_em))::bigint AS preparo_seconds,
                    EXTRACT(EPOCH FROM (done_em - created_em))::bigint AS total_seconds
                FROM kds_orders k
                LEFT JOIN ops_users u ON u.id=k.ops_user_id
                WHERE status='PRONTO'
                  AND done_em >= %s::timestamptz
                  AND done_em < (%s::timestamptz + INTERVAL '1 day')
                ORDER BY done_em ASC
                """,
                (ini_s, fim_s),
            )
            return [dict(x) for x in (cur.fetchall() or [])]


def logistica_list_runs_periodo(*, ini: str, fim: str) -> list[dict[str, Any]]:
    if not is_enabled():
        return []
    _ensure_db_ready()
    ini_s = str(ini or "").strip()
    fim_s = str(fim or "").strip()
    if not ini_s or not fim_s:
        return []

    with _conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT
                    r.id,
                    r.ops_user_id,
                    u.username AS ops_username,
                    u.nome AS ops_nome,
                    r.status,
                    r.created_em,
                    r.started_em,
                    r.finished_em,
                    COUNT(i.solicitacao_id)::bigint AS itens,
                    EXTRACT(EPOCH FROM (r.finished_em - r.started_em))::bigint AS corrida_seconds
                FROM log_runs r
                LEFT JOIN ops_users u ON u.id=r.ops_user_id
                LEFT JOIN log_run_items i ON i.run_id=r.id
                WHERE r.status='FINALIZADA'
                  AND r.finished_em IS NOT NULL
                  AND r.finished_em >= %s::timestamptz
                  AND r.finished_em < (%s::timestamptz + INTERVAL '1 day')
                GROUP BY
                    r.id,
                    r.ops_user_id,
                    u.username,
                    u.nome,
                    r.status,
                    r.created_em,
                    r.started_em,
                    r.finished_em
                ORDER BY r.finished_em ASC
                """,
                (ini_s, fim_s),
            )
            return [dict(x) for x in (cur.fetchall() or [])]


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
