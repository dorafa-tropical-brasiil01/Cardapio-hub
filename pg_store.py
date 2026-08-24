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
                    sinalizado_em TIMESTAMPTZ,
                    impressao_solicitada_em TIMESTAMPTZ,
                    recusado_em TIMESTAMPTZ,
                    motivo_recusa TEXT,
                    nota_recusa TEXT,
                    entregue_em TIMESTAMPTZ,
                    ops_user_id BIGINT
                )
                """
            )
            cur.execute("ALTER TABLE kds_orders ADD COLUMN IF NOT EXISTS sinalizado_em TIMESTAMPTZ")
            cur.execute("ALTER TABLE kds_orders ADD COLUMN IF NOT EXISTS impressao_solicitada_em TIMESTAMPTZ")
            cur.execute("ALTER TABLE kds_orders ADD COLUMN IF NOT EXISTS recusado_em TIMESTAMPTZ")
            cur.execute("ALTER TABLE kds_orders ADD COLUMN IF NOT EXISTS motivo_recusa TEXT")
            cur.execute("ALTER TABLE kds_orders ADD COLUMN IF NOT EXISTS nota_recusa TEXT")
            cur.execute("ALTER TABLE kds_orders ADD COLUMN IF NOT EXISTS entregue_em TIMESTAMPTZ")
            cur.execute("UPDATE kds_orders SET status = 'NOVO' WHERE status = 'AGUARDANDO'")
            # Migracao: pedidos com entregue_em preenchido mas status SINALIZADO -> ENTREGUE
            cur.execute("UPDATE kds_orders SET status = 'ENTREGUE' WHERE entregue_em IS NOT NULL AND status = 'SINALIZADO'")
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

            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS logistica_integracoes (
                    id BIGSERIAL PRIMARY KEY,
                    solicitacao_id TEXT NOT NULL,
                    evento TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'PENDENTE',
                    tentativas INTEGER NOT NULL DEFAULT 0,
                    criado_em TIMESTAMPTZ NOT NULL,
                    proxima_tentativa_em TIMESTAMPTZ NOT NULL,
                    enviado_em TIMESTAMPTZ,
                    ultimo_erro TEXT,
                    protocolo_externo TEXT,
                    payload_json JSONB NOT NULL,
                    resposta_json JSONB,
                    UNIQUE (solicitacao_id, evento)
                )
                """
            )
            cur.execute("CREATE INDEX IF NOT EXISTS idx_logistica_integracoes_status ON logistica_integracoes(status, proxima_tentativa_em)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_logistica_integracoes_solicitacao ON logistica_integracoes(solicitacao_id)")

            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS logistica_webhooks_recebidos (
                    id BIGSERIAL PRIMARY KEY,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    solicitacao_id TEXT NOT NULL,
                    evento TEXT NOT NULL,
                    status_externo TEXT NOT NULL,
                    payload_json JSONB NOT NULL,
                    recebido_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            cur.execute("CREATE INDEX IF NOT EXISTS idx_logistica_webhooks_solicitacao ON logistica_webhooks_recebidos(solicitacao_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_logistica_webhooks_evento ON logistica_webhooks_recebidos(evento)")

            # ------------------------------------------------------------------
            # PAGAMENTOS EXTERNOS — Fase 1 (PIX via PagBank API Order)
            #
            # Tabela central de pagamentos eletrônicos processados por um PSP.
            # O domínio (PaymentService) opera sobre esta tabela.
            # O adapter (PagBankAdapter) traduz entre o PSP e esta tabela.
            #
            # Regras canônicas (Contrato 0D):
            #   - status: PENDENTE → APROVADO / EXPIRADO / RECUSADO / CANCELADO
            #   - EXPIRADO → APROVADO é permitido (PIX pago após expiração)
            #   - Idempotência via last_event_id (não-regressão de estados terminais)
            #   - claim: PDV reivindica o pagamento (claimed_by_pdv_id)
            #   - application: PDV aplica à venda (applied_sale_id + applied_sale_payment_id)
            #
            # Nenhum campo específico de PIX ou PagBank existe aqui.
            # ------------------------------------------------------------------
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS external_payments (
                    id TEXT PRIMARY KEY,
                    provider_id TEXT NOT NULL,
                    provider_transaction_id TEXT NOT NULL,
                    payment_method TEXT NOT NULL,
                    amount REAL NOT NULL,
                    currency TEXT NOT NULL DEFAULT 'BRL',
                    status TEXT NOT NULL DEFAULT 'PENDENTE',
                    reference_id TEXT,
                    qr_code_payload TEXT,
                    qr_code_image_base64 TEXT,
                    qr_code_image_url TEXT,
                    expires_at TIMESTAMPTZ,
                    last_event_id TEXT,
                    last_event_at TIMESTAMPTZ,
                    claimed_by_pdv_id TEXT,
                    claimed_at TIMESTAMPTZ,
                    applied_sale_id INTEGER,
                    applied_sale_payment_id INTEGER,
                    applied_at TIMESTAMPTZ,
                    metadata JSONB,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_external_payments_status ON external_payments(status)"
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_external_payments_provider_tx ON external_payments(provider_id, provider_transaction_id)"
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_external_payments_reference ON external_payments(reference_id)"
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_external_payments_claimed ON external_payments(claimed_by_pdv_id)"
            )

            # ------------------------------------------------------------------
            # CONFIGURAÇÕES DO PSP
            #
            # Metadados não-secretos do provedor (endpoint base, default expiration).
            # Credenciais secretas (token, webhook_token) ficam em variáveis de
            # ambiente (Decisão 6), NÃO nesta tabela.
            # ------------------------------------------------------------------
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS payment_provider_settings (
                    provider_id TEXT PRIMARY KEY,
                    display_name TEXT NOT NULL,
                    base_url TEXT NOT NULL,
                    environment TEXT NOT NULL DEFAULT 'SANDBOX',
                    default_expires_in_seconds INTEGER,
                    webhook_url TEXT,
                    config_json JSONB,
                    is_active BOOLEAN NOT NULL DEFAULT TRUE,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            # Adicionar coluna environment se não existir (migração idempotente)
            try:
                cur.execute(
                    "ALTER TABLE payment_provider_settings ADD COLUMN IF NOT EXISTS environment TEXT NOT NULL DEFAULT 'SANDBOX'"
                )
            except Exception:
                pass

            # ------------------------------------------------------------------
            # CREDENCIAIS DE PROVEDORES (secretas, criptografadas)
            #
            # Tabela separada de payment_provider_settings porque:
            #   - settings = metadados não-secretos (URL, environment, is_active)
            #   - credentials = segredos criptografados em nível de aplicação
            #
            # O token é criptografado com Fernet no PDV antes de enviar.
            # A chave Fernet é derivada do MachineGuid da máquina (Windows)
            # + um salt de aplicação, garantindo que credenciais só podem ser
            # descriptografadas na mesma máquina que as criptografou.
            #
            # NUNCA logar o valor de encrypted_value.
            # ------------------------------------------------------------------
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS payment_provider_credentials (
                    id BIGSERIAL PRIMARY KEY,
                    provider_id TEXT NOT NULL,
                    credential_key TEXT NOT NULL,
                    encrypted_value TEXT NOT NULL,
                    hint TEXT,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    UNIQUE (provider_id, credential_key)
                )
                """
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_provider_credentials_provider ON payment_provider_credentials(provider_id)"
            )

            # ------------------------------------------------------------------
            # IDEMPOTÊNCIA DE PEDIDOS PÚBLICOS
            #
            # Protege contra pedido duplicado quando o cliente reenvia a mesma
            # requisição (toque duplo, retry de rede, refresh). A chave é gerada
            # pelo navegador e é OPCIONAL: sem ela, o fluxo segue normal.
            #
            # request_hash permite detectar reuso de chave com corpo diferente,
            # que é erro do cliente e não deve devolver a resposta antiga.
            # ------------------------------------------------------------------
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS public_pedidos_idempotency (
                    idempotency_key TEXT NOT NULL,
                    scope TEXT NOT NULL,
                    request_hash TEXT NOT NULL,
                    solicitacao_id TEXT,
                    response_json JSONB NOT NULL,
                    status_code INTEGER NOT NULL DEFAULT 200,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    expires_at TIMESTAMPTZ NOT NULL,
                    PRIMARY KEY (scope, idempotency_key)
                )
                """
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_public_pedidos_idem_expires ON public_pedidos_idempotency(expires_at)"
            )

            # ------------------------------------------------------------------
            # ZONAS DE COBERTURA PARA TAXA DE ENTREGA
            #
            # Zonas independentes do Cardápio (espelham a ideia da REMO mas
            # com taxas próprias). O operador cadastra no PDV, salva aqui,
            # e o cálculo do checkout usa max(taxa_zona, taxa_distancia).
            # ------------------------------------------------------------------
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS taxa_entrega_zonas (
                    id BIGSERIAL PRIMARY KEY,
                    nome TEXT NOT NULL,
                    cidade TEXT,
                    taxa NUMERIC(12,2) NOT NULL DEFAULT 0,
                    gratis BOOLEAN NOT NULL DEFAULT FALSE,
                    poligono JSONB,
                    cor TEXT DEFAULT '#00d4aa',
                    ativo BOOLEAN NOT NULL DEFAULT TRUE,
                    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            cur.execute("CREATE INDEX IF NOT EXISTS idx_taxa_entrega_zonas_ativo ON taxa_entrega_zonas(ativo)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_taxa_entrega_zonas_cidade ON taxa_entrega_zonas(cidade)")


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
    created = _now_iso()
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO kds_orders(solicitacao_id, status, created_em)
                VALUES (%s, %s, %s)
                ON CONFLICT (solicitacao_id) DO NOTHING
                """,
                (sid, "NOVO", created),
            )


def kds_get_current_for_user(*, ops_user_id: int) -> dict[str, Any] | None:
    if not is_enabled():
        return None
    _ensure_db_ready()
    uid = int(ops_user_id)
    with _conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # 1) Seleção manual (sem iniciar preparo): se existir e ainda estiver NOVO, vira o "pedido atual"
            cur.execute(
                """
                SELECT k.*
                FROM kds_current_selection s
                JOIN kds_orders k ON k.solicitacao_id=s.solicitacao_id
                WHERE s.ops_user_id=%s
                  AND k.status='NOVO'
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


def kds_aceitar_pedido(
    *,
    solicitacao_id: str,
    ops_user_id: int,
    impressao_solicitada_em: str | None = None,
) -> None:
    """Transiciona NOVO -> EM_PREPARO, registrando início do preparo e solicitação de impressão."""
    if not is_enabled():
        return
    _ensure_db_ready()
    sid = str(solicitacao_id or "").strip()
    if not sid:
        return
    uid = int(ops_user_id)
    kds_ensure_order_row(solicitacao_id=sid)
    started = _now_iso()
    impressao = impressao_solicitada_em or started
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM kds_current_selection WHERE ops_user_id=%s", (uid,))
            cur.execute(
                """
                UPDATE kds_orders
                SET status='EM_PREPARO',
                    started_em=%s,
                    impressao_solicitada_em=%s,
                    ops_user_id=%s
                WHERE solicitacao_id=%s AND status='NOVO'
                """,
                (started, impressao, uid, sid),
            )


def kds_start_order(*, solicitacao_id: str, ops_user_id: int) -> None:
    """Compatibilidade com chamadas antigas: equivale a aceitar sem passar timestamp."""
    kds_aceitar_pedido(solicitacao_id=solicitacao_id, ops_user_id=ops_user_id)


def kds_marcar_pronto(*, solicitacao_id: str, ops_user_id: int) -> None:
    """Transiciona EM_PREPARO -> PRONTO."""
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
                WHERE solicitacao_id=%s AND status='EM_PREPARO'
                """,
                (done, uid, sid),
            )


def kds_mark_done(*, solicitacao_id: str, ops_user_id: int) -> None:
    """Compatibilidade com chamadas antigas: equivale a marcar como pronto."""
    kds_marcar_pronto(solicitacao_id=solicitacao_id, ops_user_id=ops_user_id)


def kds_marcar_sinalizado(
    *,
    solicitacao_id: str,
    ops_user_id: int,
) -> None:
    """Transiciona PRONTO -> SINALIZADO."""
    if not is_enabled():
        return
    _ensure_db_ready()
    sid = str(solicitacao_id or "").strip()
    if not sid:
        return
    uid = int(ops_user_id)
    kds_ensure_order_row(solicitacao_id=sid)
    sinalizado = _now_iso()
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM kds_current_selection WHERE ops_user_id=%s", (uid,))
            cur.execute(
                """
                UPDATE kds_orders
                SET status='SINALIZADO', sinalizado_em=%s, ops_user_id=%s
                WHERE solicitacao_id=%s AND status='PRONTO'
                """,
                (sinalizado, uid, sid),
            )


def kds_recusar_pedido(
    *,
    solicitacao_id: str,
    ops_user_id: int,
    motivo_recusa: str,
    nota_recusa: str | None = None,
) -> None:
    """Transiciona NOVO -> RECUSADO."""
    if not is_enabled():
        return
    _ensure_db_ready()
    sid = str(solicitacao_id or "").strip()
    if not sid:
        return
    uid = int(ops_user_id)
    kds_ensure_order_row(solicitacao_id=sid)
    recusado = _now_iso()
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM kds_current_selection WHERE ops_user_id=%s", (uid,))
            cur.execute(
                """
                UPDATE kds_orders
                SET status='RECUSADO',
                    recusado_em=%s,
                    motivo_recusa=%s,
                    nota_recusa=%s,
                    ops_user_id=%s
                WHERE solicitacao_id=%s AND status='NOVO'
                """,
                (recusado, motivo_recusa, nota_recusa or None, uid, sid),
            )


def kds_get_status(*, solicitacao_id: str) -> str | None:
    """
    Consulta o status de um pedido no KDS pelo solicitacao_id.
    Retorna o status (NOVO, EM_PREPARO, PRONTO, SINALIZADO, RECUSADO) ou None se não encontrado.
    """
    if not is_enabled():
        return None
    _ensure_db_ready()
    sid = str(solicitacao_id or "").strip()
    if not sid:
        return None
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT status FROM kds_orders WHERE solicitacao_id=%s", (sid,))
            row = cur.fetchone()
            if row:
                return str(row[0] if row else "").strip().upper() or None
    return None


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
            cur.execute("SELECT COUNT(*) FROM kds_orders WHERE status IN ('NOVO','EM_PREPARO')")
            pend = int(cur.fetchone()[0] or 0)
            cur.execute("SELECT COUNT(*) FROM kds_orders WHERE status='PRONTO' AND done_em::date = CURRENT_DATE")
            prontos = int(cur.fetchone()[0] or 0)
            cur.execute("SELECT COUNT(*) FROM kds_orders WHERE status='SINALIZADO' AND sinalizado_em::date = CURRENT_DATE")
            sinalizados = int(cur.fetchone()[0] or 0)
            return {"pendentes": pend, "prontos": prontos, "sinalizados": sinalizados}


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
                WHERE status='NOVO'
                ORDER BY created_em ASC
                LIMIT %s
                """,
                (lim,),
            )
            return [str(r[0]) for r in (cur.fetchall() or []) if r and str(r[0] or "").strip()]


def kds_list_queue_with_status(*, limit: int = 50) -> list[dict[str, Any]]:
    if not is_enabled():
        return []
    _ensure_db_ready()
    lim = int(limit) if int(limit) > 0 else 50
    lim = min(lim, 200)
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT k.solicitacao_id, k.status, k.created_em, k.started_em, k.done_em, k.sinalizado_em, k.impressao_solicitada_em, k.recusado_em, k.motivo_recusa, k.nota_recusa, k.ops_user_id
                FROM kds_orders k
                WHERE k.status='NOVO'
                ORDER BY k.created_em ASC
                LIMIT %s
                """,
                (lim,),
            )
            rows = cur.fetchall() or []
            return [
                {
                    "solicitacao_id": str(r[0]),
                    "status": str(r[1]),
                    "created_em": r[2],
                    "started_em": r[3],
                    "done_em": r[4],
                    "sinalizado_em": r[5],
                    "impressao_solicitada_em": r[6],
                    "recusado_em": r[7],
                    "motivo_recusa": r[8],
                    "nota_recusa": r[9],
                    "ops_user_id": r[10],
                }
                for r in rows
                if r and str(r[0] or "").strip()
            ]


def kds_list_preparing_ids(*, limit: int = 50) -> list[str]:
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
                WHERE status='EM_PREPARO'
                ORDER BY started_em ASC
                LIMIT %s
                """,
                (lim,),
            )
            return [str(r[0]) for r in (cur.fetchall() or []) if r and str(r[0] or "").strip()]


