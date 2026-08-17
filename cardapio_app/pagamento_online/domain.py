"""
Domínio PURO do pagamento online (Fase 1A).

Este módulo contém apenas regras e cálculos. Não importa Flask, não importa
pg_store e não faz I/O. Isso permite testá-lo isoladamente e garante que as
regras financeiras sejam auditáveis sem subir a aplicação.

Separação de vocabulários (decisão do plano, ajuste 2):

    external_payments.status  -> vocabulário FINANCEIRO, dono: PaymentService
                                 (PENDENTE, APROVADO, RECUSADO, CANCELADO, EXPIRADO)

    solicitacao.status        -> vocabulário de ATENDIMENTO
                                 (AGUARDANDO_PAGAMENTO, PENDENTE,
                                  EM_ATENDIMENTO, RESPONDIDA)

    estado_pagamento          -> vocabulário DERIVADO, de apresentação
                                 (NAO_APLICAVEL, NAO_INICIADO, AGUARDANDO,
                                  EXPIRADO, RECUSADO, CONFIRMADO, FALHA)

O snapshot gravado em `solicitacao.pagamento` guarda o status financeiro
verbatim. Nenhuma tradução é feita entre os dois primeiros vocabulários, para
não haver dois nomes para o mesmo fato.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any, Final

# ---------------------------------------------------------------------------
# Configuração operacional
#
# Estes valores são CONFIGURAÇÃO DO MVP, não regra contratual do domínio
# (decisão do plano, ajuste 4). Podem mudar sem redesenho do sistema.
# ---------------------------------------------------------------------------

#: Validade do QR Code PIX, em segundos.
DEFAULT_QR_EXPIRES_IN_SECONDS: Final[int] = 1800  # 30 minutos

#: Janela operacional durante a qual o cliente pode gerar um novo QR Code.
DEFAULT_RETRY_WINDOW_SECONDS: Final[int] = 7200  # 2 horas

#: Tolerância monetária para comparação de valores (um centavo).
AMOUNT_TOLERANCE: Final[float] = 0.01


def _env_int(name: str, default: int) -> int:
    raw = str(os.environ.get(name) or "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def qr_expires_in_seconds() -> int:
    return _env_int("CARDAPIO_PIX_QR_EXPIRES_IN_SECONDS", DEFAULT_QR_EXPIRES_IN_SECONDS)


def retry_window_seconds() -> int:
    return _env_int("CARDAPIO_PIX_RETRY_WINDOW_SECONDS", DEFAULT_RETRY_WINDOW_SECONDS)


def pix_online_enabled() -> bool:
    """Feature flag da Fase 1A.

    Desligada (padrão), o Cardápio mantém exatamente o comportamento anterior:
    pedido criado como PENDENTE e KDS notificado na criação.
    """
    raw = str(os.environ.get("CARDAPIO_PIX_ONLINE_ENABLED") or "").strip().lower()
    return raw in ("1", "true", "yes", "y", "on")


# ---------------------------------------------------------------------------
# Métodos elegíveis a pagamento online
# ---------------------------------------------------------------------------

PAYMENT_METHOD_PIX: Final[str] = "PIX"

#: Somente PIX é cobrado online na Fase 1. Cartão exige checkout redirecionado
#: e está fora do escopo.
ONLINE_CHARGEABLE_METHODS: Final[frozenset[str]] = frozenset({PAYMENT_METHOD_PIX})


def is_online_chargeable(payment_method: Any) -> bool:
    return str(payment_method or "").strip().upper() in ONLINE_CHARGEABLE_METHODS


# ---------------------------------------------------------------------------
# Estados financeiros (espelho de payments/domain.py PaymentStatus)
# ---------------------------------------------------------------------------

PAY_PENDENTE: Final[str] = "PENDENTE"
PAY_APROVADO: Final[str] = "APROVADO"
PAY_RECUSADO: Final[str] = "RECUSADO"
PAY_EXPIRADO: Final[str] = "EXPIRADO"
PAY_CANCELADO: Final[str] = "CANCELADO"


# ---------------------------------------------------------------------------
# Estado derivado do pagamento (apresentação)
# ---------------------------------------------------------------------------

ESTADO_NAO_APLICAVEL: Final[str] = "NAO_APLICAVEL"
ESTADO_NAO_INICIADO: Final[str] = "NAO_INICIADO"
ESTADO_AGUARDANDO: Final[str] = "AGUARDANDO"
ESTADO_EXPIRADO: Final[str] = "EXPIRADO"
ESTADO_RECUSADO: Final[str] = "RECUSADO"
ESTADO_CONFIRMADO: Final[str] = "CONFIRMADO"
ESTADO_FALHA: Final[str] = "FALHA"

#: Estados a partir dos quais o cliente pode gerar uma nova cobrança.
ESTADOS_RETENTAVEIS: Final[frozenset[str]] = frozenset(
    {ESTADO_NAO_INICIADO, ESTADO_EXPIRADO, ESTADO_RECUSADO, ESTADO_FALHA}
)


# ---------------------------------------------------------------------------
# Ocorrências financeiras que exigem tratamento manual
# ---------------------------------------------------------------------------

OCORRENCIA_PAGAMENTO_EXCEDENTE: Final[str] = "PAGAMENTO_EXCEDENTE"
OCORRENCIA_PAGAMENTO_TARDIO_IGNORADO: Final[str] = "PAGAMENTO_TARDIO_IGNORADO"
OCORRENCIA_FALHA_CRIACAO_COBRANCA: Final[str] = "FALHA_CRIACAO_COBRANCA"


# ---------------------------------------------------------------------------
# Campos do pagamento expostos publicamente
#
# ALLOWLIST. O snapshot gravado na solicitação é construído exclusivamente a
# partir destas chaves. Campos privados (provider_transaction_id,
# claimed_by_pdv_id, applied_sale_id, last_event_id, metadata,
# qr_code_image_base64) nunca entram no registro da solicitação e, portanto,
# não podem vazar nem se o registro inteiro for serializado.
# ---------------------------------------------------------------------------

PUBLIC_PAYMENT_FIELDS: Final[tuple[str, ...]] = (
    "external_payment_id",
    "payment_method",
    "status",
    "amount",
    "currency",
    "qr_code_payload",
    "qr_code_image_url",
    "expires_at",
    "confirmado_em",
    "estornado",
    "estornado_em",
    "estornado_por",
    "observacao",
)

#: Campos que jamais podem aparecer em resposta pública. Usado pelos testes.
PRIVATE_PAYMENT_FIELDS: Final[tuple[str, ...]] = (
    "provider_id",
    "provider_transaction_id",
    "claimed_by_pdv_id",
    "claimed_at",
    "applied_sale_id",
    "applied_sale_payment_id",
    "applied_at",
    "last_event_id",
    "last_event_at",
    "metadata",
    "qr_code_image_base64",
)


# ---------------------------------------------------------------------------
# Helpers de data
# ---------------------------------------------------------------------------

def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def parse_dt(value: Any) -> datetime | None:
    """Converte datetime/str ISO em datetime timezone-aware.

    Valores naive são interpretados como horário local, coerente com o resto do
    Cardápio, que grava timestamps via `datetime.now().isoformat()`.
    """
    if value is None:
        return None

    if isinstance(value, datetime):
        dt = value
    else:
        raw = str(value).strip()
        if not raw:
            return None
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(raw)
        except ValueError:
            return None

    if dt.tzinfo is None:
        return dt.astimezone()
    return dt


def is_expired(value: Any, *, reference: datetime | None = None) -> bool:
    """True quando `value` representa um instante já passado."""
    dt = parse_dt(value)
    if dt is None:
        return False
    return dt <= (reference or now_utc())


def window_deadline_iso(*, seconds: int | None = None) -> str:
    """Prazo final da janela de retentativa, em ISO local (padrão do projeto)."""
    total = seconds if seconds is not None else retry_window_seconds()
    return (datetime.now() + timedelta(seconds=total)).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# Snapshot público do pagamento
# ---------------------------------------------------------------------------

def montar_snapshot_publico(payment_record: Any) -> dict[str, Any]:
    """Constrói o snapshot público de um registro de external_payments.

    O `status` é mantido verbatim (vocabulário financeiro). Nenhum campo fora da
    allowlist é copiado.
    """
    if not isinstance(payment_record, dict):
        return {}

    expires_at = payment_record.get("expires_at")
    if isinstance(expires_at, datetime):
        expires_at = expires_at.isoformat(timespec="seconds")

    snapshot: dict[str, Any] = {
        "external_payment_id": str(payment_record.get("id") or "") or None,
        "payment_method": payment_record.get("payment_method"),
        "status": str(payment_record.get("status") or "").strip().upper() or None,
        "amount": _as_float(payment_record.get("amount")),
        "currency": payment_record.get("currency") or "BRL",
        "qr_code_payload": payment_record.get("qr_code_payload"),
        "qr_code_image_url": payment_record.get("qr_code_image_url"),
        "expires_at": expires_at,
        "confirmado_em": None,
        "estornado": False,
        "estornado_em": None,
        "estornado_por": None,
        "observacao": None,
    }
    return {k: snapshot.get(k) for k in PUBLIC_PAYMENT_FIELDS}


def filtrar_snapshot_publico(snapshot: Any) -> dict[str, Any] | None:
    """Reaplica a allowlist a um snapshot já gravado.

    Rede de segurança para registros antigos ou gravados por outra versão.
    """
    if not isinstance(snapshot, dict):
        return None
    return {k: snapshot.get(k) for k in PUBLIC_PAYMENT_FIELDS if k in snapshot}


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return round(float(value) + 1e-9, 2)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Estado derivado
# ---------------------------------------------------------------------------

def derivar_estado_pagamento(
    *,
    solicitacao: Any,
    pagamento: Any = None,
    reference: datetime | None = None,
) -> str:
    """Deriva o estado de apresentação do pagamento de uma solicitação.

    `pagamento` é o snapshot público (ou o registro de external_payments).
    Quando ausente, usa `solicitacao["pagamento"]`.

    Nenhuma condição de exceção é lida de `solicitacao["status"]`: expiração,
    recusa e falha vivem no pagamento, não no atendimento (ajuste 2).
    """
    if not isinstance(solicitacao, dict):
        return ESTADO_NAO_APLICAVEL

    if not solicitacao.get("pagamento_online"):
        return ESTADO_NAO_APLICAVEL

    snap = pagamento if isinstance(pagamento, dict) else solicitacao.get("pagamento")
    if not isinstance(snap, dict):
        return ESTADO_NAO_INICIADO

    if snap.get("falha"):
        return ESTADO_FALHA

    payment_id = snap.get("external_payment_id") or snap.get("id")
    if not payment_id:
        return ESTADO_NAO_INICIADO

    status = str(snap.get("status") or "").strip().upper()

    if status == PAY_APROVADO:
        return ESTADO_CONFIRMADO
    if status in (PAY_RECUSADO, PAY_CANCELADO):
        return ESTADO_RECUSADO
    if status == PAY_EXPIRADO:
        return ESTADO_EXPIRADO
    if status == PAY_PENDENTE:
        if is_expired(snap.get("expires_at"), reference=reference):
            return ESTADO_EXPIRADO
        return ESTADO_AGUARDANDO

    return ESTADO_NAO_INICIADO


def pode_retentar(
    *,
    solicitacao: Any,
    estado_pagamento: str | None = None,
    reference: datetime | None = None,
) -> bool:
    """True quando o cliente pode gerar uma nova cobrança para o pedido."""
    from ..pedidos import domain as pedidos_domain

    if not isinstance(solicitacao, dict):
        return False
    if not solicitacao.get("pagamento_online"):
        return False

    status = str(solicitacao.get("status") or "").strip().upper()
    if status != pedidos_domain.SOLICITACAO_STATUS_AGUARDANDO_PAGAMENTO:
        return False

    estado = estado_pagamento or derivar_estado_pagamento(
        solicitacao=solicitacao, reference=reference
    )
    if estado not in ESTADOS_RETENTAVEIS:
        return False

    deadline = solicitacao.get("payment_window_expires_at")
    if deadline and is_expired(deadline, reference=reference):
        return False

    return True


# ---------------------------------------------------------------------------
# Cálculo definitivo do total
#
# O total cobrado NUNCA vem do cliente. Ele é recalculado a partir do catálogo
# publicado, que é a fonte de verdade dos preços.
# ---------------------------------------------------------------------------

class ProdutoDesconhecidoError(ValueError):
    """Item do pedido não existe no catálogo publicado."""

    def __init__(self, product_code: str) -> None:
        super().__init__(product_code)
        self.product_code = product_code


def indexar_precos(produtos: Any) -> dict[str, float]:
    """Mapa código -> preço unitário a partir do catálogo publicado."""
    out: dict[str, float] = {}
    if not isinstance(produtos, list):
        return out

    for p in produtos:
        if not isinstance(p, dict):
            continue

        preco = p.get("preco")
        if preco is None:
            preco = p.get("unit_price")
        if preco is None:
            preco = p.get("price")
        try:
            preco_f = float(preco)
        except (TypeError, ValueError):
            continue

        for raw_code in (p.get("pdvCode"), p.get("id"), p.get("code")):
            code = str(raw_code or "").strip().upper()
            if code:
                out.setdefault(code, preco_f)

    return out


def calcular_subtotal(*, produtos: Any, itens: Any) -> tuple[float, list[dict[str, Any]]]:
    """Calcula o subtotal e devolve os itens com preço unitário resolvido.

    Levanta ProdutoDesconhecidoError se algum código não estiver no catálogo:
    é melhor recusar o pedido do que cobrar um valor que não podemos justificar.
    """
    precos = indexar_precos(produtos)
    subtotal = 0.0
    detalhados: list[dict[str, Any]] = []

    for it in itens or []:
        if not isinstance(it, dict):
            continue
        code = str(it.get("product_code") or "").strip().upper()
        try:
            qty = float(it.get("qty") or 0)
        except (TypeError, ValueError):
            qty = 0.0

        if code not in precos:
            raise ProdutoDesconhecidoError(code)

        unit_price = precos[code]
        line_total = round(unit_price * qty + 1e-9, 2)
        subtotal = round(subtotal + line_total + 1e-9, 2)

        item = dict(it)
        item["unit_price"] = unit_price
        item["line_total"] = line_total
        detalhados.append(item)

    return subtotal, detalhados


def valores_coincidem(a: Any, b: Any, *, tolerance: float = AMOUNT_TOLERANCE) -> bool:
    """Comparação monetária com tolerância de um centavo.

    Usada na Fase 1B antes de aplicar um pagamento externo a uma venda.
    """
    try:
        return abs(float(a) - float(b)) <= tolerance
    except (TypeError, ValueError):
        return False
