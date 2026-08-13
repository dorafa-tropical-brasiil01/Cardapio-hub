"""
Pacote de pagamentos externos — Fase 1 (PIX via PagBank API Order).

Estrutura de 3 níveis (Contrato 0D):
    Nível 1 — Domínio (PaymentService, ExternalPayment, PaymentStatus, PaymentEvent)
    Nível 2 — Contrato do adapter (PaymentProviderAdapter, dataclasses)
    Nível 3 — Implementações (PagBankAdapter)

O domínio não conhece PSP, método específico, canal ou mecanismo de integração.
"""