def kds_list_preparing_with_status(*, limit: int = 50) -> list[dict[str, Any]]:
    if not is_enabled():
        return []
    _ensure_db_ready()
    lim = int(limit) if int(limit) > 0 else 50
    lim = min(lim, 200)
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT k.solicitacao_id, k.status, k.created_em, k.started_em, k.done_em, k.sinalizado_em, k.impressao_solicitada_em, k.recusado_em, k.motivo_recusa, k.nota_recusa, k.ops_user_id
                FROM kds_orders k
                WHERE k.status='EM_PREPARO'
                ORDER BY k.started_em ASC
                LIMIT %s
                """,
                (lim,),
            )
            rows = cur.fetchall() or []
            return [
                {
                    "solicitacao_id": str(r[0]),
                    "status": str(r[1]),
                    "created_em": r[2],
                    "started_em": r[3],
                    "done_em": r[4],
                    "sinalizado_em": r[5],
                    "impressao_solicitada_em": r[6],
                    "recusado_em": r[7],
                    "motivo_recusa": r[8],
                    "nota_recusa": r[9],
                    "ops_user_id": r[10],
                }
                for r in rows
                if r and str(r[0] or "").strip()
            ]


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
                WHERE solicitacao_id=%s AND status='NOVO'
                """,
                (bumped, sid),
            )


