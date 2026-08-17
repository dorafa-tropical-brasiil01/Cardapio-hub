"""Orquestração do pagamento online (Fase 1A).

Este pacote NÃO altera o domínio de pagamentos (`cardapio_app/payments`).
Ele orquestra: pedido -> cobrança -> webhook -> solicitação -> KDS.
"""

from __future__ import annotations
