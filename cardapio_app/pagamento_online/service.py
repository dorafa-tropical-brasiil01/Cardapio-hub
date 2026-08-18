"""
Orquestração do pagamento online (Fase 1A).

REGRA ZERO: este módulo NÃO altera o comportamento de PaymentService,
PagBankAdapter ou da validação de webhook. Ele apenas os USA e conecta o
resultado ao ciclo de vida da solicitação e ao KDS.

Responsabilidades:
    - construir o PaymentService (fábrica compartilhada com as rotas do PDV)
    - criar a cobrança PIX vinculada a uma solicitação (reference_id)
    - detectar transição real para APROVADO em um webhook
    - orquestrar a aprovação respeitando a REGRA DE UNICIDADE FINANCEIRA
    - derivar o estado de apresentação do pagamento
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from .. import core
from ..pedidos import domain as pedidos_domain
from . import domain

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# Fábrica do PaymentService
#
# Prioridade: configuração salva no banco (tela do PDV) e, na ausência dela,
# variáveis de ambiente. Comportamento idêntico ao que já rodava no Sandbox.
# ---------------------------------------------------------------------------

def build_adapter() -> Any:
    """Cria o PagBankAdapter com as credenciais configuradas.

    Exposto separadamente para que a orquestração possa traduzir um webhook em
    PaymentEvent sem acessar membros privados do PaymentService.
    """
    import os

    from ..payments.pagbank_adapter import PagBankAdapter

    provider_id = "PAGBANK"
    token = ""
    webhook_token = None
    sandbox = True
    base_url = None

    if core.pg_enabled():
        settings = core.pg_store.get_provider_settings(provider_id=provider_id)
        if settings and settings.get("is_active"):
            env = str(settings.get("environment") or "SANDBOX").upper()
            sandbox = env == "SANDBOX"
            base_url = settings.get("base_url") or None

            creds = core.pg_store.get_provider_credentials(provider_id=provider_id)
            from ..credential_crypto import decrypt as cred_decrypt

            for cred in (creds or []):
                key = str(cred.get("credential_key") or "")
                encrypted = str(cred.get("encrypted_value") or "")
                if not encrypted:
                    continue
                try:
                    plaintext = cred_decrypt(encrypted)
                except Exception:
                    logger.warning("build_payment_service - falha ao descriptografar %s", key)
                    continue

                if key == "PAGBANK_TOKEN":
                    token = plaintext
                elif key == "PAGBANK_WEBHOOK_TOKEN":
                    webhook_token = plaintext

    if not token:
        token = os.environ.get("PAGBANK_TOKEN", "")
        webhook_token = os.environ.get("PAGBANK_WEBHOOK_TOKEN")
        sandbox = os.environ.get("PAGBANK_SANDBOX", "1") == "1"

    if not token:
        raise RuntimeError(
            "PagBank não configurado. Use a tela de Provedores de Pagamento no PDV "
            "ou configure PAGBANK_TOKEN."
        )

    return PagBankAdapter(
        token=token,
        webhook_token=webhook_token,
        sandbox=sandbox,
        base_url=base_url,
    )


def build_payment_service() -> tuple[Any, Any]:
    """Cria (PaymentService, PaymentMethod) com o PagBankAdapter configurado."""
    from ..payments.adapter_contract import PaymentMethod
    from ..payments.domain import PaymentService

    return PaymentService(store=core.pg_store, adapter=build_adapter()), PaymentMethod


# ---------------------------------------------------------------------------
# Criação de cobrança
# ---------------------------------------------------------------------------

class CobrancaError(RuntimeError):
    """Falha ao criar a cobrança no PSP."""


def criar_cobranca_pix(*, solicitacao_id: str, amount: float, descricao: str | None = None) -> dict[str, Any]:
    """Cria uma cobrança PIX vinculada a uma solicitação.

    O vínculo é feito por `reference_id = solicitacao_id`, o que torna
    external_payments a fonte de verdade do histórico financeiro do pedido.
    """
    try:
        service, PaymentMethod = build_payment_service()
        record = service.iniciar_pagamento(
            payment_method=PaymentMethod.PIX,
            amount=float(amount),
            reference_id=str(solicitacao_id),
            description=descricao,
            expires_in_seconds=domain.qr_expires_in_seconds(),
        )
    except Exception as e:
        logger.exception("criar_cobranca_pix - falha solicitacao_id=%s", solicitacao_id)
        raise CobrancaError(str(e)) from e

    if not isinstance(record, dict) or not record.get("id"):
        raise CobrancaError("PSP não retornou registro de pagamento")

    return record


def vincular_cobranca(rec: dict[str, Any], payment_record: dict[str, Any]) -> dict[str, Any]:
    """Grava o pagamento como ativo na solicitação (sem persistir)."""
    snapshot = domain.montar_snapshot_publico(payment_record)

    rec["pagamento_online"] = True
    rec["active_payment_id"] = snapshot.get("external_payment_id")
    rec["pagamento"] = snapshot
    rec["payment_attempts"] = int(rec.get("payment_attempts") or 0) + 1
    if not rec.get("payment_window_expires_at"):
        rec["payment_window_expires_at"] = domain.window_deadline_iso()
    return rec


def registrar_falha_cobranca(rec: dict[str, Any], *, erro: str) -> dict[str, Any]:
    """Marca a solicitação como tendo falhado ao criar a cobrança."""
    rec["pagamento_online"] = True
    rec["pagamento"] = {"falha": True, "erro": str(erro)[:500]}
    rec["active_payment_id"] = None
    if not rec.get("payment_window_expires_at"):
        rec["payment_window_expires_at"] = domain.window_deadline_iso()
    registrar_ocorrencia(
        rec,
        tipo=domain.OCORRENCIA_FALHA_CRIACAO_COBRANCA,
        descricao=f"Falha ao criar cobrança no PSP: {str(erro)[:200]}",
    )
    return rec


def registrar_ocorrencia(
    rec: dict[str, Any],
    *,
    tipo: str,
    descricao: str,
    external_payment_id: str | None = None,
    amount: Any = None,
) -> dict[str, Any]:
    """Anexa uma ocorrência financeira para tratamento manual (append-only)."""
    ocorrencias = rec.get("ocorrencias_pagamento")
    if not isinstance(ocorrencias, list):
        ocorrencias = []

    ocorrencias.append(
        {
            "tipo": tipo,
            "external_payment_id": external_payment_id,
            "amount": amount,
            "detectado_em": _now_iso(),
            "descricao": descricao,
            "resolvido": False,
        }
    )
    rec["ocorrencias_pagamento"] = ocorrencias
    logger.warning(
        "ocorrencia_pagamento tipo=%s solicitacao_id=%s payment_id=%s - %s",
        tipo, rec.get("id"), external_payment_id, descricao,
    )
    return rec


def expirar_cobranca_ativa(rec: dict[str, Any]) -> None:
    """Marca a cobrança ativa PENDENTE como EXPIRADA localmente.

    O PagBank não permite cancelar QR Code PIX pendente (comportamento
    preservado em PagBankAdapter.cancel_payment). A transição PENDENTE ->
    EXPIRADO é local e permitida pelo PaymentService, que também permite
    EXPIRADO -> APROVADO caso o cliente pague o QR antigo mais tarde.
    """
    payment_id = str(rec.get("active_payment_id") or "").strip()
    if not payment_id or not core.pg_enabled():
        return

    try:
        atual = core.pg_store.get_external_payment(payment_id=payment_id)
    except Exception:
        atual = None

    if not isinstance(atual, dict):
        return
    if str(atual.get("status") or "").strip().upper() != domain.PAY_PENDENTE:
        return

    try:
        core.pg_store.update_external_payment_status(
            payment_id=payment_id, status=domain.PAY_EXPIRADO
        )
    except Exception:
        logger.exception("expirar_cobranca_ativa - falha payment_id=%s", payment_id)


def cancelar_pedido_publico(rec: dict[str, Any]) -> dict[str, Any]:
    """Cancela um pedido online antes do pagamento.

    - Marca a solicitação como cancelada.
    - Atualiza a cobrança ativa para CANCELADO, bloqueando futuros pagamentos.
    - Registra ocorrência se houver tentativa de pagamento posterior.
    """
    solicitacao_id = str(rec.get("id") or "").strip()
    if not solicitacao_id:
        return {"ok": False, "error": "solicitacao_invalida"}

    status = str(rec.get("status") or "").strip().upper()
    if status != pedidos_domain.SOLICITACAO_STATUS_AGUARDANDO_PAGAMENTO:
        return {"ok": False, "error": "status_nao_cancelavel"}

    if not rec.get("pagamento_online"):
        return {"ok": False, "error": "nao_e_pagamento_online"}

    if rec.get("cancelado"):
        return {"ok": True, "ja_cancelado": True}

    # Não permite cancelar se o pagamento já foi confirmado.
    estado = domain.derivar_estado_pagamento(solicitacao=rec)
    if estado == domain.ESTADO_CONFIRMADO:
        return {"ok": False, "error": "pagamento_ja_confirmado"}

    payment_id = str(rec.get("active_payment_id") or "").strip()
    if payment_id and core.pg_enabled():
        try:
            atual = core.pg_store.get_external_payment(payment_id=payment_id)
            if isinstance(atual, dict):
                current_status = str(atual.get("status") or "").strip().upper()
                if current_status == domain.PAY_APROVADO:
                    return {"ok": False, "error": "pagamento_ja_confirmado"}
                if current_status not in (domain.PAY_APROVADO,):
                    core.pg_store.update_external_payment_status(
                        payment_id=payment_id, status=domain.PAY_CANCELADO
                    )
        except Exception:
            logger.exception("cancelar_pedido_publico - falha ao cancelar payment_id=%s", payment_id)

    snap = rec.get("pagamento")
    if isinstance(snap, dict):
        snap["status"] = domain.PAY_CANCELADO
        snap["cancelado_em"] = _now_iso()
        rec["pagamento"] = domain.filtrar_snapshot_publico(snap)

    rec["cancelado"] = True
    rec["cancelado_em"] = _now_iso()
    rec["payment_window_expires_at"] = _now_iso()

    registrar_ocorrencia(
        rec,
        tipo=domain.OCORRENCIA_PAGAMENTO_TARDIO_IGNORADO,
        descricao="Pedido cancelado pelo cliente antes do pagamento.",
        external_payment_id=payment_id or rec.get("active_payment_id"),
    )

    try:
        core.pg_store.save_solicitacao(record=rec)
    except Exception:
        logger.exception("cancelar_pedido_publico - falha ao salvar solicitacao_id=%s", solicitacao_id)
        return {"ok": False, "error": "falha_ao_salvar"}

    return {"ok": True}


# ---------------------------------------------------------------------------
# Estado derivado para respostas públicas
# ---------------------------------------------------------------------------

def estado_publico(rec: dict[str, Any]) -> dict[str, Any]:
    """Retorna estado_pagamento derivado e elegibilidade de retentativa."""
    if rec.get("cancelado"):
        return {"estado_pagamento": "CANCELADO", "pode_retentar": False}

    estado = domain.derivar_estado_pagamento(solicitacao=rec)
    return {
        "estado_pagamento": estado,
        "pode_retentar": domain.pode_retentar(solicitacao=rec, estado_pagamento=estado),
    }


#: Mapeamento estado derivado -> status_publico exibido ao cliente.
_STATUS_PUBLICO_PAGAMENTO = {
    domain.ESTADO_AGUARDANDO: "AGUARDANDO_PAGAMENTO",
    domain.ESTADO_NAO_INICIADO: "AGUARDANDO_PAGAMENTO",
    domain.ESTADO_EXPIRADO: "PAGAMENTO_EXPIRADO",
    domain.ESTADO_RECUSADO: "PAGAMENTO_RECUSADO",
    domain.ESTADO_FALHA: "PAGAMENTO_FALHOU",
}


def status_publico(rec: dict[str, Any]) -> dict[str, Any]:
    """Status público do pedido, considerando o estágio de pagamento.

    Enquanto o pedido aguarda pagamento, o estágio financeiro é o que importa e
    o KDS ainda não recebeu nada. Depois de pago, delega para a regra
    operacional já existente (`pg_store.calcular_status_publico`).
    """
    solicitacao_id = str(rec.get("id") or "").strip()
    status_solicitacao = str(rec.get("status") or "").strip().upper()

    if rec.get("cancelado"):
        return {
            "status_publico": "PEDIDO_CANCELADO",
            "finalizado": True,
            "atualizado_em": _now_iso(),
        }

    estado = domain.derivar_estado_pagamento(solicitacao=rec)

    if status_solicitacao == pedidos_domain.SOLICITACAO_STATUS_AGUARDANDO_PAGAMENTO:
        return {
            "status_publico": _STATUS_PUBLICO_PAGAMENTO.get(estado, "AGUARDANDO_PAGAMENTO"),
            "finalizado": False,
            "atualizado_em": _now_iso(),
        }

    resultado = core.pg_store.calcular_status_publico(solicitacao_id=solicitacao_id)
    if not isinstance(resultado, dict):
        resultado = {"status_publico": "DESCONHECIDO", "finalizado": False}

    # Pedido online já pago e ainda na fila da cozinha: para o cliente isso é
    # "aceito", não "enviado". A regra base devolve ENVIADO porque foi escrita
    # para o fluxo presencial, em que aceite e atendimento são a mesma coisa.
    if (
        estado == domain.ESTADO_CONFIRMADO
        and str(resultado.get("status_publico") or "").upper() == "ENVIADO"
    ):
        resultado["status_publico"] = "ACEITO"

    return resultado


# ---------------------------------------------------------------------------
# Webhook: detecção de transição real
# ---------------------------------------------------------------------------

def processar_webhook(*, headers: dict[str, str], body: bytes, base_url: str = "") -> dict[str, Any] | None:
    """Processa o webhook e orquestra a aprovação quando ela for real.

    A idempotência do pagamento continua sendo responsabilidade do
    PaymentService (via last_event_id). Aqui garantimos apenas que o KDS não
    seja notificado duas vezes: só orquestramos quando o status do pagamento
    efetivamente passou para APROVADO nesta chamada.
    """
    adapter = build_adapter()
    service, _ = build_payment_service()

    conhecia_antes = False
    status_antes = ""
    try:
        evento = adapter.validate_webhook(headers, body)
        if evento is not None:
            anterior = core.pg_store.get_external_payment_by_provider_tx(
                provider_id=adapter.provider_id,
                provider_transaction_id=evento.provider_transaction_id,
            )
            if isinstance(anterior, dict):
                conhecia_antes = True
                status_antes = str(anterior.get("status") or "").strip().upper()
    except Exception:
        # Falha ao inspecionar o estado anterior não pode impedir o
        # processamento do webhook em si.
        logger.exception("processar_webhook - falha ao ler estado anterior")

    record = service.processar_webhook(headers=headers, body=body)
    if not isinstance(record, dict):
        return None

    status_depois = str(record.get("status") or "").strip().upper()
    transicao_real = status_depois == domain.PAY_APROVADO and status_antes != domain.PAY_APROVADO

    try:
        if transicao_real:
            orquestrar_pagamento_aprovado(record, base_url=base_url)
        elif conhecia_antes and status_depois != status_antes:
            sincronizar_snapshot(record)
    except Exception:
        # Nunca deixar uma falha de orquestração virar erro para o PSP: isso
        # provocaria reenvio infinito do webhook.
        logger.exception(
            "processar_webhook - falha na orquestração payment_id=%s", record.get("id")
        )

    return record


def sincronizar_snapshot(payment_record: dict[str, Any]) -> None:
    """Atualiza o snapshot da solicitação quando o pagamento ativo muda de status.

    Usado para transições que não são aprovação (recusa, cancelamento,
    expiração), de modo que o cliente veja o estado correto.
    """
    rec = _carregar_solicitacao(payment_record)
    if rec is None:
        return

    payment_id = str(payment_record.get("id") or "").strip()
    if str(rec.get("active_payment_id") or "").strip() != payment_id:
        return

    snapshot = domain.filtrar_snapshot_publico(rec.get("pagamento")) or {}
    snapshot["status"] = str(payment_record.get("status") or "").strip().upper() or None
    rec["pagamento"] = snapshot
    core.pg_store.save_solicitacao(record=rec)


# ---------------------------------------------------------------------------
# Orquestração da aprovação
# ---------------------------------------------------------------------------

def orquestrar_pagamento_aprovado(payment_record: dict[str, Any], *, base_url: str = "") -> str:
    """Conecta a aprovação do pagamento ao ciclo de vida da solicitação.

    REGRA DE UNICIDADE FINANCEIRA: uma solicitação não pode ter mais de um
    pagamento aprovado aplicado. Aprovação de um segundo pagamento não é
    aplicada automaticamente; gera ocorrência para tratamento manual.

    Corolário: pagamento aprovado NÃO significa automaticamente "este é o
    pagamento ativo". O active_payment_id não é substituído por webhook tardio.

    Retorna um código do desfecho, útil para log e teste:
        "SEM_REFERENCIA", "SOLICITACAO_NAO_ENCONTRADA", "EXCEDENTE",
        "TARDIO_IGNORADO", "CONFIRMADO"
    """
    payment_id = str(payment_record.get("id") or "").strip()
    rec = _carregar_solicitacao(payment_record)

    if rec is None:
        logger.info(
            "orquestrar_pagamento_aprovado - sem solicitação vinculada payment_id=%s", payment_id
        )
        return "SEM_REFERENCIA" if not payment_record.get("reference_id") else "SOLICITACAO_NAO_ENCONTRADA"

    # 0) Pedido cancelado pelo cliente: não aplica o pagamento.
    if rec.get("cancelado"):
        registrar_ocorrencia(
            rec,
            tipo=domain.OCORRENCIA_PAGAMENTO_TARDIO_IGNORADO,
            descricao="Pagamento aprovado para pedido já cancelado. Nenhuma alteração automática foi feita.",
            external_payment_id=payment_id,
            amount=payment_record.get("amount"),
        )
        core.pg_store.save_solicitacao(record=rec)
        return "CANCELADO"

    # 1) Unicidade financeira: já existe outro pagamento aprovado?
    outro = _outro_pagamento_aprovado(
        reference_id=str(payment_record.get("reference_id") or ""),
        payment_id=payment_id,
    )
    if outro is not None:
        registrar_ocorrencia(
            rec,
            tipo=domain.OCORRENCIA_PAGAMENTO_EXCEDENTE,
            descricao=(
                "Pagamento aprovado enquanto já existia outro pagamento aprovado "
                f"({outro}) para a mesma solicitação. Exige estorno manual."
            ),
            external_payment_id=payment_id,
            amount=payment_record.get("amount"),
        )
        core.pg_store.save_solicitacao(record=rec)
        return "EXCEDENTE"

    # 2) A solicitação ainda está aguardando pagamento?
    status_atual = str(rec.get("status") or "").strip().upper()
    if status_atual != pedidos_domain.SOLICITACAO_STATUS_AGUARDANDO_PAGAMENTO:
        registrar_ocorrencia(
            rec,
            tipo=domain.OCORRENCIA_PAGAMENTO_TARDIO_IGNORADO,
            descricao=(
                f"Pagamento aprovado com a solicitação já em '{status_atual}'. "
                "Nenhuma alteração automática foi feita."
            ),
            external_payment_id=payment_id,
            amount=payment_record.get("amount"),
        )
        core.pg_store.save_solicitacao(record=rec)
        return "TARDIO_IGNORADO"

    # 3) Este é o único pagamento aprovado: assume o fluxo normal.
    snapshot = domain.montar_snapshot_publico(payment_record)
    snapshot["confirmado_em"] = _now_iso()

    rec["status"] = pedidos_domain.SOLICITACAO_STATUS_PENDENTE
    rec["pago_em"] = _now_iso()
    rec["active_payment_id"] = payment_id
    rec["pagamento"] = snapshot

    core.pg_store.save_solicitacao(record=rec)

    solicitacao_id = str(rec.get("id") or "").strip()
    logger.info(
        "orquestrar_pagamento_aprovado - confirmado solicitacao_id=%s payment_id=%s amount=%s",
        solicitacao_id, payment_id, payment_record.get("amount"),
    )

    _liberar_para_producao(rec, base_url=base_url)
    return "CONFIRMADO"


def _liberar_para_producao(rec: dict[str, Any], *, base_url: str = "") -> None:
    """Cria a linha do KDS e notifica a cozinha. Só ocorre após pagamento."""
    solicitacao_id = str(rec.get("id") or "").strip()
    if not solicitacao_id:
        return

    try:
        core.pg_store.kds_ensure_order_row(solicitacao_id=solicitacao_id)
    except Exception:
        logger.exception("_liberar_para_producao - falha kds_ensure_order_row sid=%s", solicitacao_id)

    try:
        core.notify_telegram_new_order(rec)
    except Exception:
        logger.exception("_liberar_para_producao - falha telegram sid=%s", solicitacao_id)

    try:
        from ..kds.service import notificar_kds_novo_pedido

        notificar_kds_novo_pedido(solicitacao_id=solicitacao_id, base_url=str(base_url or ""))
    except Exception:
        logger.exception("_liberar_para_producao - falha notificar KDS sid=%s", solicitacao_id)


def _carregar_solicitacao(payment_record: dict[str, Any]) -> dict[str, Any] | None:
    reference_id = str(payment_record.get("reference_id") or "").strip()
    if not reference_id or not core.pg_enabled():
        return None
    try:
        rec = core.pg_store.get_solicitacao(solicitacao_id=reference_id)
    except Exception:
        logger.exception("_carregar_solicitacao - falha reference_id=%s", reference_id)
        return None
    return rec if isinstance(rec, dict) else None


def _outro_pagamento_aprovado(*, reference_id: str, payment_id: str) -> str | None:
    """ID de outro pagamento APROVADO da mesma solicitação, se existir.

    A fonte de verdade do histórico financeiro é external_payments, consultada
    por reference_id. Nenhum histórico é mantido no JSON da solicitação.

    Observação: `list_pending_by_reference` retorna todos os pagamentos da
    referência, apesar do nome.
    """
    ref = str(reference_id or "").strip()
    if not ref or not core.pg_enabled():
        return None

    try:
        pagamentos = core.pg_store.list_pending_by_reference(reference_id=ref)
    except Exception:
        logger.exception("_outro_pagamento_aprovado - falha reference_id=%s", ref)
        return None

    for p in pagamentos or []:
        if not isinstance(p, dict):
            continue
        pid = str(p.get("id") or "").strip()
        if not pid or pid == payment_id:
            continue
        if str(p.get("status") or "").strip().upper() == domain.PAY_APROVADO:
            return pid

    return None


def tem_cobranca_ativa_pendente(rec: dict[str, Any]) -> bool:
    """True quando existe cobrança ativa PENDENTE e ainda não expirada."""
    estado = domain.derivar_estado_pagamento(solicitacao=rec)
    return estado == domain.ESTADO_AGUARDANDO