def _kds_list_by_status(*, status: str, order_by: str, limit: int = 50) -> list[dict[str, Any]]:
    if not is_enabled():
        return []
    _ensure_db_ready()
    lim = int(limit) if int(limit) > 0 else 50
    lim = min(lim, 200)
    st = str(status or "").strip()
    allowed_order_by = {
        "created_em": "created_em",
        "started_em": "started_em",
        "done_em": "done_em",
        "sinalizado_em": "sinalizado_em",
        "recusado_em": "recusado_em",
        "entregue_em": "entregue_em",
    }
    ob = allowed_order_by.get(order_by, "created_em")
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT k.solicitacao_id, k.status, k.created_em, k.started_em, k.done_em, k.sinalizado_em, k.impressao_solicitada_em, k.recusado_em, k.motivo_recusa, k.nota_recusa, k.ops_user_id
                FROM kds_orders k
                WHERE k.status=%s
                ORDER BY k.{ob} ASC
                LIMIT %s
                """,
                (st, lim),
            )
            rows = cur.fetchall() or []
            return [
                {
                    "solicitacao_id": str(r[0]),
                    "status": str(r[1]),
                    "created_em": r[2],
                    "started_em": r[3],
                    "done_em": r[4],
                    "sinalizado_em": r[5],
                    "impressao_solicitada_em": r[6],
                    "recusado_em": r[7],
                    "motivo_recusa": r[8],
                    "nota_recusa": r[9],
                    "ops_user_id": r[10],
                }
                for r in rows
                if r and str(r[0] or "").strip()
            ]


def kds_list_prontos(*, limit: int = 50) -> list[dict[str, Any]]:
    return _kds_list_by_status(status="PRONTO", order_by="done_em", limit=limit)


def kds_list_sinalizados(*, limit: int = 50) -> list[dict[str, Any]]:
    return _kds_list_by_status(status="SINALIZADO", order_by="sinalizado_em", limit=limit)


def kds_list_entregues(*, limit: int = 50) -> list[dict[str, Any]]:
    return _kds_list_by_status(status="ENTREGUE", order_by="entregue_em", limit=limit)


def kds_list_recusados(*, limit: int = 50) -> list[dict[str, Any]]:
    return _kds_list_by_status(status="RECUSADO", order_by="recusado_em", limit=limit)


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
                JOIN cardapio_solicitacoes s ON s.id = k.solicitacao_id
                WHERE k.status='PRONTO'
                  AND s.record->>'tipo_entrega' = 'DELIVERY'
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
                JOIN cardapio_solicitacoes s ON s.id = k.solicitacao_id
                LEFT JOIN log_order_flags f ON f.solicitacao_id=k.solicitacao_id
                WHERE k.status='PRONTO'
                  AND s.record->>'tipo_entrega' = 'DELIVERY'
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


# ------------------------------------------------------------------
# INTEGRAÇÃO COM CENTRAL LOGÍSTICA EXTERNA
# ------------------------------------------------------------------


def logistica_integracao_criar(
    *,
    solicitacao_id: str,
    evento: str,
    payload_json: dict[str, Any],
) -> dict[str, Any]:
    """Cria um registro PENDENTE na fila de integração."""
    if not is_enabled():
        raise RuntimeError("pg_disabled")
    _ensure_db_ready()
    sid = str(solicitacao_id or "").strip()
    ev = str(evento or "").strip().upper()
    if not sid or not ev:
        raise RuntimeError("dados_invalidos")
    now = _now_iso()
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO logistica_integracoes(
                    solicitacao_id, evento, status, tentativas, criado_em,
                    proxima_tentativa_em, payload_json
                )
                VALUES (%s, %s, 'PENDENTE', 0, %s, %s, %s)
                ON CONFLICT (solicitacao_id, evento)
                DO UPDATE SET
                    payload_json = EXCLUDED.payload_json,
                    status = CASE
                        WHEN logistica_integracoes.status = 'ENVIADO' THEN 'ENVIADO'
                        ELSE logistica_integracoes.status
                    END
                RETURNING id
                """,
                (sid, ev, now, now, psycopg2.extras.Json(payload_json)),
            )
            row = cur.fetchone()
            if not row:
                raise RuntimeError("falha_ao_criar_integracao")
            return {"ok": True, "id": int(row[0])}


