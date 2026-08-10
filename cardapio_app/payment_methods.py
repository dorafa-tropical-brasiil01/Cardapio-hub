"""
ESPELHO da fonte única de verdade das modalidades de pagamento.

    Original: PDV/app/core/payment_methods.py
    Espelho:  Cardapio/cardapio_app/payment_methods.py  (este arquivo)

O Cardápio Online roda em outro processo/servidor e não pode importar o
pacote do PDV. Por isso os códigos são replicados aqui.

ATENÇÃO: ao alterar qualquer código interno em um dos arquivos, altere o
outro. O teste `PDV/tests/test_payment_methods_sync.py` falha se os dois
saírem de sincronia.

Os pedidos gerados aqui (link público, QR Code de mesa, quiosque, street)
devem sempre enviar ao PDV um dos códigos abaixo, nunca um texto livre.
"""

from __future__ import annotations


DINHEIRO = "DINHEIRO"
PIX = "PIX"
CARTAO_DEBITO = "CARTAO_DEBITO"
CARTAO_CREDITO = "CARTAO_CREDITO"
FIADO = "FIADO"

#: Código genérico anterior à separação débito/crédito.
#: Aceito apenas na LEITURA de pedidos antigos.
CARTAO_LEGADO = "CARTAO"

#: Pedido sem definição de uma única modalidade.
#:
#: NÃO é uma modalidade de pagamento e nunca existiu no PDV como tal. Pagar
#: misto significa dividir o valor entre duas modalidades, e essa divisão só
#: pode ser feita no balcão, onde o operador informa quanto entra em cada uma.
#: No pedido online o cliente informa apenas a intenção, e "Misto" não informa
#: nada de útil para quem vai receber.
#:
#: Mantido apenas para LER pedidos antigos e para não recusar um pedido vindo
#: de uma página que ficou aberta antes desta mudança.
MISTO = "MISTO"


#: Nomes exibidos ao cliente final. Devem bater com o PDV.
DISPLAY_NAMES: dict[str, str] = {
    DINHEIRO: "Dinheiro",
    PIX: "PIX",
    CARTAO_DEBITO: "Cartão de débito",
    CARTAO_CREDITO: "Cartão de crédito",
    FIADO: "Venda a prazo",
    CARTAO_LEGADO: "Cartão (registro antigo)",
    MISTO: "A definir no balcão",
}


#: Modalidades que o cliente pode escolher em um pedido online.
#: "Venda a prazo" não aparece: depende de cadastro e aprovação no balcão.
#: "Misto" não aparece: é exclusivo do PDV físico.
ONLINE_PAYMENT_METHODS: tuple[str, ...] = (
    DINHEIRO,
    PIX,
    CARTAO_DEBITO,
    CARTAO_CREDITO,
)


#: Códigos que a API tolera receber por compatibilidade, mas que NÃO são
#: oferecidos ao cliente. Recusar um destes derrubaria o pedido de quem está
#: com a página antiga carregada no navegador, e o cliente não tem como
#: adivinhar o motivo. Tolerar é diferente de oferecer.
LEGACY_WIRE_PAYMENT_METHODS: frozenset[str] = frozenset({CARTAO_LEGADO, MISTO})


#: Tudo que a API aceita receber: o que é oferecido hoje mais o legado tolerado.
ALLOWED_PAYMENT_METHODS: frozenset[str] = frozenset(
    {*ONLINE_PAYMENT_METHODS, *LEGACY_WIRE_PAYMENT_METHODS}
)


def normalize(payment_method: str | None) -> str:
    """Normaliza um código recebido do navegador ou da API."""
    return str(payment_method or "").strip().upper()


def display_name(payment_method: str | None) -> str:
    """Nome amigável. Para códigos desconhecidos, devolve o próprio código."""
    code = normalize(payment_method)
    return DISPLAY_NAMES.get(code, code or "-")


def is_allowed(payment_method: str | None) -> bool:
    """True quando a API deve aceitar o código informado."""
    return normalize(payment_method) in ALLOWED_PAYMENT_METHODS


def is_offered_online(payment_method: str | None) -> bool:
    """True apenas para o que o cliente pode escolher hoje.

    Use isto para montar telas. `is_allowed` é mais permissivo de propósito,
    porque também cobre os códigos legados que ainda chegam pela rede.
    """
    return normalize(payment_method) in set(ONLINE_PAYMENT_METHODS)
