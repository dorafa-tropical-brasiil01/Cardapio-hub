"""
Nível 2 — CONTRATO DO ADAPTER (PaymentProviderAdapter).

Define a interface que qualquer PSP deve implementar para integrar com o domínio.
O domínio (Nível 1) usa este contrato; não conhece a implementação concreta.

Princípios:
    - Provider-agnostic by contract; provider-specific by adapter.
    - Method-agnostic by contract; method-specific by adapter.
    - Mechanism-agnostic by contract; mechanism-specific by adapter.

O adapter é responsável por:
    - autenticação com o PSP
    - construção da requisição
    - conversão monetária (reais ↔ centavos)
    - normalização de status (PAID → APPROVED, etc.)
    - validação de webhook (assinatura, token)
    - síntese de event_id quando o PSP não fornece

O domínio NÃO conhece:
    - o formato da resposta do PSP
    - o identificador interno do PSP (txid, charge_id, etc.)
    - o mecanismo de integração (REST, Bluetooth, SmartPOS, TEF)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum


# ---------------------------------------------------------------------------
# Enum de método de pagamento (canônico)
#
# Os valores são strings compatíveis com app/core/payment_methods.py.
# ---------------------------------------------------------------------------

class PaymentMethod(str, Enum):
    PIX = "PIX"
    CARTAO_CREDITO = "CARTAO_CREDITO"
    CARTAO_DEBITO = "CARTAO_DEBITO"
    VOUCHER = "VOUCHER"  # Vale Refeição / Vale Alimentação (VR, Alelo, Sodexo, etc.)
    # Futuro: BOLETO, CARTEIRA_DIGITAL, etc.


# ---------------------------------------------------------------------------
# Enum de status canônico retornado pelo adapter
#
# Cada PSP tem seus próprios status; o adapter normaliza para estes.
# ---------------------------------------------------------------------------

class ProviderPaymentStatus(str, Enum):
    PENDING = "PENDING"        # Cobrança criada, aguardando pagamento
    APPROVED = "APPROVED"      # Pagamento aprovado/liquidado
    DECLINED = "DECLINED"      # Pagamento recusado
    CANCELLED = "CANCELLED"    # Cobrança cancelada
    EXPIRED = "EXPIRED"        # Cobrança expirou sem pagamento
    ERROR = "ERROR"            # Erro no processamento


# ---------------------------------------------------------------------------
# Dataclasses do contrato
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CreatePaymentRequest:
    """Parâmetros para criar uma cobrança no PSP.

    Para PIX: amount + payment_method + reference_id + expires_in_seconds.
    Para cartão (futuro): será estendido com campos de cartão (token, parcelas, etc.)
    sem alteração do domínio — o adapter consome os campos relevantes.
    """
    amount: float                              # Valor em reais (ex.: 100.00)
    payment_method: PaymentMethod              # Método de pagamento
    reference_id: str                          # ID de referência (external_payment_id)
    description: str | None = None             # Descrição opcional
    expires_in_seconds: int | None = None      # Validade da cobrança (default do PSP)


@dataclass(frozen=True)
class QRCodeData:
    """Dados do QR Code / PIX para exibição ao cliente.
    Específico do método PIX. Para cartão, qr_code = None no CreatePaymentResult.
    """
    payload: str                               # Payload "copia e cola" (ex.: "00020126...")
    image_base64: str | None                   # Imagem base64 (se o PSP fornecer)
    image_url: str | None                      # URL da imagem (se o PSP fornecer)


@dataclass(frozen=True)
class CreatePaymentResult:
    """Retorno de create_payment."""
    provider_transaction_id: str               # ID da transação no PSP (ex.: ORDE_...)
    status: ProviderPaymentStatus              # Status inicial (tipicamente PENDING)
    qr_code: QRCodeData | None                 # QR Code (se aplicável ao método)
    expires_at: datetime                       # Quando a cobrança expira (OBRIGATÓRIO)


@dataclass(frozen=True)
class PaymentStatusResult:
    """Retorno de get_payment_status."""
    provider_transaction_id: str
    status: ProviderPaymentStatus
    amount: float | None = None                # Valor confirmado (se disponível)


@dataclass(frozen=True)
class PaymentEvent:
    """Evento canônico de webhook ou consulta.

    O adapter traduz o evento externo (webhook do PSP, resposta de consulta)
    para este formato canônico. O domínio opera sobre PaymentEvent.
    """
    provider_transaction_id: str               # ID da transação no PSP
    status: ProviderPaymentStatus              # Status normalizado
    event_id: str                              # ID do evento para idempotência
    amount: float | None = None                # Valor confirmado (se informado)
    occurred_at: datetime | None = None        # Quando ocorreu (se informado)
    raw_payload: str | None = None             # Payload bruto (para debug/log)
    reference_id: str | None = None            # ID de referência (external_payment_id) — defesa em profundidade
    currency: str | None = None                # Moeda (ex.: "BRL") — defesa em profundidade


# ---------------------------------------------------------------------------
# Contrato do adapter
# ---------------------------------------------------------------------------

class PaymentProviderAdapter(ABC):
    """Contrato que qualquer PSP deve implementar.

    O domínio usa este contrato; não conhece a implementação concreta.
    Cada implementação (PagBankAdapter, etc.) traduz entre o PSP e este contrato.
    """

    @property
    @abstractmethod
    def provider_id(self) -> str:
        """Identificador do provedor (ex.: 'PAGBANK')."""
        ...

    @abstractmethod
    def create_payment(self, request: CreatePaymentRequest) -> CreatePaymentResult:
        """Cria uma cobrança no PSP.

        Para PIX: cria uma Order com QR Code e retorna o QR Code.
        Para outros métodos: cria a cobrança conforme o método.
        """
        ...

    @abstractmethod
    def get_payment_status(self, provider_transaction_id: str) -> PaymentStatusResult:
        """Consulta o status de uma cobrança no PSP.

        Usado pela reconciliação Cardápio → PSP (Bloco 3.7).
        """
        ...

    @abstractmethod
    def cancel_payment(self, provider_transaction_id: str) -> bool:
        """Cancela uma cobrança no PSP.

        Retorna True se cancelada, False se não foi possível cancelar.
        Para PIX QR Code pendente, o PagBank não tem endpoint de cancelamento;
        o adapter retorna False e aguarda expiração natural.
        """
        ...

    @abstractmethod
    def validate_webhook(self, headers: dict[str, str], body: bytes) -> PaymentEvent | None:
        """Valida e traduz um webhook recebido do PSP.

        Verifica assinatura/token, extrai o status, normaliza para PaymentEvent.
        Retorna None se o webhook for inválido (assinatura incorreta, etc.).
        """
        ...