def logistica_integracao_pegar_proximo_pendente(
    *,
    max_tentativas: int = 3,
    for_update: bool = True,
) -> dict[str, Any] | None:
    """Pega o próximo registro PENDENTE pronto para envio."""
    if not is_enabled():
        return None
    _ensure_db_ready()
    with _conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            query = """
                SELECT *
                FROM logistica_integracoes
                WHERE status = 'PENDENTE'
                  AND tentativas < %s
                  AND proxima_tentativa_em <= %s
                ORDER BY proxima_tentativa_em ASC
            """
            if for_update:
                query += " FOR UPDATE SKIP LOCKED"
            cur.execute(query, (max_tentativas, _now_iso()))
            row = cur.fetchone()
            return dict(row) if row else None


def logistica_integracao_marcar_enviando(*, integracao_id: int) -> None:
    if not is_enabled():
        return
    _ensure_db_ready()
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE logistica_integracoes
                SET status = 'ENVIANDO', tentativas = tentativas + 1
                WHERE id = %s AND status = 'PENDENTE'
                """,
                (int(integracao_id),),
            )


def logistica_integracao_marcar_enviado(
    *,
    integracao_id: int,
    protocolo_externo: str | None = None,
    resposta_json: dict[str, Any] | None = None,
) -> None:
    if not is_enabled():
        return
    _ensure_db_ready()
    now = _now_iso()
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE logistica_integracoes
                SET status = 'ENVIADO',
                    enviado_em = %s,
                    protocolo_externo = %s,
                    resposta_json = %s,
                    ultimo_erro = NULL
                WHERE id = %s
                """,
                (now, protocolo_externo or None, psycopg2.extras.Json(resposta_json) if resposta_json else None, int(integracao_id)),
            )


def logistica_integracao_marcar_erro(
    *,
    integracao_id: int,
    ultimo_erro: str,
    proxima_tentativa_em: str | None = None,
    max_tentativas: int = 3,
) -> None:
    if not is_enabled():
        return
    _ensure_db_ready()
    with _conn() as conn:
        with conn.cursor() as cur:
            if proxima_tentativa_em:
                cur.execute(
                    """
                    UPDATE logistica_integracoes
                    SET status = 'PENDENTE',
                        ultimo_erro = %s,
                        proxima_tentativa_em = %s
                    WHERE id = %s
                    """,
                    (ultimo_erro, proxima_tentativa_em, int(integracao_id)),
                )
            else:
                cur.execute(
                    """
                    UPDATE logistica_integracoes
                    SET status = 'ERRO', ultimo_erro = %s
                    WHERE id = %s
                    """,
                    (ultimo_erro, int(integracao_id)),
                )


def logistica_integracao_reprocessar(*, integracao_id: int) -> None:
    """Volta um registro ERRO para PENDENTE para nova tentativa."""
    if not is_enabled():
        return
    _ensure_db_ready()
    now = _now_iso()
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE logistica_integracoes
                SET status = 'PENDENTE',
                    tentativas = 0,
                    ultimo_erro = NULL,
                    proxima_tentativa_em = %s
                WHERE id = %s AND status = 'ERRO'
                """,
                (now, int(integracao_id)),
            )


def logistica_integracao_listar_pendentes(*, limit: int = 100) -> list[dict[str, Any]]:
    if not is_enabled():
        return []
    _ensure_db_ready()
    lim = int(limit) if int(limit) > 0 else 100
    with _conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT *
                FROM logistica_integracoes
                WHERE status IN ('PENDENTE', 'ENVIANDO', 'ERRO')
                ORDER BY criado_em DESC
                LIMIT %s
                """,
                (lim,),
            )
            return [dict(r) for r in (cur.fetchall() or [])]


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


def get_solicitacao_by_access_token(*, access_token: str) -> dict[str, Any] | None:
    """
    Localiza um pedido pelo access_token público.
    Retorna o record completo do pedido ou None se não encontrado.
    """
    if not is_enabled():
        return None

    tok = str(access_token or "").strip()
    if not tok:
        return None

    _ensure_db_ready()

    with _conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT record FROM cardapio_solicitacoes WHERE record->>'access_token' = %s",
                (tok,),
            )
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


