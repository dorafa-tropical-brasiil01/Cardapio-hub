from __future__ import annotations

from typing import Final

# Status do KDS (ciclo de preparo da cozinha).
KDS_STATUS_NOVO: Final[str] = "NOVO"
KDS_STATUS_EM_PREPARO: Final[str] = "EM_PREPARO"
KDS_STATUS_PRONTO: Final[str] = "PRONTO"
KDS_STATUS_SINALIZADO: Final[str] = "SINALIZADO"
KDS_STATUS_RECUSADO: Final[str] = "RECUSADO"

# Legado: AGUARDANDO foi substituído por NOVO. Mantido para compatibilidade
# em migrations e em código que ainda possa referenciá-lo.
KDS_STATUS_AGUARDANDO: Final[str] = "AGUARDANDO"

# Status da solicitação (ciclo de atendimento).
#
# São apenas quatro. As condições de exceção do pagamento (expirado, recusado,
# falha na criação da cobrança) NÃO são status da solicitação: elas pertencem ao
# ciclo de vida de external_payments e são derivadas na leitura. Ver
# cardapio_app/pagamento_online/domain.py.
SOLICITACAO_STATUS_AGUARDANDO_PAGAMENTO: Final[str] = "AGUARDANDO_PAGAMENTO"
SOLICITACAO_STATUS_PENDENTE: Final[str] = "PENDENTE"
SOLICITACAO_STATUS_EM_ATENDIMENTO: Final[str] = "EM_ATENDIMENTO"
SOLICITACAO_STATUS_RESPONDIDA: Final[str] = "RESPONDIDA"

LOG_STATUS_AGUARDANDO: Final[str] = "AGUARDANDO"
LOG_STATUS_EM_CORRIDA: Final[str] = "EM_CORRIDA"
LOG_STATUS_ENTREGUE: Final[str] = "ENTREGUE"
LOG_STATUS_DEVOLVIDO: Final[str] = "DEVOLVIDO"

# Motivos padrão de recusa no KDS.
KDS_MOTIVO_FALTOU_INGREDIENTE: Final[str] = "FALTOU_INGREDIENTE"
KDS_MOTIVO_FORA_HORARIO: Final[str] = "FORA_HORARIO"
KDS_MOTIVO_PEDIDO_MUITO_GRANDE: Final[str] = "PEDIDO_MUITO_GRANDE"
KDS_MOTIVO_OUTRO: Final[str] = "OUTRO"
