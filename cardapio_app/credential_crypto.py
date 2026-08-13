"""
Criptografia simétrica de credenciais de provedores de pagamento (Cardápio).

Usa Fernet (AES-128-CBC + HMAC-SHA256) da biblioteca `cryptography`.
A chave é derivada de uma variável de ambiente (CARDAPIO_CREDENTIAL_SECRET)
 combinada com um salt de aplicação.

O Cardápio é quem criptografa e descriptografa as credenciais, porque:
    - O Cardápio armazena as credenciais (PostgreSQL);
    - O Cardápio usa as credenciais (PagBankAdapter em _get_payment_service);
    - O Cardápio valida webhooks (precisa do webhook_token descriptografado).

O PDV envia credenciais em texto plano via HTTPS (TLS protege em trânsito).
O Cardápio criptografa antes de armazenar e descriptografa quando precisa usar.

NUNCA logar o valor de `encrypt()` ou `decrypt()`.
NUNCA logar a chave derivada.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import os

logger = logging.getLogger(__name__)

_APP_SALT = b"DoRafa-Cardapio-PaymentProviderCredentials-v1"


def _get_secret() -> str:
    """Obtém o secret da env var CARDAPIO_CREDENTIAL_SECRET.

    Se não estiver definida, usa um fallback derivado de DATABASE_URL
    (para desenvolvimento). Em produção, SEMPRE definir CARDAPIO_CREDENTIAL_SECRET.
    """
    secret = os.environ.get("CARDAPIO_CREDENTIAL_SECRET", "")
    if not secret:
        # Fallback para desenvolvimento — NÃO usar em produção
        db_url = os.environ.get("DATABASE_URL", "") or os.environ.get("POSTGRES_URL", "")
        secret = db_url or "dev-fallback-secret-NOT-SECURE"
        logger.warning(
            "CARDAPIO_CREDENTIAL_SECRET não definida — usando fallback de desenvolvimento. "
            "DEFINIR em produção!"
        )
    return secret


def _derive_fernet_key() -> bytes:
    """Deriva uma chave Fernet (32 bytes base64-url) do secret."""
    secret = _get_secret()
    dk = hashlib.pbkdf2_hmac(
        "sha256",
        secret.encode("utf-8"),
        _APP_SALT,
        100_000,
        dklen=32,
    )
    return base64.urlsafe_b64encode(dk)


def encrypt(plaintext: str) -> str:
    """Criptografa um texto plano e retorna o token Fernet (string)."""
    from cryptography.fernet import Fernet

    key = _derive_fernet_key()
    f = Fernet(key)
    token = f.encrypt(plaintext.encode("utf-8"))
    return token.decode("utf-8")


def decrypt(token: str) -> str:
    """Descriptografa um token Fernet e retorna o texto plano."""
    from cryptography.fernet import Fernet

    key = _derive_fernet_key()
    f = Fernet(key)
    plaintext = f.decrypt(token.encode("utf-8"))
    return plaintext.decode("utf-8")


def mask(value: str, visible_tail: int = 4) -> str:
    """Mascara um valor, mostrando apenas os últimos N caracteres."""
    if not value:
        return ""
    s = str(value)
    if len(s) <= visible_tail:
        return "*" * len(s)
    return "*" * (len(s) - visible_tail) + s[-visible_tail:]