def calcular_status_publico(*, solicitacao_id: str) -> dict[str, Any]:
    """
    Calcula o status público de um pedido com base nos estados operacionais.

    Regras:
    - DELIVERY: ENVIADO -> ACEITO -> PREPARANDO -> PRONTO -> EM_ENTREGA -> ENTREGUE
    - RETIRADA: ENVIADO -> ACEITO -> PREPARANDO -> PRONTO (termina aqui)

    Para DELIVERY, ENTREGUE depende de log_run_items.delivered_em IS NOT NULL.
    Para RETIRADA, o fluxo termina em PRONTO (não existe evento de retirada física).
    """
    if not is_enabled():
        return {"status_publico": "DESCONHECIDO", "finalizado": False}

    sid = str(solicitacao_id or "").strip()
    if not sid:
        return {"status_publico": "DESCONHECIDO", "finalizado": False}

    _ensure_db_ready()

    # Obter o pedido
    rec = get_solicitacao(solicitacao_id=sid)
    if not isinstance(rec, dict):
        return {"status_publico": "DESCONHECIDO", "finalizado": False}

    # Obter tipo_entrega
    tipo_entrega = str(rec.get("tipo_entrega") or "").strip().upper()
    status_cardapio = str(rec.get("status") or "").strip().upper()

    # Obter status do KDS
    kds_status = None
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT status FROM kds_orders WHERE solicitacao_id=%s", (sid,))
            row = cur.fetchone()
            if row:
                kds_status = str(row[0] if row else "").strip().upper()

    # Aplicar regras por tipo de entrega
    if tipo_entrega == "DELIVERY":
        # REGRA 1: ENTREGUE (se delivered_em existe)
        with _conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT delivered_em
                    FROM log_run_items
                    WHERE solicitacao_id=%s
                      AND delivered_em IS NOT NULL
                    LIMIT 1
                    """,
                    (sid,),
                )
                if cur.fetchone():
                    return {
                        "status_publico": "ENTREGUE",
                        "finalizado": True,
                        "atualizado_em": _now_iso(),
                    }

        # REGRA 2: EM_ENTREGA (se corrida está EM_ANDAMENTO)
        with _conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT r.status
                    FROM log_runs r
                    JOIN log_run_items i ON i.run_id = r.id
                    WHERE i.solicitacao_id=%s
                      AND r.status = 'EM_ANDAMENTO'
                    LIMIT 1
                    """,
                    (sid,),
                )
                if cur.fetchone():
                    return {
                        "status_publico": "EM_ENTREGA",
                        "finalizado": False,
                        "atualizado_em": _now_iso(),
                    }

        # REGRA 3: PRONTO
        if kds_status == "PRONTO":
            return {
                "status_publico": "PRONTO",
                "finalizado": False,
                "atualizado_em": _now_iso(),
            }

        # REGRA 4: PREPARANDO
        if kds_status == "EM_PREPARO":
            return {
                "status_publico": "PREPARANDO",
                "finalizado": False,
                "atualizado_em": _now_iso(),
            }

        # REGRA 5: ACEITO
        if status_cardapio == "EM_ATENDIMENTO":
            return {
                "status_publico": "ACEITO",
                "finalizado": False,
                "atualizado_em": _now_iso(),
            }

        # REGRA 6: ENVIADO (padrão)
        return {
            "status_publico": "ENVIADO",
            "finalizado": False,
            "atualizado_em": _now_iso(),
        }

    elif tipo_entrega == "RETIRADA":
        # REGRA 1: PRONTO (estado final para RETIRADA nesta versão)
        if kds_status == "PRONTO":
            return {
                "status_publico": "PRONTO",
                "finalizado": False,  # NÃO é finalizado fisicamente
                "atualizado_em": _now_iso(),
            }

        # REGRA 2: PREPARANDO
        if kds_status == "EM_PREPARO":
            return {
                "status_publico": "PREPARANDO",
                "finalizado": False,
                "atualizado_em": _now_iso(),
            }

        # REGRA 3: ACEITO
        if status_cardapio == "EM_ATENDIMENTO":
            return {
                "status_publico": "ACEITO",
                "finalizado": False,
                "atualizado_em": _now_iso(),
            }

        # REGRA 4: ENVIADO (padrão)
        return {
            "status_publico": "ENVIADO",
            "finalizado": False,
            "atualizado_em": _now_iso(),
        }

    # Tipo de entrega não reconhecido
    return {
        "status_publico": "DESCONHECIDO",
        "finalizado": False,
        "atualizado_em": _now_iso(),
    }


def kds_marcar_entregue(*, solicitacao_id: str, ops_user_id: int | None = None) -> None:
    """Transiciona pedido KDS para ENTREGUE quando a Central confirma entrega."""
    if not is_enabled():
        return
    _ensure_db_ready()
    sid = str(solicitacao_id or "").strip()
    if not sid:
        return
    uid = int(ops_user_id) if ops_user_id is not None else None
    entregue = _now_iso()
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE kds_orders
                SET status='ENTREGUE', entregue_em=%s, ops_user_id=COALESCE(%s, ops_user_id)
                WHERE solicitacao_id=%s AND entregue_em IS NULL
                """,
                (entregue, uid, sid),
            )


def logistica_webhook_receber(
    *,
    idempotency_key: str,
    solicitacao_id: str,
    evento: str,
    status_externo: str,
    payload: dict[str, Any],
) -> bool:
    """
    Registra um webhook recebido da Central Logística.
    Retorna True se foi inserido (novo), False se idempotency_key já existia.
    """
    if not is_enabled():
        return False
    _ensure_db_ready()
    sid = str(solicitacao_id or "").strip()
    key = str(idempotency_key or "").strip()
    ev = str(evento or "").strip().upper()
    st = str(status_externo or "").strip().upper()
    if not sid or not key or not ev or not st:
        raise ValueError("dados_incompletos")
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO logistica_webhooks_recebidos
                    (idempotency_key, solicitacao_id, evento, status_externo, payload_json)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (idempotency_key) DO NOTHING
                """,
                (key, sid, ev, st, psycopg2.extras.Json(payload)),
            )
            return cur.rowcount > 0


# ---------------------------------------------------------------------------
# ZONAS DE COBERTURA (taxa_entrega_zonas) — CRUD
# ---------------------------------------------------------------------------

