from __future__ import annotations

import base64
import hashlib
import hmac
import io
import json
import logging
import mimetypes
import os
import re
import secrets
import threading
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from flask import jsonify, make_response, request, send_file, send_from_directory
from werkzeug.utils import secure_filename

from . import payment_methods

try:
    import pg_store
except Exception as e:
    _PG_STORE_IMPORT_ERROR = repr(e)
    pg_store = None
else:
    _PG_STORE_IMPORT_ERROR = ""

logger = logging.getLogger(__name__)

ALLOWED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
ALLOWED_COMPROVANTE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".pdf", ".jfif", ".heic", ".heif"}
# Modalidades de pagamento: espelho da fonte única de verdade.
# Ver cardapio_app/payment_methods.py e PDV/app/core/payment_methods.py
ALLOWED_PAYMENT_METHODS = set(payment_methods.ALLOWED_PAYMENT_METHODS)


@dataclass(frozen=True)
class AppContext:
    bundle_dir: Path
    data_dir: Path
    data_file: Path
    catalogo_publicado_file: Path
    assets_dir: Path
    mesas_file: Path
    solicitacoes_file: Path


def build_context(*, bundle_dir: Path | None = None) -> AppContext:
    bd = (bundle_dir or Path(os.environ.get("CARDAPIO_BUNDLE_DIR") or Path(__file__).resolve().parent.parent)).resolve()
    data_dir = Path(os.environ.get("CARDAPIO_DATA_DIR") or bd).resolve()
    data_dir.mkdir(parents=True, exist_ok=True)

    return AppContext(
        bundle_dir=bd,
        data_dir=data_dir,
        data_file=data_dir / "produtos.json",
        catalogo_publicado_file=data_dir / "catalogo_publicado.json",
        assets_dir=data_dir / "assets",
        mesas_file=data_dir / "mesas.json",
        solicitacoes_file=data_dir / "solicitacoes.json",
    )


def pdv_key() -> str:
    return os.environ.get("PDV_KEY", "")


def promo_hmac_secret() -> str:
    return str(os.environ.get("PROMO_HMAC_SECRET") or "").strip()


def promo_enabled_flag() -> str:
    return str(os.environ.get("PROMO_ENABLED") or "").strip().lower()


def promo_public_base_url() -> str:
    raw = str(os.environ.get("CARDAPIO_PUBLIC_BASE_URL") or os.environ.get("PROMO_PUBLIC_BASE_URL") or "").strip()
    if not raw:
        return ""

    base = raw.strip().rstrip("/")
    low = base.lower()
    if low.startswith("http://") or low.startswith("https://"):
        return base

    # Se cair aqui, pode ser um valor sem esquema (ex.: dominio.com) ou algo perigoso
    # como uma string de conexão (ex.: postgresql://...).
    if "://" in base:
        return ""

    return f"https://{base}"


def promo_path() -> str:
    p = str(os.environ.get("PROMO_PATH") or "/promocao").strip()
    return p or "/promocao"


def promo_consent_text() -> str:
    return str(
        os.environ.get("PROMO_CONSENT_TEXT")
        or "AO CLICAR EM CONFIRMAR, VOCÊ AUTORIZA O ENVIO DE OFERTAS, PROMOÇÕES E COMUNICAÇÕES DA LANCHONETE DO’RAFA POR MEIO DE WHATSAPP OU OUTROS CANAIS. VOCÊ PODE CANCELAR O RECEBIMENTO A QUALQUER MOMENTO."
    ).strip()


def telegram_bot_token() -> str:
    return os.environ.get("TELEGRAM_BOT_TOKEN", "")


def telegram_chat_id() -> str:
    return os.environ.get("TELEGRAM_CHAT_ID", "")


