"""
Política A4 — dados sensíveis de cartão.

Trava arquitetural formal: dados sensíveis de cartão (encrypted_card, número,
CVV, etc.) NUNCA devem ser logados, persistidos, enviados para APM, incluídos
em traceback, auditoria, analytics ou cache.

Esta política é NÃO INVASIVA ao fluxo PIX: nenhum código do PIX é alterado.
O módulo existe para ser usado pelo código de cartão (M2/M3, V2) quando for
escrito, e pode ser aplicado retroativamente ao logging do Cardápio.

Uso típico:

    from cardapio_app.sensitive_data import redact_sensitive, safe_log_dict

    # Antes de logar um dict que pode conter encrypted_card:
    logger.info("payload %s", redact_sensitive(payload))

    # Para garantir que um dict só exponha campos seguros:
    safe = safe_log_dict(payload, allowed_keys={"id", "status", "amount"})

Regras:
    - encrypted_card: substituído por "[REDACTED:encrypted_card]"
    - card.number / number: substituído por "[REDACTED:number]"
    - security_code / cvv: substituído por "[REDACTED:security_code]"
    - holder_tax_id: substituído por "[REDACTED:holder_tax_id]"
    - Qualquer campo cujo nome case-insensitive contenha "encrypted" ou "card"
      e não esteja na allowlist é redacted.

Esta política NÃO altera o comportamento do PaymentService, PagBankAdapter,
adapter_contract ou da validação de webhook (REGRA ZERO).
"""

from __future__ import annotations

import copy
import re
from typing import Any, Iterable

# ---------------------------------------------------------------------------
# Campos sensíveis — nunca devem aparecer em logs, APM, auditoria ou cache
# ---------------------------------------------------------------------------

#: Campos exatos (case-insensitive) que são sempre sensíveis.
SENSITIVE_FIELD_NAMES: frozenset[str] = frozenset({
    "encrypted_card",
    "encrypted",
    "security_code",
    "cvv",
    "cvc",
    "card_number",
    "number",  # quando dentro de um objeto "card"
    "holder_tax_id",
    "tax_id",  # quando dentro de um objeto "card" ou "holder"
    "exp_month",
    "exp_year",
    "holder_name",
})

#: Padrões de nome de campo que indicam sensibilidade (regex, case-insensitive).
_SENSITIVE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"encrypted", re.IGNORECASE),
    re.compile(r"security_?code", re.IGNORECASE),
    re.compile(r"\bcvv\b", re.IGNORECASE),
    re.compile(r"\bcvc\b", re.IGNORECASE),
    re.compile(r"card_?number", re.IGNORECASE),
    re.compile(r"holder_?tax", re.IGNORECASE),
)

#: Valor de redação.
_REDACTED = "[REDACTED]"


def _is_sensitive_key(key: str) -> bool:
    """True se o nome do campo indica um dado sensível de cartão."""
    k = str(key or "").strip().lower()
    if k in SENSITIVE_FIELD_NAMES:
        return True
    return any(p.search(k) for p in _SENSITIVE_PATTERNS)


def redact_sensitive(value: Any) -> Any:
    """Redact dados sensíveis de cartão de uma estrutura qualquer.

    Recursivamente percorre dicts e listas, substituindo valores de campos
    sensíveis por "[REDACTED]". Não modifica o original — retorna uma cópia.

    Args:
        value: dict, list, ou valor primitivo.

    Returns:
        Cópia com campos sensíveis redacted.
    """
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for k, v in value.items():
            if _is_sensitive_key(k):
                result[k] = _REDACTED
            else:
                result[k] = redact_sensitive(v)
        return result
    if isinstance(value, list):
        return [redact_sensitive(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_sensitive(item) for item in value)
    return value


def safe_log_dict(data: dict[str, Any], *, allowed_keys: Iterable[str]) -> dict[str, Any]:
    """Constrói um dict seguro para log a partir de uma allowlist explícita.

    Só inclui chaves que estão na allowlist. Qualquer outra chave é descartada.
    Mais seguro que redact_sensitive quando se sabe exatamente o que expor.

    Args:
        data: dict original.
        allowed_keys: chaves permitidas no resultado.

    Returns:
        Novo dict contendo apenas as chaves permitidas.
    """
    allowed = set(allowed_keys)
    return {k: copy.deepcopy(v) for k, v in data.items() if k in allowed}


def assert_no_sensitive(data: Any, *, path: str = "") -> None:
    """Afirma que uma estrutura não contém dados sensíveis.

    Levanta AssertionError se encontrar qualquer campo sensível com valor
    não-redacted. Útil em testes e em asserts de runtime antes de logar.

    Args:
        data: estrutura a verificar.
        path: caminho interno (para mensagem de erro).
    """
    if isinstance(data, dict):
        for k, v in data.items():
            current_path = f"{path}.{k}" if path else str(k)
            if _is_sensitive_key(k) and v != _REDACTED and v is not None:
                raise AssertionError(
                    f"campo sensível detectado em {current_path}: valor não redacted"
                )
            assert_no_sensitive(v, path=current_path)
    elif isinstance(data, list):
        for i, item in enumerate(data):
            assert_no_sensitive(item, path=f"{path}[{i}]")