def list_taxa_entrega_zonas(*, ativo_only: bool = True) -> list[dict[str, Any]]:
    if not is_enabled():
        return []
    _ensure_db_ready()
    with _conn() as conn:
        with conn.cursor() as cur:
            if ativo_only:
                cur.execute(
                    "SELECT id, nome, cidade, taxa, gratis, poligono, cor, ativo, criado_em, atualizado_em "
                    "FROM taxa_entrega_zonas WHERE ativo = TRUE ORDER BY cidade, taxa ASC"
                )
            else:
                cur.execute(
                    "SELECT id, nome, cidade, taxa, gratis, poligono, cor, ativo, criado_em, atualizado_em "
                    "FROM taxa_entrega_zonas ORDER BY ativo DESC, cidade, taxa ASC"
                )
            rows = cur.fetchall()
    out: list[dict[str, Any]] = []
    for r in rows:
        poligono = r[5]
        if isinstance(poligono, str):
            try:
                import json as _json
                poligono = _json.loads(poligono)
            except Exception:
                poligono = None
        out.append({
            "id": r[0],
            "nome": r[1],
            "cidade": r[2],
            "taxa": float(r[3] or 0),
            "gratis": bool(r[4]),
            "poligono": poligono,
            "cor": r[6] or "#00d4aa",
            "ativo": bool(r[7]),
            "criado_em": str(r[8]) if r[8] else None,
            "atualizado_em": str(r[9]) if r[9] else None,
        })
    return out


def create_taxa_entrega_zona(
    *,
    nome: str,
    cidade: str | None = None,
    taxa: float = 0,
    gratis: bool = False,
    poligono: list | None = None,
    cor: str = "#00d4aa",
) -> dict[str, Any] | None:
    if not is_enabled():
        return None
    _ensure_db_ready()
    import json as _json
    import psycopg2.extras as _extras
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO taxa_entrega_zonas (nome, cidade, taxa, gratis, poligono, cor, ativo)
                VALUES (%s, %s, %s, %s, %s, %s, TRUE)
                RETURNING id, nome, cidade, taxa, gratis, poligono, cor, ativo
                """,
                (
                    str(nome or "").strip(),
                    (str(cidade or "").strip() or None),
                    float(taxa or 0),
                    bool(gratis),
                    _extras.Json(poligono) if poligono else None,
                    str(cor or "#00d4aa").strip() or "#00d4aa",
                ),
            )
            row = cur.fetchone()
            conn.commit()
    if not row:
        return None
    poligono_out = row[5]
    if isinstance(poligono_out, str):
        try:
            poligono_out = _json.loads(poligono_out)
        except Exception:
            poligono_out = None
    return {
        "id": row[0],
        "nome": row[1],
        "cidade": row[2],
        "taxa": float(row[3] or 0),
        "gratis": bool(row[4]),
        "poligono": poligono_out,
        "cor": row[6] or "#00d4aa",
        "ativo": bool(row[7]),
    }


def update_taxa_entrega_zona(
    *,
    zona_id: int,
    nome: str | None = None,
    cidade: str | None = None,
    taxa: float | None = None,
    gratis: bool | None = None,
    poligono: list | None = None,
    cor: str | None = None,
    ativo: bool | None = None,
) -> dict[str, Any] | None:
    if not is_enabled():
        return None
    _ensure_db_ready()
    import json as _json
    import psycopg2.extras as _extras
    sets: list[str] = []
    params: list[Any] = []
    if nome is not None:
        sets.append("nome = %s")
        params.append(str(nome).strip())
    if cidade is not None:
        sets.append("cidade = %s")
        params.append(str(cidade).strip() or None)
    if taxa is not None:
        sets.append("taxa = %s")
        params.append(float(taxa))
    if gratis is not None:
        sets.append("gratis = %s")
        params.append(bool(gratis))
    if poligono is not None:
        sets.append("poligono = %s")
        params.append(_extras.Json(poligono))
    if cor is not None:
        sets.append("cor = %s")
        params.append(str(cor).strip() or "#00d4aa")
    if ativo is not None:
        sets.append("ativo = %s")
        params.append(bool(ativo))
    if not sets:
        return None
    sets.append("atualizado_em = NOW()")
    params.append(int(zona_id))
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE taxa_entrega_zonas SET {', '.join(sets)} WHERE id = %s "
                "RETURNING id, nome, cidade, taxa, gratis, poligono, cor, ativo",
                tuple(params),
            )
            row = cur.fetchone()
            conn.commit()
    if not row:
        return None
    poligono_out = row[5]
    if isinstance(poligono_out, str):
        try:
            poligono_out = _json.loads(poligono_out)
        except Exception:
            poligono_out = None
    return {
        "id": row[0],
        "nome": row[1],
        "cidade": row[2],
        "taxa": float(row[3] or 0),
        "gratis": bool(row[4]),
        "poligono": poligono_out,
        "cor": row[6] or "#00d4aa",
        "ativo": bool(row[7]),
    }


def delete_taxa_entrega_zona(*, zona_id: int) -> bool:
    if not is_enabled():
        return False
    _ensure_db_ready()
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM taxa_entrega_zonas WHERE id = %s", (int(zona_id),))
            deleted = cur.rowcount > 0
            conn.commit()
    return deleted


# ---------------------------------------------------------------------------
# PAGAMENTOS EXTERNOS — CRUD
#
# Funções de acesso à tabela external_payments.
# O PaymentService usa estas funções; elas não contêm regras de domínio.
# ---------------------------------------------------------------------------


def create_external_payment(
    *,
    payment_id: str,
    provider_id: str,
    provider_transaction_id: str,
    payment_method: str,
    amount: float,
    reference_id: str | None = None,
    qr_code_payload: str | None = None,
    qr_code_image_base64: str | None = None,
    qr_code_image_url: str | None = None,
    expires_at: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Cria um registro em external_payments. Retorna o registro criado."""
    if not is_enabled():
        return None

    with _conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                INSERT INTO external_payments
                    (id, provider_id, provider_transaction_id, payment_method,
                     amount, reference_id, qr_code_payload, qr_code_image_base64,
                     qr_code_image_url, expires_at, metadata)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    payment_id,
                    provider_id,
                    provider_transaction_id,
                    payment_method,
                    amount,
                    reference_id,
                    qr_code_payload,
                    qr_code_image_base64,
                    qr_code_image_url,
                    expires_at,
                    psycopg2.extras.Json(metadata) if metadata else None,
                ),
            )
            row = cur.fetchone()
            conn.commit()
            return dict(row) if row else None


def get_external_payment(*, payment_id: str) -> dict[str, Any] | None:
    """Busca um external_payment por ID."""
    if not is_enabled():
        return None

    with _conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM external_payments WHERE id = %s",
                (payment_id,),
            )
            row = cur.fetchone()
            return dict(row) if row else None


