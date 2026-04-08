from __future__ import annotations

import hashlib
import os
import secrets
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from .. import core


OpsRole = Literal["KDS", "LOGISTICA"]


@dataclass(frozen=True)
class OpsUser:
    id: int
    username: str
    role: OpsRole
    nome: str | None
    telefone: str | None
    telegram: str | None
    endereco: str | None
    pix: str | None
    ativo: bool
    criado_em: str


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _hash_password(password: str, salt_hex: str) -> str:
    pwd = (password or "").encode("utf-8")
    salt = bytes.fromhex(salt_hex)
    dk = hashlib.pbkdf2_hmac("sha256", pwd, salt, 120_000)
    return dk.hex()


def create_password_hash(password: str) -> tuple[str, str]:
    salt = secrets.token_bytes(16).hex()
    return salt, _hash_password(password, salt)


def verify_password(password: str, salt_hex: str, hash_hex: str) -> bool:
    try:
        got = _hash_password(password, salt_hex)
        return secrets.compare_digest(got, str(hash_hex or ""))
    except Exception:
        return False


def ensure_default_admin_if_empty(ctx: core.AppContext) -> None:
    username = str(os.environ.get("OPS_ADMIN_USERNAME") or "").strip()
    password = str(os.environ.get("OPS_ADMIN_PASSWORD") or "").strip()
    if not username or not password:
        return

    if core.pg_enabled():
        try:
            existing = core.pg_store.get_ops_user_by_username(username=username)
        except Exception:
            existing = None
        if isinstance(existing, dict) and int(existing.get("id") or 0) > 0:
            return

        salt, pwd_hash = create_password_hash(password)
        try:
            core.pg_store.create_ops_user(
                username=username,
                role="KDS",
                nome="ADMIN",
                telefone=None,
                telegram=None,
                endereco=None,
                pix=None,
                password_salt=salt,
                password_hash=pwd_hash,
            )
        except Exception:
            return


def auth_user(username: str, password: str) -> dict[str, Any] | None:
    u = str(username or "").strip().lower()
    p = str(password or "")
    if not u or not p:
        return None

    if not core.pg_enabled():
        return None

    try:
        rec = core.pg_store.get_ops_user_by_username(username=u)
    except Exception:
        rec = None

    if not isinstance(rec, dict):
        return None

    if bool(rec.get("ativo")) is False:
        return None

    salt = str(rec.get("password_salt") or "").strip()
    h = str(rec.get("password_hash") or "").strip()
    if not salt or not h:
        return None

    if not verify_password(p, salt, h):
        return None

    return rec
