"""
F5/A4 — Testes da política de dados sensíveis de cartão.

Verifica que dados sensíveis (encrypted_card, CVV, número, etc.) são redacted
em logs e nunca vazam para persistência, APM, auditoria ou cache.

A política é NÃO INVASIVA ao fluxo PIX: nenhum código do PIX é alterado.

Execute com:
    python Cardapio/tests/test_sensitive_data.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CARDAPIO_ROOT = REPO_ROOT / "Cardapio"
sys.path.insert(0, str(CARDAPIO_ROOT))

from cardapio_app.sensitive_data import (  # noqa: E402
    SENSITIVE_FIELD_NAMES,
    assert_no_sensitive,
    redact_sensitive,
    safe_log_dict,
    validate_metadata,
)


# ---------------------------------------------------------------------------
# 1. redact_sensitive substitui campos sensíveis
# ---------------------------------------------------------------------------


def test_redact_encrypted_card() -> None:
    payload = {
        "id": "ORDE_123",
        "charges": [
            {
                "payment_method": {
                    "type": "CREDIT_CARD",
                    "card": {
                        "encrypted": "V++53ir0qvoK/rUSzNjCqP8Hz9ZTa+HohR779n63CV+NvCeYj4J4lQevL4NKN7Di3BxKQGqfQW5cfS7/4rHw4w8URuOV/j/mGau2GXxkKQ6/szJ6BQr//C4e4XgfCHDwcONQhuPDHMdOB1C+4lzyBbsPJUZ/8TUQrxhMMiMFjwGeg62uf7cUqdFjp+Q5dqJXwhLgH3d1EoX+JKStBLqVzF0lW3gHtFOyfvFhuxxBgB0xrzTKfbTqnL5aSYBoGXRFM0gLodMm6knx7bW+syThxyQffnaigCwj2aNohsu+fuXII+3WnlgrHQxaBx3ChRuWKy+loV2L2USiGulp/bPEcg==",
                        "store": False,
                    },
                    "holder": {
                        "name": "Jose da Silva",
                        "tax_id": "65544332211",
                    },
                }
            }
        ],
    }

    redacted = redact_sensitive(payload)

    # Campos sensíveis redacted
    card = redacted["charges"][0]["payment_method"]["card"]
    assert card["encrypted"] == "[REDACTED]", f"encrypted não foi redacted: {card['encrypted']}"
    holder = redacted["charges"][0]["payment_method"]["holder"]
    assert holder["tax_id"] == "[REDACTED]", f"holder.tax_id não foi redacted: {holder['tax_id']}"
    # holder.name (key="name") não é globalmente sensível — "name" é genérico.
    # A política redact holder_name como chave plana, mas não "name" dentro de holder.
    assert holder["name"] == "Jose da Silva", "name genérico não deve ser redacted"

    # Campos não-sensíveis preservados
    assert redacted["id"] == "ORDE_123"
    assert card["store"] is False
    assert redacted["charges"][0]["payment_method"]["type"] == "CREDIT_CARD"

    # Original não foi modificado
    assert payload["charges"][0]["payment_method"]["card"]["encrypted"].startswith("V++")
    print("[OK] 1: redact_sensitive substitui encrypted_card e tax_id por [REDACTED]")


# ---------------------------------------------------------------------------
# 2. redact_sensitive não modifica o original
# ---------------------------------------------------------------------------


def test_redact_nao_modifica_original() -> None:
    original = {"encrypted_card": "SECRETO", "id": "123"}
    redacted = redact_sensitive(original)

    assert original["encrypted_card"] == "SECRETO", "original foi modificado"
    assert redacted["encrypted_card"] == "[REDACTED]"
    assert redacted["id"] == "123"
    print("[OK] 2: redact_sensitive retorna cópia — original não é modificado")


# ---------------------------------------------------------------------------
# 3. redact_sensitive em listas
# ---------------------------------------------------------------------------


def test_redact_em_listas() -> None:
    payload = {
        "charges": [
            {"card": {"encrypted": "SEC1", "number": "4242424242424242"}},
            {"card": {"encrypted": "SEC2", "number": "5555555555554444"}},
        ]
    }
    redacted = redact_sensitive(payload)

    for i, charge in enumerate(redacted["charges"]):
        assert charge["card"]["encrypted"] == "[REDACTED]", f"charge {i} encrypted não redacted"
        assert charge["card"]["number"] == "[REDACTED]", f"charge {i} number não redacted"

    # Original preservado
    assert payload["charges"][0]["card"]["encrypted"] == "SEC1"
    print("[OK] 3: redact_sensitive percorre listas e redact cada item")


# ---------------------------------------------------------------------------
# 4. Padrões de nomes sensíveis
# ---------------------------------------------------------------------------


def test_padroes_nomes_sensiveis() -> None:
    casos = [
        ("encrypted_card", True),
        ("encrypted", True),
        ("security_code", True),
        ("securitycode", True),
        ("cvv", True),
        ("cvc", True),
        ("card_number", True),
        ("cardnumber", True),
        ("holder_tax_id", True),
        ("holder_tax", True),
        ("tax_id", True),
        ("holder_name", True),
        ("exp_month", True),
        ("exp_year", True),
        # Não sensíveis
        ("id", False),
        ("status", False),
        ("amount", False),
        ("currency", False),
        ("brand", False),
        ("last_digits", False),
        ("first_digits", False),
        ("installments", False),
        ("reference_id", False),
        ("store", False),
        ("type", False),
    ]

    from cardapio_app.sensitive_data import _is_sensitive_key

    for key, expected in casos:
        obtained = _is_sensitive_key(key)
        assert obtained == expected, f"{key}: esperado {expected}, obtido {obtained}"
    print(f"[OK] 4: {len(casos)} padrões de nomes sensíveis verificados")


# ---------------------------------------------------------------------------
# 5. safe_log_dict com allowlist
# ---------------------------------------------------------------------------


def test_safe_log_dict_allowlist() -> None:
    data = {
        "id": "ORDE_123",
        "status": "PAID",
        "amount": 500,
        "encrypted_card": "SECRETO",
        "card_number": "4242424242424242",
        "cvv": "123",
    }

    safe = safe_log_dict(data, allowed_keys={"id", "status", "amount"})

    assert safe == {"id": "ORDE_123", "status": "PAID", "amount": 500}
    assert "encrypted_card" not in safe
    assert "card_number" not in safe
    assert "cvv" not in safe
    print("[OK] 5: safe_log_dict exibe apenas chaves da allowlist")


# ---------------------------------------------------------------------------
# 6. assert_no_sensitive detecta vazamento
# ---------------------------------------------------------------------------


def test_assert_no_sensitive_passa_com_redacted() -> None:
    data = {"encrypted_card": "[REDACTED]", "id": "123"}
    # Não deve levantar
    assert_no_sensitive(data)
    print("[OK] 6: assert_no_sensitive passa quando campos sensíveis estão redacted")


def test_assert_no_sensitive_detecta_vazamento() -> None:
    data = {"encrypted_card": "SECRETO", "id": "123"}
    try:
        assert_no_sensitive(data)
    except AssertionError as e:
        assert "encrypted_card" in str(e)
        print("[OK] 6b: assert_no_sensitive detecta campo sensível não-redacted")
        return
    raise AssertionError("deveria ter detectado vazamento")


def test_assert_no_sensitive_ignora_none() -> None:
    data = {"encrypted_card": None, "id": "123"}
    # None não é vazamento
    assert_no_sensitive(data)
    print("[OK] 6c: assert_no_sensitive ignora campos sensíveis com valor None")


def test_assert_no_sensitive_aninhado() -> None:
    data = {
        "charges": [
            {"card": {"encrypted": "SECRETO"}},
        ]
    }
    try:
        assert_no_sensitive(data)
    except AssertionError as e:
        assert "charges" in str(e) or "encrypted" in str(e)
        print("[OK] 6d: assert_no_sensitive detecta vazamento aninhado em listas/dicts")
        return
    raise AssertionError("deveria ter detectado vazamento aninhado")


# ---------------------------------------------------------------------------
# 7. Payload real do PagBank (cartão) é redacted corretamente
# ---------------------------------------------------------------------------


def test_payload_real_pagbank_cartao_redacted() -> None:
    """Simula o payload real de criação de pedido com cartão do PagBank."""
    payload = {
        "reference_id": "ex-00001",
        "customer": {
            "name": "Jose da Silva",
            "email": "email@test.com",
            "tax_id": "12345678909",
        },
        "charges": [
            {
                "reference_id": "ref-cobranca",
                "description": "descricao",
                "amount": {"value": 500, "currency": "BRL"},
                "payment_method": {
                    "type": "CREDIT_CARD",
                    "installments": 1,
                    "capture": True,
                    "card": {
                        "encrypted": "V++53ir0qvoK/rUSzNjCqP8Hz9ZTa+HohR779n63CV+...",
                        "store": False,
                    },
                    "holder": {
                        "name": "Jose da Silva",
                        "tax_id": "65544332211",
                    },
                },
            }
        ],
    }

    redacted = redact_sensitive(payload)

    # Campos não-sensíveis preservados
    assert redacted["reference_id"] == "ex-00001"
    assert redacted["customer"]["email"] == "email@test.com"
    assert redacted["charges"][0]["amount"]["value"] == 500
    assert redacted["charges"][0]["payment_method"]["installments"] == 1
    assert redacted["charges"][0]["payment_method"]["capture"] is True

    # Campos sensíveis redacted
    assert redacted["charges"][0]["payment_method"]["card"]["encrypted"] == "[REDACTED]"
    assert redacted["charges"][0]["payment_method"]["holder"]["tax_id"] == "[REDACTED]"
    # holder.name (key="name") não é globalmente sensível
    assert redacted["charges"][0]["payment_method"]["holder"]["name"] == "Jose da Silva"

    # customer.tax_id é sensível (CPF)
    assert redacted["customer"]["tax_id"] == "[REDACTED]"

    # Nenhum valor sensível no resultado serializado
    serializado = repr(redacted)
    assert "V++53ir0" not in serializado
    assert "65544332211" not in serializado
    assert "12345678909" not in serializado
    print("[OK] 7: payload real do PagBank com cartão é redacted corretamente")


# ---------------------------------------------------------------------------
# 8. Response do PagBank (sem dados sensíveis) não é alterada
# ---------------------------------------------------------------------------


def test_response_pagbank_sem_dados_sensiveis() -> None:
    """A response do PagBank não contém dados sensíveis — redact não altera."""
    response = {
        "id": "ORDE_1E38BD2E-F2CC-4D9C-9727-787CDFBCA7CE",
        "reference_id": "ex-00001",
        "charges": [
            {
                "id": "CHAR_67FC568B-00D8-431D-B2E7-755E3E6C66A0",
                "status": "PAID",
                "amount": {"value": 500, "currency": "BRL"},
                "payment_method": {
                    "type": "CREDIT_CARD",
                    "installments": 1,
                    "card": {
                        "brand": "visa",
                        "first_digits": "411111",
                        "last_digits": "1111",
                        "exp_month": "12",
                        "exp_year": "2026",
                        "store": False,
                    },
                },
            }
        ],
    }

    redacted = redact_sensitive(response)

    # first_digits e last_digits NÃO são sensíveis (são mascarados pelo PSP)
    assert redacted["charges"][0]["payment_method"]["card"]["first_digits"] == "411111"
    assert redacted["charges"][0]["payment_method"]["card"]["last_digits"] == "1111"
    assert redacted["charges"][0]["payment_method"]["card"]["brand"] == "visa"

    # exp_month e exp_year SÃO sensíveis
    assert redacted["charges"][0]["payment_method"]["card"]["exp_month"] == "[REDACTED]"
    assert redacted["charges"][0]["payment_method"]["card"]["exp_year"] == "[REDACTED]"
    print("[OK] 8: response do PagBank — first/last_digits preservados, exp_month/year redacted")


# ---------------------------------------------------------------------------
# 9. SENSITIVE_FIELD_NAMES contém os campos esperados
# ---------------------------------------------------------------------------


def test_sensitive_field_names_completo() -> None:
    esperados = {
        "encrypted_card",
        "encrypted",
        "security_code",
        "cvv",
        "cvc",
        "card_number",
        "number",
        "holder_tax_id",
        "tax_id",
        "exp_month",
        "exp_year",
        "holder_name",
    }
    assert esperados.issubset(SENSITIVE_FIELD_NAMES), (
        f"campos faltando: {esperados - SENSITIVE_FIELD_NAMES}"
    )
    print(f"[OK] 9: SENSITIVE_FIELD_NAMES contém os {len(esperados)} campos esperados")


# ---------------------------------------------------------------------------
# 10. Não altera o fluxo PIX — payload PIX não tem campos sensíveis
# ---------------------------------------------------------------------------


def test_payload_pix_nao_e_alterado() -> None:
    """Payload do PIX não contém dados de cartão — redact não altera nada."""
    pix_payload = {
        "id": "ORDE_F87334AC",
        "reference_id": "ex-00001",
        "charges": [
            {
                "id": "CHAR_F1F10115",
                "status": "PAID",
                "amount": {"value": 500, "currency": "BRL"},
                "payment_method": {"type": "PIX"},
            }
        ],
        "qr_codes": [
            {
                "id": "qrcode-1",
                "text": "00020126BR.GOV.BCB.PIX",
                "expires_at": "2026-08-24T15:00:00-03:00",
            }
        ],
    }

    redacted = redact_sensitive(pix_payload)

    # Tudo preservado — PIX não tem dados sensíveis de cartão
    assert redacted == pix_payload
    print("[OK] 10: payload PIX não é alterado pela política A4 (não-invasiva)")


# ---------------------------------------------------------------------------
# 11. validate_metadata — guard para persistência
# ---------------------------------------------------------------------------


def test_validate_metadata_aceita_seguro() -> None:
    metadata = {"description": "Pedido 123", "charge_id": "CHAR_ABC"}
    result = validate_metadata(metadata)
    assert result == metadata
    print("[OK] 11: validate_metadata aceita metadata sem campos sensíveis")


def test_validate_metadata_none_retorna_none() -> None:
    assert validate_metadata(None) is None
    print("[OK] 11b: validate_metadata(None) retorna None")


def test_validate_metadata_rejeita_encrypted_card() -> None:
    metadata = {"description": "Pedido 123", "encrypted_card": "SECRETO"}
    try:
        validate_metadata(metadata)
    except ValueError as e:
        assert "encrypted_card" in str(e)
        print("[OK] 11c: validate_metadata rejeita encrypted_card com ValueError")
        return
    raise AssertionError("deveria ter rejeitado encrypted_card")


def test_validate_metadata_rejeita_cvv() -> None:
    metadata = {"cvv": "123"}
    try:
        validate_metadata(metadata)
    except ValueError as e:
        assert "cvv" in str(e)
        print("[OK] 11d: validate_metadata rejeita cvv com ValueError")
        return
    raise AssertionError("deveria ter rejeitado cvv")


def test_validate_metadata_rejeita_multiplos() -> None:
    metadata = {"description": "ok", "encrypted_card": "SEC", "card_number": "4242", "cvv": "123"}
    try:
        validate_metadata(metadata)
    except ValueError as e:
        msg = str(e)
        assert "encrypted_card" in msg
        assert "card_number" in msg
        assert "cvv" in msg
        assert "description" not in msg, "campo seguro não deve estar na lista de rejeitados"
        print("[OK] 11e: validate_metadata rejeita múltiplos campos e lista todos")
        return
    raise AssertionError("deveria ter rejeitado múltiplos campos sensíveis")


def test_validate_metadata_rejeita_tipo_invalido() -> None:
    try:
        validate_metadata("não é dict")  # type: ignore
    except TypeError as e:
        assert "dict" in str(e)
        print("[OK] 11f: validate_metadata rejeita tipo não-dict com TypeError")
        return
    raise AssertionError("deveria ter rejeitado tipo inválido")


def test_validate_metadata_charge_id_e_seguro() -> None:
    """charge_id é necessário para estorno (R3) e NÃO é sensível."""
    metadata = {"charge_id": "CHAR_67FC568B-00D8-431D-B2E7-755E3E6C66A0", "nsu": "032416400102"}
    result = validate_metadata(metadata)
    assert result == metadata
    print("[OK] 11g: validate_metadata aceita charge_id e nsu (não-sensíveis, necessários para estorno)")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


def main() -> int:
    testes = [
        test_redact_encrypted_card,
        test_redact_nao_modifica_original,
        test_redact_em_listas,
        test_padroes_nomes_sensiveis,
        test_safe_log_dict_allowlist,
        test_assert_no_sensitive_passa_com_redacted,
        test_assert_no_sensitive_detecta_vazamento,
        test_assert_no_sensitive_ignora_none,
        test_assert_no_sensitive_aninhado,
        test_payload_real_pagbank_cartao_redacted,
        test_response_pagbank_sem_dados_sensiveis,
        test_sensitive_field_names_completo,
        test_payload_pix_nao_e_alterado,
        test_validate_metadata_aceita_seguro,
        test_validate_metadata_none_retorna_none,
        test_validate_metadata_rejeita_encrypted_card,
        test_validate_metadata_rejeita_cvv,
        test_validate_metadata_rejeita_multiplos,
        test_validate_metadata_rejeita_tipo_invalido,
        test_validate_metadata_charge_id_e_seguro,
    ]

    falhas = 0
    for t in testes:
        try:
            t()
        except Exception as e:  # noqa: BLE001
            falhas += 1
            print(f"[FALHOU] {t.__name__}: {e}")

    print("-" * 70)
    if falhas:
        print(f"{falhas} de {len(testes)} teste(s) falharam")
        return 1
    print(f"{len(testes)} testes passaram")
    return 0


if __name__ == "__main__":
    sys.exit(main())