def get_external_payment_by_provider_tx(
    *, provider_id: str, provider_transaction_id: str
) -> dict[str, Any] | None:
    """Busca por (provider_id, provider_transaction_id). Para idempotência."""
    if not is_enabled():
        return None

    with _conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT * FROM external_payments
                WHERE provider_id = %s AND provider_transaction_id = %s
                """,
                (provider_id, provider_transaction_id),
            )
            row = cur.fetchone()
            return dict(row) if row else None


def list_pending_external_payments() -> list[dict[str, Any]]:
    """Lista pagamentos APROVADOS não aplicados (para o PDV descobrir via polling)."""
    if not is_enabled():
        return []

    with _conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT * FROM external_payments
                WHERE status = 'APROVADO'
                  AND applied_sale_id IS NULL
                ORDER BY updated_at ASC
                """
            )
            rows = cur.fetchall()
            return [dict(r) for r in rows]


def list_pending_by_reference(*, reference_id: str) -> list[dict[str, Any]]:
    """Lista pagamentos pendentes por reference_id (solicitacao_id)."""
    if not is_enabled():
        return []

    with _conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT * FROM external_payments
                WHERE reference_id = %s
                ORDER BY created_at ASC
                """,
                (reference_id,),
            )
            rows = cur.fetchall()
            return [dict(r) for r in rows]


def update_external_payment_status(
    *,
    payment_id: str,
    status: str,
    last_event_id: str | None = None,
) -> bool:
    """Atualiza o status de um external_payment.

    Respeita a não-regressão de estados terminais:
    APROVADO, RECUSADO, CANCELADO são terminais — não podem ser sobrescritos.

    Retorna True se o status foi atualizado, False se foi bloqueado pela
    não-regressão.
    """
    if not is_enabled():
        return False

    terminal_states = {"APROVADO", "RECUSADO", "CANCELADO"}

    with _conn() as conn:
        with conn.cursor() as cur:
            # Verificar estado atual para não-regressão
            cur.execute(
                "SELECT status FROM external_payments WHERE id = %s",
                (payment_id,),
            )
            row = cur.fetchone()
            if row is None:
                return False

            current_status = str(row[0])
            if current_status in terminal_states and status != current_status:
                # Não-regressão: estado terminal não pode mudar
                # EXCEÇÃO: EXPIRADO → APROVADO é permitido (PIX pago após expiração)
                if not (current_status == "EXPIRADO" and status == "APROVADO"):
                    return False

            cur.execute(
                """
                UPDATE external_payments
                SET status = %s,
                    last_event_id = COALESCE(%s, last_event_id),
                    last_event_at = NOW(),
                    updated_at = NOW()
                WHERE id = %s
                """,
                (status, last_event_id, payment_id),
            )
            conn.commit()
            return cur.rowcount > 0


def claim_external_payment(
    *, payment_id: str, pdv_id: str
) -> dict[str, Any] | None:
    """PDV reivindica um pagamento aprovado.

    Retorna o registro atualizado. Se o pagamento já foi reivindicado pelo
    mesmo PDV, a chamada é idempotente e retorna o registro. Retorna None se
    o pagamento não estiver aprovado ou já estiver reivindicado por outro PDV.
    """
    if not is_enabled():
        return None

    with _conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # Atomic: permite claim se ainda não reivindicado OU se já foi
            # reivindicado pelo mesmo PDV (idempotência).
            cur.execute(
                """
                UPDATE external_payments
                SET claimed_by_pdv_id = COALESCE(claimed_by_pdv_id, %s),
                    claimed_at = COALESCE(claimed_at, NOW()),
                    updated_at = NOW()
                WHERE id = %s
                  AND status = 'APROVADO'
                  AND (claimed_by_pdv_id IS NULL OR claimed_by_pdv_id = %s)
                RETURNING *
                """,
                (pdv_id, payment_id, pdv_id),
            )
            row = cur.fetchone()
            conn.commit()
            return dict(row) if row else None


def apply_external_payment(
    *,
    payment_id: str,
    sale_id: int,
    sale_payment_id: int,
    pdv_id: str | None = None,
) -> bool:
    """PDV aplica o pagamento a uma venda.

    Se pdv_id for informado, também realiza o claim atomicamente e verifica
    se o pagamento pertence ao PDV (ou está sem reivindicação). A operação
    é idempotente: se a mesma tupla (payment_id, sale_id, sale_payment_id)
    já foi aplicada, retorna True.

    Quando pdv_id não é informado, mantém o comportamento legado (Fase 1A)
    para compatibilidade com PaymentService.
    """
    if not is_enabled():
        return False

    with _conn() as conn:
        with conn.cursor() as cur:
            if pdv_id:
                cur.execute(
                    """
                    UPDATE external_payments
                    SET claimed_by_pdv_id = COALESCE(claimed_by_pdv_id, %s),
                        applied_sale_id = %s,
                        applied_sale_payment_id = %s,
                        applied_at = NOW(),
                        updated_at = NOW()
                    WHERE id = %s
                      AND status = 'APROVADO'
                      AND (claimed_by_pdv_id IS NULL OR claimed_by_pdv_id = %s)
                      AND (
                          applied_sale_id IS NULL
                          OR (applied_sale_id = %s AND applied_sale_payment_id = %s)
                      )
                    """,
                    (
                        pdv_id,
                        sale_id,
                        sale_payment_id,
                        payment_id,
                        pdv_id,
                        sale_id,
                        sale_payment_id,
                    ),
                )
            else:
                # Comportamento legado: aplica sem verificação de PDV.
                # Mantido para compatibilidade com PaymentService e Fase 1A.
                cur.execute(
                    """
                    UPDATE external_payments
                    SET applied_sale_id = %s,
                        applied_sale_payment_id = %s,
                        applied_at = NOW(),
                        updated_at = NOW()
                    WHERE id = %s
                      AND applied_sale_id IS NULL
                    """,
                    (sale_id, sale_payment_id, payment_id),
                )
            conn.commit()
            return cur.rowcount > 0


def expire_stale_pending_payments() -> int:
    """Expira pagamentos PENDENTE cujo expires_at < NOW().

    Retorna a quantidade de pagamentos expirados.
    Usado pela reconciliação Cardápio → PSP (Bloco 3.7) e expiração local (Bloco 4.3b).
    """
    if not is_enabled():
        return 0

    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE external_payments
                SET status = 'EXPIRADO',
                    updated_at = NOW()
                WHERE status = 'PENDENTE'
                  AND expires_at IS NOT NULL
                  AND expires_at < NOW()
                """
            )
            count = cur.rowcount
            conn.commit()
            return count