def telegram_bot_enabled() -> bool:
    token = str(os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()
    return bool(token)


def central_logistica_webhook_url() -> str:
    return os.environ.get("CENTRAL_LOGISTICA_WEBHOOK_URL", "")


def central_logistica_api_key() -> str:
    return os.environ.get("CENTRAL_LOGISTICA_API_KEY", "")


def central_logistica_empresa_id() -> str:
    return os.environ.get("CENTRAL_LOGISTICA_EMPRESA_ID", "EMPRESA01")


def central_logistica_timeout_seconds() -> float:
    try:
        return float(os.environ.get("CENTRAL_LOGISTICA_TIMEOUT_SECONDS", "5.0"))
    except Exception:
        return 5.0


def central_logistica_retry_enabled() -> bool:
    v = str(os.environ.get("CENTRAL_LOGISTICA_RETRY_ENABLED") or "").strip().lower()
    return v in ("1", "true", "yes", "y", "on")


def central_logistica_enabled() -> bool:
    url = str(central_logistica_webhook_url() or "").strip()
    return bool(url)


def central_logistica_post_json(*, path: str, payload: dict[str, Any] | None = None, timeout: float | None = None) -> tuple[int, Any]:
    """Faz POST JSON na REMO e retorna (status_code, body_json)."""
    base_url = str(central_logistica_webhook_url() or "").strip().rstrip("/")
    if not base_url:
        return 0, None

    url = f"{base_url}{path}"
    data = json.dumps(payload or {}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url=url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "x-api-key": str(central_logistica_api_key() or "").strip(),
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout or central_logistica_timeout_seconds()) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return int(resp.status), (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            body = json.loads(raw) if raw else None
        except Exception:
            body = None
        return int(e.code), body
    except Exception:
        logger.exception("Erro ao chamar REMO: %s", url)
        return 0, None


def pdv_products_url() -> str:
    return os.environ.get("PDV_PRODUCTS_URL", "http://127.0.0.1:5600/api/produtos?ativos=1")


def pg_enabled() -> bool:
    if pg_store is None:
        return False
    try:
        return bool(pg_store.is_enabled())
    except Exception:
        return False


def database_url_configured() -> bool:
    return bool(str(os.environ.get("DATABASE_URL") or "").strip())


def telegram_enabled() -> bool:
    token = str(os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()
    chat_id = str(os.environ.get("TELEGRAM_CHAT_ID") or "").strip()
    return bool(token and chat_id)


def admin_enabled() -> bool:
    v = str(os.environ.get("CARDAPIO_ADMIN_ENABLED") or "").strip().lower()
    if v in ("1", "true", "yes", "y", "on"):
        return True
    if v in ("0", "false", "no", "n", "off"):
        return False
    return not pg_enabled()


def init_pg_if_enabled() -> None:
    if not pg_enabled():
        return
    try:
        pg_store.init_db()
        pg_store.ensure_default_mesas(max_mesas=30)
    except Exception:
        pass


def pg_store_import_error() -> str:
    return _PG_STORE_IMPORT_ERROR or ""


def bootstrap_file_if_missing(*, src: Path, dst: Path) -> None:
    try:
        if dst.exists():
            return
        if not src.exists() or not src.is_file():
            return
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(src.read_bytes())
    except Exception:
        pass


def read_json_file(path: Path) -> Any:
    if not path.exists():
        raise FileNotFoundError(str(path))
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json_file(path: Path, data: Any) -> None:
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    tmp_path.replace(path)


def ensure_catalogo_publicado_file(ctx: AppContext) -> dict[str, Any]:
    bootstrap_file_if_missing(src=(ctx.bundle_dir / "catalogo_publicado.json"), dst=ctx.catalogo_publicado_file)
    if not ctx.catalogo_publicado_file.exists():
        write_json_file(ctx.catalogo_publicado_file, {"categorias": [], "produtos": [], "ui": {}})

    data = read_json_file(ctx.catalogo_publicado_file)
    if not isinstance(data, dict):
        data = {"categorias": [], "produtos": [], "ui": {}}
    if not isinstance(data.get("categorias"), list):
        data["categorias"] = []
    if not isinstance(data.get("produtos"), list):
        data["produtos"] = []
    if not isinstance(data.get("ui"), dict):
        data["ui"] = {}
    return data


def read_catalogo_publicado(ctx: AppContext) -> dict[str, Any]:
    if pg_enabled():
        try:
            rec = pg_store.get_catalogo_publicado()
            if isinstance(rec, dict):
                return rec
        except Exception:
            pass
    return ensure_catalogo_publicado_file(ctx)


def _weekday_key_from_datetime(dt: datetime) -> str:
    wd = int(dt.weekday())
    if wd == 0:
        return "seg"
    if wd == 1:
        return "ter"
    if wd == 2:
        return "qua"
    if wd == 3:
        return "qui"
    if wd == 4:
        return "sex"
    if wd == 5:
        return "sab"
    return "dom"


def get_local_now(*, tz_name: str | None) -> datetime:
    tz_raw = str(tz_name or "").strip() or "America/Sao_Paulo"
    try:
        from zoneinfo import ZoneInfo

        return datetime.now(ZoneInfo(tz_raw))
    except Exception:
        return datetime.now()


def filter_catalogo_items_by_weekday(*, items: list[dict[str, Any]], tz_name: str | None) -> list[dict[str, Any]]:
    if not isinstance(items, list):
        return []

    now = get_local_now(tz_name=tz_name)
    wd_key = _weekday_key_from_datetime(now)

    map_field = {
        "seg": "cardapioSeg",
        "ter": "cardapioTer",
        "qua": "cardapioQua",
        "qui": "cardapioQui",
        "sex": "cardapioSex",
        "sab": "cardapioSab",
        "dom": "cardapioDom",
    }
    field = map_field.get(wd_key) or "cardapioSeg"

    out: list[dict[str, Any]] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        # Retrocompatibilidade: se não existir campo do dia, assume True.
        if it.get(field) is None:
            out.append(it)
            continue
        if bool(it.get(field)):
            out.append(it)
    return out


def save_catalogo_publicado(*, ctx: AppContext, record: dict[str, Any]) -> None:
    if not isinstance(record, dict):
        return
    if pg_enabled():
        pg_store.save_catalogo_publicado(record=record)
        return
    write_json_file(ctx.catalogo_publicado_file, record)


def fetch_pdv_payload() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    url = str(pdv_products_url() or "").strip()
    if not url:
        return [], {}
    req = urllib.request.Request(
        url=url,
        headers={
            "Accept": "application/json",
            "X-PDV-KEY": str(pdv_key() or ""),
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            raw = resp.read().decode("utf-8")
            j = json.loads(raw) if raw else {}
            if not isinstance(j, dict):
                return [], {}
            arr = j.get("produtos")
            produtos = arr if isinstance(arr, list) else []
            ui = j.get("ui") if isinstance(j.get("ui"), dict) else {}
            return produtos, ui
    except Exception:
        return [], {}


def normalize_asset_ref(ctx: AppContext, value: Any) -> str:
    if value is None:
        return ""
    s = str(value).strip()
    if not s:
        return ""

    s = s.replace("\\\\", "/")
    s = s.replace("\\", "/")

    low = s.lower()
    if low.startswith("http://") or low.startswith("https://"):
        return s

    if s.startswith("/assets/"):
        return s
    if s.startswith("assets/"):
        return "/" + s

    m = re.search(r"/assets/[^/]+$", s, flags=re.IGNORECASE)
    if m:
        return m.group(0)

    if re.match(r"^[a-zA-Z]:/", s):
        name = Path(s).name
        return f"/assets/{name}" if name else ""

    base = s.strip("/")
    base = base.split("/")[-1] if base else ""
    if base and "." not in base:
        for ext in sorted(ALLOWED_IMAGE_EXTENSIONS):
            candidate = ctx.assets_dir / f"{base}{ext}"
            if candidate.exists():
                return f"/assets/{base}{ext}"

    return s


def normalize_section_name(value: Any) -> str:
    s = str(value or "").strip()
    if not s:
        return "Produtos"
    s = re.sub(r"\s+", " ", s)
    return s


def section_id_from_name(name: str) -> str:
    base = str(name or "").strip().lower()
    base = re.sub(r"\s+", "_", base)
    base = re.sub(r"[^a-z0-9_\-]", "", base)
    base = base.strip("_-")
    if not base or base == "produtos":
        return "produtos"
    return f"sec_{base}"


def is_allowed_image_upload_filename(filename: str) -> bool:
    name = str(filename or "").strip().lower()
    ext = Path(name).suffix
    return bool(ext) and ext in ALLOWED_IMAGE_EXTENSIONS


def is_allowed_image(filename: str) -> bool:
    ext = Path(filename).suffix.lower()
    return ext in ALLOWED_IMAGE_EXTENSIONS


def is_valid_whatsapp(value: Any) -> bool:
    s = re.sub(r"\D+", "", str(value or "").strip())
    if len(s) < 10:
        return False
    if len(s) > 13:
        return False
    return True


def whatsapp_digits(value: Any) -> str:
    digits = re.sub(r"\D+", "", str(value or "").strip())
    if not digits:
        return ""
    # Add Brazilian country code (55) if not present
    if not digits.startswith("55"):
        digits = "55" + digits
    return digits


def whatsapp_default_message(*, context: str | None = None, record: dict[str, Any] | None = None) -> str:
    _ = str(context or "").strip().lower()
    base_msg = "Olá! 😊 Estamos entrando em contato sobre seu pedido, você pode acompanhar o status dele pelo link."
    
    if record and isinstance(record, dict):
        access_token = str(record.get("access_token") or "").strip()
        if access_token:
            base_url = promo_base_url()
            tracking_url = f"{base_url}/status/{urllib.parse.quote(access_token)}"
            base_msg += f"\n\nAcompanhe seu pedido:\n{tracking_url}"
    
    return base_msg


def whatsapp_wa_me_url(*, phone: Any, message: str | None = None) -> str:
    digits = whatsapp_digits(phone)
    if not digits:
        return ""
    url = f"https://wa.me/{digits}"
    msg = str(message or "").strip()
    if not msg:
        return url
    try:
        q = urllib.parse.quote(msg)
    except Exception:
        q = ""
    return url + (f"?text={q}" if q else "")


def is_localhost() -> bool:
    ip = (request.remote_addr or "").strip()
    return ip in ("127.0.0.1", "::1")


def require_localhost() -> Any:
    if not is_localhost():
        return jsonify({"error": "forbidden"}), 403
    return None


def require_pdv_key() -> Any:
    key_env = pdv_key()
    if not key_env:
        return jsonify({"error": "pdv_key_nao_configurada"}), 500
    key = (request.headers.get("X-PDV-KEY") or "").strip()
    if not key or key != key_env:
        return jsonify({"error": "unauthorized"}), 401
    expected_id = str(os.environ.get("CARDAPIO_PDV_ID") or "").strip().upper()
    if expected_id:
        got_id = str(request.headers.get("X-PDV-ID") or "").strip().upper()
        if not got_id or got_id != expected_id:
            return jsonify({"error": "unauthorized"}), 401
    return None


def telegram_send_message(text: str) -> bool:
    if not telegram_enabled():
        return False

    token = str(os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()
    chat_id = str(os.environ.get("TELEGRAM_CHAT_ID") or "").strip()
    if not token or not chat_id:
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": str(text or "").strip()[:3900],
        "disable_web_page_preview": True,
    }
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url=url,
        data=raw,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=2.5) as resp:
            ok = int(getattr(resp, "status", 0) or 0) == 200
            return ok
    except Exception:
        logger.exception("Falha ao enviar mensagem no Telegram")
        return False


def telegram_send_message_to(*, chat_id: str, text: str) -> bool:
    if not telegram_bot_enabled():
        return False

    token = str(os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()
    cid = str(chat_id or "").strip()
    if not token or not cid:
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": cid,
        "text": str(text or "").strip()[:3900],
        "disable_web_page_preview": True,
    }
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url=url,
        data=raw,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=2.5) as resp:
            ok = int(getattr(resp, "status", 0) or 0) == 200
            return ok
    except Exception:
        logger.exception("Falha ao enviar mensagem no Telegram")
        return False


def format_telegram_new_order_message(record: dict[str, Any]) -> str:
    def _digits_only(raw: str) -> str:
        return "".join([ch for ch in str(raw or "") if ch.isdigit()])

    def _money_brl(v: float) -> str:
        return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    kind = str(record.get("kind") or "").strip().upper()
    rid = str(record.get("id") or record.get("pedido_id") or record.get("order_id") or "").strip()
    mesa = record.get("mesa")
    pagamento = str(record.get("pagamento_preferido") or "").strip().upper()
    tipo_entrega = str(record.get("tipo_entrega") or "").strip().upper()
    created = str(record.get("criado_em") or "").strip()

    data_br = ""
    try:
        if created:
            s = created.replace(" ", "T")
            s = s.split("+")[0].split("Z")[0]
            dt = __import__("datetime").datetime.fromisoformat(s)
            data_br = dt.strftime("%d/%m/%Y")
    except Exception:
        data_br = ""

    cliente_nome = str(record.get("cliente_nome") or "").strip()
    whatsapp = _digits_only(str(record.get("cliente_whatsapp") or "").strip())
    endereco = record.get("endereco") if isinstance(record.get("endereco"), dict) else None

    localizacao = ""
    referencia = ""
    if mesa is not None:
        localizacao = f"Mesa {mesa}"
    elif endereco:
        maps_url = str(endereco.get("maps_url") or endereco.get("maps") or endereco.get("localizacao") or "").strip()
        if maps_url:
            localizacao = maps_url
        referencia = str(endereco.get("referencia") or "").strip()

    lines: list[str] = []
    lines.append("NOVO PEDIDO")
    lines.append(f"Data: {data_br}" if data_br else "Data: ")
    lines.append("")
    lines.append(f"Cliente: {cliente_nome}")
    lines.append(f"WhatsApp: {whatsapp}")

    wa_url = whatsapp_wa_me_url(phone=whatsapp, message=whatsapp_default_message(context="pedido", record=record))
    if wa_url:
        lines.append(f"Falar com o cliente: {wa_url}")
    lines.append("")

    itens = record.get("itens") if isinstance(record.get("itens"), list) else []
    lines.append("Itens:")
    for it in itens:
        if not isinstance(it, dict):
            continue
        nome = str(it.get("nome") or "").strip()
        code = str(it.get("product_code") or it.get("pdvCode") or "").strip()
        try:
            qty = float(it.get("qty") or it.get("quantidade") or 0)
        except Exception:
            qty = 0

        unit_price_raw = it.get("unit_price")
        if unit_price_raw is None:
            unit_price_raw = it.get("preco")
        try:
            unit_price = float(unit_price_raw) if unit_price_raw is not None else None
        except Exception:
            unit_price = None

        label = nome or code or "(item)"
        if unit_price is not None and unit_price >= 0:
            lines.append(f"- {qty:g} x {label} ({_money_brl(unit_price)})")
        else:
            lines.append(f"- {qty:g} x {label}")

    total = record.get("total")
    if total is None:
        total = record.get("total_estimado")
    try:
        total_f = float(total) if total is not None else None
    except Exception:
        total_f = None

    taxa = record.get("taxa_entrega")
    try:
        taxa_f = float(taxa) if taxa is not None else None
    except Exception:
        taxa_f = None

    lines.append("")
    lines.append(f"Total: R$ {_money_brl(total_f)}" if total_f is not None else "Total: ")
    if taxa_f is not None:
        lines.append(f"Taxa de entrega: R$ {_money_brl(taxa_f)}")
    lines.append("")
    lines.append("")
    lines.append("Tipo de Pagamento:")
    lines.append(payment_methods.display_name(pagamento))
    if pagamento == "DINHEIRO":
        troco_para = record.get("troco_para")
        if troco_para is not None and str(troco_para).strip() != "":
            try:
                tp = float(troco_para)
            except Exception:
                tp = None
            if tp is not None and tp > 0:
                lines.append(f"Troco para: R$ {_money_brl(tp)}")
    lines.append("")
    lines.append("Tipo de entrega:")
    if tipo_entrega:
        lines.append(tipo_entrega)
    elif kind == "DELIVERY":
        lines.append("DELIVERY")
    elif mesa is not None:
        lines.append("SALAO")
    else:
        lines.append("")

    lines.append("")
    lines.append("Localização:")
    lines.append(localizacao)
    lines.append("")
    lines.append("Referencia:")
    lines.append(referencia)

    lines.append("")
    lines.append("ID do pedido:")
    lines.append(rid)

    # Adicionar link de acompanhamento se houver access_token
    access_token = str(record.get("access_token") or "").strip()
    if access_token:
        base_url = promo_base_url()
        tracking_url = f"{base_url}/status/{urllib.parse.quote(access_token)}"
        lines.append("")
        lines.append("Acompanhar pedido:")
        lines.append(tracking_url)

    return "\n".join(lines).strip()


def notify_telegram_new_order(record: dict[str, Any]) -> None:
    if not telegram_enabled():
        return

    def _worker() -> None:
        try:
            msg = format_telegram_new_order_message(record)
            if msg:
                telegram_send_message(msg)
        except Exception:
            logger.exception("Falha ao notificar Telegram (novo pedido)")

    try:
        threading.Thread(target=_worker, daemon=True).start()
    except Exception:
        _worker()


def promo_enabled() -> bool:
    enabled = promo_enabled_flag()
    if enabled in ("1", "true", "yes", "y", "on"):
        return True
    if enabled in ("0", "false", "no", "n", "off"):
        return False
    return bool(promo_hmac_secret())


def promo_base_url() -> str:
    base = promo_public_base_url()
    if base:
        return base.rstrip("/")
    return str(request.host_url or "").rstrip("/")


def b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")


def b64url_decode(txt: str) -> bytes:
    s = str(txt or "").strip()
    if not s:
        return b""
    pad = "=" * ((4 - (len(s) % 4)) % 4)
    return base64.urlsafe_b64decode((s + pad).encode("utf-8"))


def promo_make_token(*, payload: dict[str, Any]) -> str:
    secret = promo_hmac_secret()
    if not secret:
        raise RuntimeError("promo_secret_nao_configurado")
    payload_json = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    sig = hmac.new(secret.encode("utf-8"), payload_json, hashlib.sha256).digest()
    return b64url_encode(payload_json) + "." + b64url_encode(sig)


def promo_make_short_token() -> str:
    while True:
        tok = secrets.token_urlsafe(9).strip()
        tok = tok.replace("-", "").replace("_", "").strip()
        if tok and "." not in tok and len(tok) >= 10:
            return tok


def mask_name(value: Any) -> str:
    s = str(value or "").strip()
    if not s:
        return ""
    parts = [p for p in s.split() if p]
    if len(parts) >= 2:
        first = parts[0]
        last_initial = parts[-1][:1]
        return f"{first} {last_initial}****"
    base = parts[0]
    if len(base) <= 2:
        return base[:1] + "****"
    return base[:2] + "****"


def mask_phone(value: Any) -> str:
    raw = re.sub(r"\D+", "", str(value or "").strip())
    if not raw:
        return ""
    tail = raw[-4:] if len(raw) >= 4 else raw
    return ("*" * max(0, len(raw) - len(tail))) + tail


def promo_title_from_ui(ui: Any) -> str:
    if not isinstance(ui, dict):
        return "Promoção"
    for k in ("promoTitle", "promoName", "promoCampaignName", "campaignName"):
        v = str(ui.get(k) or "").strip()
        if v:
            return v
    return "Promoção"


def promo_parse_and_verify_token(*, token: str) -> dict[str, Any] | None:
    secret = promo_hmac_secret()
    if not secret:
        return None
    tok = str(token or "").strip()
    if not tok or "." not in tok:
        return None
    p64, s64 = tok.split(".", 1)
    try:
        payload_raw = b64url_decode(p64)
        sig_raw = b64url_decode(s64)
    except Exception:
        return None

    expected_sig = hmac.new(secret.encode("utf-8"), payload_raw, hashlib.sha256).digest()
    if not hmac.compare_digest(expected_sig, sig_raw):
        return None

    try:
        obj = json.loads(payload_raw.decode("utf-8")) if payload_raw else None
    except Exception:
        obj = None
    return dict(obj) if isinstance(obj, dict) else None


def promo_get_sale_id_from_token(tok: str) -> int | None:
    t = str(tok or "").strip()
    if not t:
        return None
    if "." in t:
        payload = promo_parse_and_verify_token(token=t)
        if not isinstance(payload, dict):
            return None
        try:
            return int(payload.get("sale_id"))
        except Exception:
            return None
    try:
        rec0 = pg_store.get_promo_inscricao_by_token(token=t)
    except Exception:
        rec0 = None
    if not isinstance(rec0, dict):
        return None
    try:
        return int(rec0.get("sale_id"))
    except Exception:
        return None


def ensure_mesas_file(ctx: AppContext) -> dict[str, Any]:
    if pg_enabled():
        mp = {}
        try:
            mp = pg_store.get_table_token_map()
        except Exception:
            mp = {}
        mesas = []
        for mesa in range(1, 31):
            tok = str(mp.get(mesa) or "").strip()
            if tok:
                mesas.append({"mesa": mesa, "token": tok})
        return {"mesas": mesas}

    bootstrap_file_if_missing(src=(ctx.bundle_dir / "mesas.json"), dst=ctx.mesas_file)
    if not ctx.mesas_file.exists():
        write_json_file(ctx.mesas_file, {"mesas": []})

    data = read_json_file(ctx.mesas_file)
    if not isinstance(data, dict):
        data = {"mesas": []}

    mesas = data.get("mesas")
    if not isinstance(mesas, list):
        mesas = []
        data["mesas"] = mesas

    if len(mesas) == 0:
        mesas = []
        for n in range(1, 31):
            mesas.append({"mesa": n, "token": secrets.token_urlsafe(24)})
        data["mesas"] = mesas
        write_json_file(ctx.mesas_file, data)

    return data


def get_table_token_map(ctx: AppContext) -> dict[int, str]:
    if pg_enabled():
        try:
            return pg_store.get_table_token_map()
        except Exception:
            return {}

    data = ensure_mesas_file(ctx)
    out: dict[int, str] = {}
    for m in data.get("mesas", []):
        try:
            mesa = int(m.get("mesa"))
        except Exception:
            continue
        token = str(m.get("token") or "").strip()
        if mesa > 0 and token:
            out[mesa] = token
    return out


def validate_table_token(*, ctx: AppContext, mesa: Any, token: Any) -> tuple[bool, str]:
    try:
        mesa_i = int(mesa)
    except Exception:
        return False, "mesa_invalida"

    if mesa_i < 1 or mesa_i > 30:
        return False, "mesa_fora_do_intervalo"

    tok = str(token or "").strip()
    if not tok:
        return False, "token_ausente"

    mp = get_table_token_map(ctx)
    expected = mp.get(mesa_i)
    if not expected:
        return False, "mesa_nao_cadastrada"
    if tok != expected:
        logger.warning(
            "token_invalido (remote=%s mesa=%s tok_prefix=%s expected_prefix=%s)",
            (request.remote_addr or "").strip(),
            mesa_i,
            tok[:8],
            expected[:8],
        )
        return False, "token_invalido"

    return True, ""


def ensure_solicitacoes_file(ctx: AppContext) -> dict[str, Any]:
    if pg_enabled():
        return {"solicitacoes": []}

    if not ctx.solicitacoes_file.exists():
        write_json_file(ctx.solicitacoes_file, {"solicitacoes": []})
    data = read_json_file(ctx.solicitacoes_file)
    if not isinstance(data, dict):
        data = {"solicitacoes": []}
    if not isinstance(data.get("solicitacoes"), list):
        data["solicitacoes"] = []
    return data


def save_solicitacoes(ctx: AppContext, data: dict[str, Any]) -> None:
    if pg_enabled():
        arr = data.get("solicitacoes")
        if isinstance(arr, list):
            for s in arr:
                if isinstance(s, dict):
                    try:
                        pg_store.save_solicitacao(record=s)
                    except Exception:
                        pass
        return

    write_json_file(ctx.solicitacoes_file, data)


def find_solicitacao(ctx: AppContext, data: dict[str, Any], solicitacao_id: str) -> tuple[int, dict[str, Any]] | tuple[None, None]:
    if pg_enabled():
        try:
            s = pg_store.get_solicitacao(solicitacao_id=str(solicitacao_id or "").strip())
        except Exception:
            s = None
        if isinstance(s, dict):
            return 0, s
        return None, None

    arr = data.get("solicitacoes")
    if not isinstance(arr, list):
        return None, None
    for i, s in enumerate(arr):
        if isinstance(s, dict) and str(s.get("id")) == str(solicitacao_id):
            return i, s
    return None, None


def documents_dir() -> Path:
    userprofile = os.environ.get("USERPROFILE")
    home = Path(userprofile) if userprofile else Path.home()

    candidates = [home / "Documents", home / "Documentos"]
    for c in candidates:
        if c.exists():
            return c
    return candidates[0]


def caixa_documents_dir() -> Path:
    d = documents_dir() / "CAIXA"
    d.mkdir(parents=True, exist_ok=True)
    return d


def comprovantes_pix_dir() -> Path:
    d = caixa_documents_dir() / "Comprovantes_PIX"
    d.mkdir(parents=True, exist_ok=True)
    return d


def is_allowed_comprovante(filename: str) -> bool:
    ext = Path(filename).suffix.lower()
    return ext in ALLOWED_COMPROVANTE_EXTENSIONS


def infer_ext_from_mimetype(mimetype: str) -> str:
    mt = str(mimetype or "").lower().split(";")[0].strip()
    if mt == "application/pdf":
        return ".pdf"
    if mt in ("image/jpeg", "image/jpg", "image/jfif"):
        return ".jpg"
    if mt == "image/png":
        return ".png"
    if mt in ("image/heic", "image/heif"):
        return ".heic" if mt == "image/heic" else ".heif"
    return ""


def serve_asset(ctx: AppContext, filename: str):
    try:
        fn = str(filename or "")
        fn = fn.replace("\\", "/")
        if fn.startswith("assets/"):
            fn = fn[len("assets/") :]
        filename = fn
    except Exception:
        pass

    if pg_enabled():
        try:
            rec = pg_store.get_asset(path=f"assets/{filename}")
            if rec is not None:
                raw, ct = rec
                return send_file(
                    io.BytesIO(raw),
                    mimetype=(ct or "application/octet-stream"),
                    download_name=str(filename),
                    max_age=3600,
                )
        except Exception:
            pass

    try:
        p = (ctx.assets_dir / filename).resolve()
        if p.exists() and p.is_file():
            return send_from_directory(str(ctx.assets_dir), filename)
    except Exception:
        pass
    return send_from_directory(str(ctx.bundle_dir / "assets"), filename)