def list_pendentes_para_reconciliacao(*, janela_minutos: int = 5) -> list[dict[str, Any]]:
    """Lista cobranças PENDENTE candidatas à reconciliação com o PSP.

    Seleciona cobranças cujo expires_at está dentro da janela (ex.: 5 minutos
    antes ou depois da expiração) para que o scheduler consulte o PSP e detecte
    aprovações que não chegaram via webhook.

    Bloco 3.7 — reconciliação Cardápio → PSP.
    """
    if not is_enabled():
        return []

    with _conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT * FROM external_payments
                WHERE status = 'PENDENTE'
                  AND provider_transaction_id IS NOT NULL
                  AND expires_at IS NOT NULL
                  AND expires_at <= NOW() + (%s || ' minutes')::interval
                ORDER BY expires_at ASC
                LIMIT 50
                """,
                (str(int(janela_minutos)),),
            )
            rows = cur.fetchall()
            return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# IDEMPOTÊNCIA DE PEDIDOS PÚBLICOS
#
# Usada por POST /api/public/pedidos e POST /api/public/pedidos/<id>/pagar.
# A chave é gerada pelo cliente e é opcional.
# ---------------------------------------------------------------------------


def idempotency_get(*, scope: str, idempotency_key: str) -> dict[str, Any] | None:
    """Busca uma resposta cacheada ainda válida. Retorna None se ausente/expirada."""
    if not is_enabled():
        return None

    key = str(idempotency_key or "").strip()
    sc = str(scope or "").strip()
    if not key or not sc:
        return None

    _ensure_db_ready()

    with _conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT * FROM public_pedidos_idempotency
                WHERE scope = %s
                  AND idempotency_key = %s
                  AND expires_at > NOW()
                """,
                (sc, key),
            )
            row = cur.fetchone()
            return dict(row) if row else None


def idempotency_put(
    *,
    scope: str,
    idempotency_key: str,
    request_hash: str,
    response_json: dict[str, Any],
    status_code: int = 200,
    ttl_seconds: int = 600,
    solicitacao_id: str | None = None,
) -> None:
    """Grava (ou substitui, se já expirada) a resposta associada à chave."""
    if not is_enabled():
        return

    key = str(idempotency_key or "").strip()
    sc = str(scope or "").strip()
    if not key or not sc:
        return

    _ensure_db_ready()

    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO public_pedidos_idempotency
                    (idempotency_key, scope, request_hash, solicitacao_id,
                     response_json, status_code, expires_at)
                VALUES (%s, %s, %s, %s, %s, %s, NOW() + (%s * INTERVAL '1 second'))
                ON CONFLICT (scope, idempotency_key) DO UPDATE SET
                    request_hash = EXCLUDED.request_hash,
                    solicitacao_id = EXCLUDED.solicitacao_id,
                    response_json = EXCLUDED.response_json,
                    status_code = EXCLUDED.status_code,
                    created_at = NOW(),
                    expires_at = EXCLUDED.expires_at
                """,
                (
                    key,
                    sc,
                    str(request_hash or ""),
                    (str(solicitacao_id).strip() if solicitacao_id else None),
                    psycopg2.extras.Json(response_json),
                    int(status_code),
                    int(ttl_seconds),
                ),
            )
            conn.commit()


def idempotency_purge_expired() -> int:
    """Remove registros de idempotência expirados. Retorna a quantidade."""
    if not is_enabled():
        return 0

    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM public_pedidos_idempotency WHERE expires_at <= NOW()")
            count = cur.rowcount
            conn.commit()
            return count


def get_provider_settings(*, provider_id: str) -> dict[str, Any] | None:
    """Busca configurações não-secretas de um provedor."""
    if not is_enabled():
        return None

    with _conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM payment_provider_settings WHERE provider_id = %s",
                (provider_id,),
            )
            row = cur.fetchone()
            return dict(row) if row else None


def upsert_provider_settings(
    *,
    provider_id: str,
    display_name: str,
    base_url: str,
    environment: str = "SANDBOX",
    default_expires_in_seconds: int | None = None,
    webhook_url: str | None = None,
    config_json: dict[str, Any] | None = None,
    is_active: bool = True,
) -> bool:
    """Cria ou atualiza configurações de um provedor."""
    if not is_enabled():
        return False

    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO payment_provider_settings
                    (provider_id, display_name, base_url, environment,
                     default_expires_in_seconds, webhook_url, config_json, is_active)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (provider_id) DO UPDATE SET
                    display_name = EXCLUDED.display_name,
                    base_url = EXCLUDED.base_url,
                    environment = EXCLUDED.environment,
                    default_expires_in_seconds = EXCLUDED.default_expires_in_seconds,
                    webhook_url = EXCLUDED.webhook_url,
                    config_json = EXCLUDED.config_json,
                    is_active = EXCLUDED.is_active,
                    updated_at = NOW()
                """,
                (
                    provider_id,
                    display_name,
                    base_url,
                    environment,
                    default_expires_in_seconds,
                    webhook_url,
                    psycopg2.extras.Json(config_json) if config_json else None,
                    is_active,
                ),
            )
            conn.commit()
            return True


# ---------------------------------------------------------------------------
# CREDENCIAIS DE PROVEDORES — CRUD (secretas, criptografadas)
# ---------------------------------------------------------------------------

def upsert_provider_credential(
    *,
    provider_id: str,
    credential_key: str,
    encrypted_value: str,
    hint: str | None = None,
) -> bool:
    """Cria ou atualiza uma credencial criptografada de provedor.

    O valor DEVE chegar já criptografado (Fernet) do PDV.
    O Cardápio NÃO descriptografa — apenas armazena e devolve.
    """
    if not is_enabled():
        return False

    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO payment_provider_credentials
                    (provider_id, credential_key, encrypted_value, hint)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (provider_id, credential_key) DO UPDATE SET
                    encrypted_value = EXCLUDED.encrypted_value,
                    hint = EXCLUDED.hint,
                    updated_at = NOW()
                """,
                (provider_id, credential_key, encrypted_value, hint),
            )
            conn.commit()
            return True


def get_provider_credentials(*, provider_id: str) -> list[dict[str, Any]]:
    """Lista credenciais criptografadas de um provedor.

    Retorna encrypted_value (NÃO descriptografado). O PDV descriptografa.
    """
    if not is_enabled():
        return []

    with _conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT credential_key, encrypted_value, hint
                FROM payment_provider_credentials
                WHERE provider_id = %s
                """,
                (provider_id,),
            )
            rows = cur.fetchall()
            return [dict(r) for r in rows]


def delete_provider_credential(*, provider_id: str, credential_key: str) -> bool:
    """Remove uma credencial específica."""
    if not is_enabled():
        return False

    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM payment_provider_credentials
                WHERE provider_id = %s AND credential_key = %s
                """,
                (provider_id, credential_key),
            )
            conn.commit()
            return cur.rowcount > 0


def delete_all_provider_credentials(*, provider_id: str) -> bool:
    """Remove todas as credenciais de um provedor."""
    if not is_enabled():
        return False

    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM payment_provider_credentials WHERE provider_id = %s",
                (provider_id,),
            )
            conn.commit()
            return True


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
