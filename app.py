from __future__ import annotations

import json
import logging
import os
import re
import secrets
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, make_response, request, send_from_directory
from werkzeug.utils import secure_filename

try:
    import pg_store
except Exception:
    pg_store = None

logger = logging.getLogger(__name__)

BUNDLE_DIR = Path(os.environ.get("CARDAPIO_BUNDLE_DIR") or Path(__file__).resolve().parent).resolve()


def _bootstrap_file_if_missing(*, src: Path, dst: Path) -> None:
    try:
        if dst.exists():
            return
        if not src.exists() or not src.is_file():
            return
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(src.read_bytes())
    except Exception:
        pass
DATA_DIR = Path(os.environ.get("CARDAPIO_DATA_DIR") or BUNDLE_DIR).resolve()
DATA_DIR.mkdir(parents=True, exist_ok=True)

DATA_FILE = DATA_DIR / "produtos.json"
CATALOGO_PUBLICADO_FILE = DATA_DIR / "catalogo_publicado.json"
ASSETS_DIR = DATA_DIR / "assets"
MESAS_FILE = DATA_DIR / "mesas.json"
SOLICITACOES_FILE = DATA_DIR / "solicitacoes.json"

ALLOWED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
ALLOWED_COMPROVANTE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".pdf", ".jfif", ".heic", ".heif"}

PDV_KEY = os.environ.get("PDV_KEY", "")
ALLOWED_PAYMENT_METHODS = {"PIX", "DINHEIRO", "CARTAO", "MISTO"}

PDV_PRODUCTS_URL = os.environ.get("PDV_PRODUCTS_URL", "http://127.0.0.1:5600/api/produtos?ativos=1")

app = Flask(
    __name__,
    static_folder=str(BUNDLE_DIR),
    static_url_path="",
)


def _pg_enabled() -> bool:
    if pg_store is None:
        return False
    try:
        return bool(pg_store.is_enabled())
    except Exception:
        return False


def _admin_enabled() -> bool:
    v = str(os.environ.get("CARDAPIO_ADMIN_ENABLED") or "").strip().lower()
    if v in ("1", "true", "yes", "y", "on"):
        return True
    if v in ("0", "false", "no", "n", "off"):
        return False
    return not _pg_enabled()


if _pg_enabled():
    try:
        pg_store.init_db()
        pg_store.ensure_default_mesas(max_mesas=30)
    except Exception:
        pass


def _read_json_file(path: Path) -> Any:
    if not path.exists():
        raise FileNotFoundError(str(path))
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _ensure_catalogo_publicado_file() -> dict[str, Any]:
    _bootstrap_file_if_missing(src=(BUNDLE_DIR / "catalogo_publicado.json"), dst=CATALOGO_PUBLICADO_FILE)
    if not CATALOGO_PUBLICADO_FILE.exists():
        _write_json_file(CATALOGO_PUBLICADO_FILE, {"categorias": [], "produtos": [], "ui": {}})

    data = _read_json_file(CATALOGO_PUBLICADO_FILE)
    if not isinstance(data, dict):
        data = {"categorias": [], "produtos": [], "ui": {}}
    if not isinstance(data.get("categorias"), list):
        data["categorias"] = []
    if not isinstance(data.get("produtos"), list):
        data["produtos"] = []
    if not isinstance(data.get("ui"), dict):
        data["ui"] = {}
    return data


def _read_catalogo_publicado() -> dict[str, Any]:
    if _pg_enabled():
        try:
            rec = pg_store.get_catalogo_publicado()
            if isinstance(rec, dict):
                return rec
        except Exception:
            pass
    return _ensure_catalogo_publicado_file()


def _save_catalogo_publicado(*, record: dict[str, Any]) -> None:
    if not isinstance(record, dict):
        return
    if _pg_enabled():
        pg_store.save_catalogo_publicado(record=record)
        return
    _write_json_file(CATALOGO_PUBLICADO_FILE, record)


def _fetch_pdv_products() -> list[dict[str, Any]]:
    url = str(PDV_PRODUCTS_URL or "").strip()
    if not url:
        return []
    req = urllib.request.Request(
        url=url,
        headers={
            "Accept": "application/json",
            "X-PDV-KEY": str(PDV_KEY or ""),
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            raw = resp.read().decode("utf-8")
            j = json.loads(raw) if raw else {}
            arr = j.get("produtos") if isinstance(j, dict) else None
            return arr if isinstance(arr, list) else []
    except Exception:
        return []


def _fetch_pdv_payload() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    url = str(PDV_PRODUCTS_URL or "").strip()
    if not url:
        return [], {}
    req = urllib.request.Request(
        url=url,
        headers={
            "Accept": "application/json",
            "X-PDV-KEY": str(PDV_KEY or ""),
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


def _normalize_asset_ref(value: Any) -> str:
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

    # Se vier só um nome (sem extensão), tenta resolver no diretório assets.
    # Exemplos: "bg_tropical", "Layout", "panel_frame"
    base = s.strip("/")
    base = base.split("/")[-1] if base else ""
    if base and "." not in base:
        for ext in sorted(ALLOWED_IMAGE_EXTENSIONS):
            candidate = ASSETS_DIR / f"{base}{ext}"
            if candidate.exists():
                return f"/assets/{base}{ext}"

    return s


def _normalize_section_name(value: Any) -> str:
    s = str(value or "").strip()
    if not s:
        return "Produtos"
    s = re.sub(r"\s+", " ", s)
    return s


def _section_id_from_name(name: str) -> str:
    base = str(name or "").strip().lower()
    base = re.sub(r"\s+", "_", base)
    base = re.sub(r"[^a-z0-9_\-]", "", base)
    base = base.strip("_-")
    if not base or base == "produtos":
        return "produtos"
    return f"sec_{base}"


def _write_json_file(path: Path, data: Any) -> None:
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    tmp_path.replace(path)


def _is_allowed_image_upload_filename(filename: str) -> bool:
    name = str(filename or "").strip().lower()
    ext = Path(name).suffix
    return bool(ext) and ext in ALLOWED_IMAGE_EXTENSIONS


def _documents_dir() -> Path:
    userprofile = os.environ.get("USERPROFILE")
    home = Path(userprofile) if userprofile else Path.home()

    candidates = [home / "Documents", home / "Documentos"]
    for c in candidates:
        if c.exists():
            return c
    return candidates[0]


def _caixa_documents_dir() -> Path:
    d = _documents_dir() / "CAIXA"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _comprovantes_pix_dir() -> Path:
    d = _caixa_documents_dir() / "Comprovantes_PIX"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _is_allowed_comprovante(filename: str) -> bool:
    ext = Path(filename).suffix.lower()
    return ext in ALLOWED_COMPROVANTE_EXTENSIONS


def _infer_ext_from_mimetype(mimetype: str) -> str:
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


def _is_localhost() -> bool:
    ip = (request.remote_addr or "").strip()
    return ip in ("127.0.0.1", "::1")


def _require_localhost() -> Any:
    if not _is_localhost():
        return jsonify({"error": "forbidden"}), 403
    return None


def _require_pdv_key() -> Any:
    if not PDV_KEY:
        return jsonify({"error": "pdv_key_nao_configurada"}), 500
    key = (request.headers.get("X-PDV-KEY") or "").strip()
    if not key or key != PDV_KEY:
        return jsonify({"error": "unauthorized"}), 401
    return None


def _ensure_mesas_file() -> dict[str, Any]:
    if _pg_enabled():
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

    _bootstrap_file_if_missing(src=(BUNDLE_DIR / "mesas.json"), dst=MESAS_FILE)
    if not MESAS_FILE.exists():
        _write_json_file(MESAS_FILE, {"mesas": []})

    data = _read_json_file(MESAS_FILE)
    if not isinstance(data, dict):
        data = {"mesas": []}

    mesas = data.get("mesas")
    if not isinstance(mesas, list):
        mesas = []
        data["mesas"] = mesas

    # Se não houver mesas cadastradas, gera 1..30 automaticamente.
    if len(mesas) == 0:
        mesas = []
        for n in range(1, 31):
            mesas.append({"mesa": n, "token": secrets.token_urlsafe(24)})
        data["mesas"] = mesas
        _write_json_file(MESAS_FILE, data)

    return data


def _get_table_token_map() -> dict[int, str]:
    if _pg_enabled():
        try:
            return pg_store.get_table_token_map()
        except Exception:
            return {}

    data = _ensure_mesas_file()
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


def _validate_table_token(*, mesa: Any, token: Any) -> tuple[bool, str]:
    try:
        mesa_i = int(mesa)
    except Exception:
        return False, "mesa_invalida"

    if mesa_i < 1 or mesa_i > 30:
        return False, "mesa_fora_do_intervalo"

    tok = str(token or "").strip()
    if not tok:
        return False, "token_ausente"

    mp = _get_table_token_map()
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


def _ensure_solicitacoes_file() -> dict[str, Any]:
    if _pg_enabled():
        return {"solicitacoes": []}

    if not SOLICITACOES_FILE.exists():
        _write_json_file(SOLICITACOES_FILE, {"solicitacoes": []})
    data = _read_json_file(SOLICITACOES_FILE)
    if not isinstance(data, dict):
        data = {"solicitacoes": []}
    if not isinstance(data.get("solicitacoes"), list):
        data["solicitacoes"] = []
    return data


def _save_solicitacoes(data: dict[str, Any]) -> None:
    if _pg_enabled():
        arr = data.get("solicitacoes")
        if isinstance(arr, list):
            for s in arr:
                if isinstance(s, dict):
                    try:
                        pg_store.save_solicitacao(record=s)
                    except Exception:
                        pass
        return

    _write_json_file(SOLICITACOES_FILE, data)


def _find_solicitacao(data: dict[str, Any], solicitacao_id: str) -> tuple[int, dict[str, Any]] | tuple[None, None]:
    if _pg_enabled():
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


def _is_allowed_image(filename: str) -> bool:
    ext = Path(filename).suffix.lower()
    return ext in ALLOWED_IMAGE_EXTENSIONS


def _is_valid_whatsapp(value: Any) -> bool:
    s = re.sub(r"\D+", "", str(value or "").strip())
    if len(s) < 10:
        return False
    if len(s) > 13:
        return False
    return True


@app.get("/")
def home():
    return send_from_directory(str(BUNDLE_DIR), "index.html")


@app.get("/index")
def legacy_index_redirect():
    # Alguns ambientes antigos podem acessar o arquivo "index" (sem .html), que contém
    # lógica de fallback para ./produtos.json. Redirecionar para a home atual.
    resp = make_response("", 302)
    resp.headers["Location"] = "/"
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.get("/produtos.json")
def block_legacy_bundle_produtos_json():
    # Bloquear acesso direto ao produtos.json do bundle (legado). O frontend deve
    # consumir apenas /api/data, que é derivado do PDV (fonte de verdade).
    return make_response("not_found", 404)


@app.get("/Cardapio_DoRafa_mesa_<mesa_txt>")
def cardapio_mesa_comercial(mesa_txt: str):
    try:
        mesa_i = int(str(mesa_txt or "").strip())
    except Exception:
        mesa_i = 0

    if mesa_i < 1 or mesa_i > 30:
        return make_response("Mesa inválida", 404)

    mp = _get_table_token_map()
    token = str(mp.get(int(mesa_i)) or "").strip()
    if not token:
        return make_response("Mesa não cadastrada", 404)

    mesa_json = json.dumps(int(mesa_i), ensure_ascii=False)
    token_json = json.dumps(token, ensure_ascii=False)

    html = (
        "<!doctype html>"
        "<html lang=\"pt-BR\">"
        "<head>"
        "<meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
        "<title>Cardápio</title>"
        "</head>"
        "<body>"
        "<script>"
        "try { localStorage.setItem('cardapio.mesa.v1', String(" + mesa_json + ")); } catch (e) {}"
        "try { localStorage.setItem('cardapio.token.v1', String(" + token_json + ")); } catch (e) {}"
        "window.location.replace('/');"
        "</script>"
        "</body>"
        "</html>"
    )

    resp = make_response(html, 200)
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.get("/admin")
def admin_page():
    if not _admin_enabled():
        return make_response("not_found", 404)
    denied = _require_localhost()
    if denied is not None:
        return denied
    return send_from_directory(str(BUNDLE_DIR), "admin.html")


@app.get("/api/data")
def api_get_data():
    # No modo Hub público, o catálogo é servido a partir do último snapshot publicado pelo PDV.
    if not _admin_enabled():
        published = _read_catalogo_publicado()
        if not isinstance(published, dict):
            published = {"categorias": [], "produtos": [], "ui": {}}

        # Permite manter metadados/descrições/imagens locais (admin local) sobrepondo o publicado.
        try:
            local = _read_json_file(DATA_FILE)
        except FileNotFoundError:
            local = {"categorias": [], "produtos": [], "ui": {}}
        if not isinstance(local, dict):
            local = {"categorias": [], "produtos": [], "ui": {}}

        local_products = local.get("produtos") if isinstance(local.get("produtos"), list) else []
        meta_by_code: dict[str, dict[str, Any]] = {}
        for p in local_products:
            if not isinstance(p, dict):
                continue
            keys = [p.get("pdvCode"), p.get("code"), p.get("id")]
            for k in keys:
                kk = str(k or "").strip().upper()
                if kk:
                    meta_by_code[kk] = p

        pub_products = published.get("produtos") if isinstance(published.get("produtos"), list) else []
        merged_products: list[dict[str, Any]] = []
        for p in pub_products:
            if not isinstance(p, dict):
                continue
            code = str(p.get("id") or p.get("pdvCode") or p.get("code") or "").strip().upper()
            if not code:
                continue
            meta = meta_by_code.get(code, {})
            out_p = dict(p)
            out_p["id"] = code
            out_p["pdvCode"] = code
            if meta.get("descricao") is not None and str(meta.get("descricao") or "").strip():
                out_p["descricao"] = meta.get("descricao")
            if meta.get("imagem") is not None and str(meta.get("imagem") or "").strip():
                out_p["imagem"] = _normalize_asset_ref(meta.get("imagem"))
            if meta.get("queridinho") is not None:
                out_p["queridinho"] = bool(meta.get("queridinho"))
            merged_products.append(out_p)

        out = dict(published)
        out["produtos"] = merged_products
        ui = out.get("ui") if isinstance(out.get("ui"), dict) else {}
        if "logo" in ui:
            ui = dict(ui)
            ui["logo"] = _normalize_asset_ref(ui.get("logo"))
        banner = ui.get("banner") if isinstance(ui.get("banner"), dict) else {}
        imgs = banner.get("imagens") if isinstance(banner.get("imagens"), list) else []
        banner = dict(banner)
        banner["imagens"] = [_normalize_asset_ref(x) for x in imgs if _normalize_asset_ref(x)]
        if ui:
            ui = dict(ui)
            ui["banner"] = banner
            out["ui"] = ui
        return jsonify(out)

    # Modo local (admin): mantém o comportamento atual (catálogo vindo do PDV local)
    try:
        local = _read_json_file(DATA_FILE)
    except FileNotFoundError:
        local = {"categorias": [], "produtos": [], "ui": {}}
    if not isinstance(local, dict):
        local = {"categorias": [], "produtos": [], "ui": {}}

    pdv_products, pdv_ui = _fetch_pdv_payload()
    if not pdv_products:
        out2: dict[str, Any] = dict(local)
        out2["produtos"] = []
        return jsonify(out2)

    local_products = local.get("produtos") if isinstance(local.get("produtos"), list) else []
    meta_by_code: dict[str, dict[str, Any]] = {}
    for p in local_products:
        if not isinstance(p, dict):
            continue
        keys = [
            p.get("pdvCode"),
            p.get("code"),
            p.get("id"),
        ]
        for k in keys:
            kk = str(k or "").strip().upper()
            if kk:
                meta_by_code[kk] = p

    merged_products2: list[dict[str, Any]] = []
    for p in pdv_products:
        if not isinstance(p, dict):
            continue
        if p.get("cardapio_show") is False:
            continue
        code = str(p.get("code") or "").strip().upper()
        if not code:
            continue

        meta = meta_by_code.get(code, {})
        featured_raw = p.get("cardapio_featured")
        featured = bool(featured_raw) if featured_raw is not None else bool(meta.get("queridinho"))
        img_raw = p.get("image")
        img = _normalize_asset_ref(img_raw)
        merged_products2.append(
            {
                "id": code,
                "pdvCode": code,
                "nome": str(p.get("name") or meta.get("nome") or "").strip() or code,
                "preco": float(p.get("unit_price") or 0),
                "ativo": bool(p.get("is_active")) if p.get("is_active") is not None else bool(meta.get("ativo", True)),
                "categoriaId": "",
                "descricao": meta.get("descricao") or "",
                "imagem": img or _normalize_asset_ref(meta.get("imagem")),
                "queridinho": featured,
                "cardapioSection": p.get("cardapio_section"),
            }
        )

    out2: dict[str, Any] = dict(local)

    section_order: list[str] = []
    section_id_by_name: dict[str, str] = {}
    for mp in merged_products2:
        sec_name = _normalize_section_name(mp.get("cardapioSection"))
        if sec_name not in section_id_by_name:
            section_id_by_name[sec_name] = _section_id_from_name(sec_name)
            section_order.append(sec_name)
        mp["categoriaId"] = section_id_by_name[sec_name]

    out_categories: list[dict[str, Any]] = []
    sec_names = [n for n in section_order if n != "Produtos"]
    sec_names_sorted = sorted(sec_names, key=lambda x: x.lower())
    if "Produtos" in section_order:
        sec_names_sorted.append("Produtos")
    for nm in sec_names_sorted:
        out_categories.append({"id": section_id_by_name.get(nm) or _section_id_from_name(nm), "nome": nm})

    out2["categorias"] = out_categories
    out2["produtos"] = merged_products2
    if isinstance(pdv_ui, dict) and pdv_ui:
        local_ui = out2.get("ui") if isinstance(out2.get("ui"), dict) else {}
        merged_ui = dict(local_ui)
        merged_ui.update(pdv_ui)

        if "logo" in merged_ui:
            merged_ui["logo"] = _normalize_asset_ref(merged_ui.get("logo"))
        banner = merged_ui.get("banner") if isinstance(merged_ui.get("banner"), dict) else {}
        imgs = banner.get("imagens") if isinstance(banner.get("imagens"), list) else []
        banner = dict(banner)
        banner["imagens"] = [_normalize_asset_ref(x) for x in imgs if _normalize_asset_ref(x)]
        merged_ui["banner"] = banner

        out2["ui"] = merged_ui
    return jsonify(out2)


@app.post("/api/data")
def api_save_data():
    if not _admin_enabled():
        return jsonify({"error": "forbidden"}), 403
    denied = _require_localhost()
    if denied is not None:
        return denied

    data = request.get_json(silent=True)
    if data is None:
        return jsonify({"error": "json_invalido"}), 400

    if not isinstance(data, dict):
        return jsonify({"error": "json_precisa_ser_objeto"}), 400

    if "produtos" not in data or "categorias" not in data:
        return jsonify({"error": "estrutura_incompleta"}), 400

    _write_json_file(DATA_FILE, data)
    return jsonify({"ok": True})


@app.post("/api/pdv/assets/upload")
def api_pdv_assets_upload():
    denied = _require_pdv_key()
    if denied is not None:
        return denied

    if "file" not in request.files:
        return jsonify({"error": "arquivo_nao_enviado"}), 400

    file = request.files["file"]
    if not file or not file.filename:
        return jsonify({"error": "arquivo_invalido"}), 400

    filename = secure_filename(file.filename)
    if not filename or not _is_allowed_image_upload_filename(filename):
        return jsonify({"error": "extensao_nao_permitida"}), 400

    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    target = (ASSETS_DIR / filename).resolve()

    # Evitar colisões
    base = target.stem
    ext = target.suffix
    i = 1
    while target.exists():
        target = (ASSETS_DIR / f"{base}_{i}{ext}").resolve()
        i += 1

    try:
        file.save(str(target))
    except Exception:
        return jsonify({"error": "falha_ao_salvar"}), 500

    return jsonify({"ok": True, "path": f"assets/{target.name}"})


@app.post("/api/pdv/catalogo/publicar")
def api_pdv_publicar_catalogo():
    denied = _require_pdv_key()
    if denied is not None:
        return denied

    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({"error": "json_invalido"}), 400

    produtos = body.get("produtos")
    categorias = body.get("categorias")
    ui = body.get("ui")
    if not isinstance(produtos, list) or not isinstance(categorias, list):
        return jsonify({"error": "estrutura_incompleta"}), 400
    if ui is not None and not isinstance(ui, dict):
        return jsonify({"error": "ui_invalido"}), 400

    record = {
        "categorias": categorias,
        "produtos": produtos,
        "ui": ui if isinstance(ui, dict) else {},
        "publicado_em": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
    }

    try:
        _save_catalogo_publicado(record=record)
    except Exception:
        return jsonify({"error": "falha_ao_salvar"}), 500

    return jsonify({"ok": True})


@app.post("/api/pdv/solicitacoes/<solicitacao_id>/status")
def api_pdv_set_status(solicitacao_id: str):
    denied = _require_pdv_key()
    if denied is not None:
        return denied

    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({"error": "json_invalido"}), 400

    pdv_status = str(body.get("pdv_status") or "").strip().upper()
    if pdv_status not in ("FECHADA", "FINALIZADA"):
        return jsonify({"error": "pdv_status_invalido"}), 400

    if _pg_enabled():
        try:
            pg_store.update_solicitacao_status(solicitacao_id=solicitacao_id, pdv_status=pdv_status)
        except Exception:
            return jsonify({"error": "falha_ao_salvar"}), 500
    else:
        data = _ensure_solicitacoes_file()
        idx, s = _find_solicitacao(data, solicitacao_id=solicitacao_id)
        if s is None or idx is None:
            return jsonify({"error": "nao_encontrado"}), 404

        s["pdv_status"] = pdv_status
        s["pdv_status_em"] = __import__("datetime").datetime.now().isoformat(timespec="seconds")
        data["solicitacoes"][idx] = s
        _save_solicitacoes(data)
    return jsonify({"ok": True})


@app.post("/api/solicitacoes/<solicitacao_id>/comprovante")
def api_upload_comprovante(solicitacao_id: str):
    mesa = request.args.get("mesa")
    token = request.args.get("token")
    ok, err = _validate_table_token(mesa=mesa, token=token)
    if not ok:
        return jsonify({"error": err}), 401

    data = _ensure_solicitacoes_file()
    idx, s = _find_solicitacao(data, solicitacao_id=solicitacao_id)
    if s is None or idx is None:
        return jsonify({"error": "nao_encontrado"}), 404
    if int(s.get("mesa") or 0) != int(mesa):
        return jsonify({"error": "forbidden"}), 403

    cur_status = str(s.get("status") or "").upper()
    resposta = s.get("resposta") if isinstance(s.get("resposta"), dict) else None
    resp_tipo = str((resposta or {}).get("tipo") or "").upper()
    if cur_status != "RESPONDIDA" or resp_tipo != "ENVIAR_PIX":
        return jsonify({"error": "comprovante_indisponivel"}), 409

    if "file" not in request.files:
        return jsonify({"error": "arquivo_nao_enviado"}), 400

    file = request.files["file"]
    if not file or not file.filename:
        # Alguns celulares enviam arquivo sem nome; tenta inferir pelo mimetype
        inferred_ext = _infer_ext_from_mimetype(getattr(file, "mimetype", "") or "")
        if not inferred_ext:
            return jsonify({"error": "arquivo_invalido"}), 400
        filename = f"comprovante{inferred_ext}"
    else:
        filename = secure_filename(file.filename)
        if not filename:
            inferred_ext = _infer_ext_from_mimetype(getattr(file, "mimetype", "") or "")
            if not inferred_ext:
                return jsonify({"error": "arquivo_invalido"}), 400
            filename = f"comprovante{inferred_ext}"

    # Aceita por extensão OU por mimetype conhecido
    if not _is_allowed_comprovante(filename):
        inferred_ext = _infer_ext_from_mimetype(getattr(file, "mimetype", "") or "")
        if inferred_ext and inferred_ext in ALLOWED_COMPROVANTE_EXTENSIONS:
            filename = f"comprovante{inferred_ext}"
        else:
            return jsonify({"error": "extensao_nao_permitida"}), 400

    ext = Path(filename).suffix.lower()
    mesa_i = int(s.get("mesa") or 0)
    target_dir = _comprovantes_pix_dir()

    stamp = __import__("datetime").datetime.now().strftime("%Y%m%d_%H%M%S")
    out_name = f"PIX_MESA_{mesa_i}_{solicitacao_id}_{stamp}{ext}"
    out_path = (target_dir / out_name).resolve()

    try:
        file.save(str(out_path))
    except Exception:
        return jsonify({"error": "falha_ao_salvar"}), 500

    s["comprovante"] = {
        "filename": out_name,
        "path": str(out_path),
        "uploaded_em": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
    }
    if _pg_enabled():
        try:
            pg_store.save_solicitacao(record=s)
        except Exception:
            return jsonify({"error": "falha_ao_salvar"}), 500
    else:
        data["solicitacoes"][idx] = s
        _save_solicitacoes(data)

    return jsonify({"ok": True})


@app.post("/api/upload")
def api_upload():
    if not _admin_enabled():
        return jsonify({"error": "forbidden"}), 403
    denied = _require_localhost()
    if denied is not None:
        return denied

    if "file" not in request.files:
        return jsonify({"error": "arquivo_nao_enviado"}), 400

    file = request.files["file"]
    if not file or not file.filename:
        return jsonify({"error": "arquivo_invalido"}), 400

    filename = secure_filename(file.filename)
    if not _is_allowed_image(filename):
        return jsonify({"error": "extensao_nao_permitida"}), 400

    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    target = ASSETS_DIR / filename

    base = target.stem
    ext = target.suffix
    i = 1
    while target.exists():
        target = ASSETS_DIR / f"{base}_{i}{ext}"
        i += 1

    file.save(str(target))
    return jsonify({"ok": True, "path": f"assets/{target.name}"})


@app.get("/assets/<path:filename>")
def assets(filename: str):
    # Primeiro tenta assets graváveis (DATA_DIR/assets). Se não existir, faz fallback para o bundle.
    try:
        fn = str(filename or "")
        fn = fn.replace("\\", "/")
        if fn.startswith("assets/"):
            fn = fn[len("assets/") :]
        filename = fn
    except Exception:
        pass
    try:
        p = (ASSETS_DIR / filename).resolve()
        if p.exists() and p.is_file():
            return send_from_directory(str(ASSETS_DIR), filename)
    except Exception:
        pass
    return send_from_directory(str(BUNDLE_DIR / "assets"), filename)


@app.get("/api/mesas")
def api_get_mesas():
    if not _admin_enabled():
        return jsonify({"error": "forbidden"}), 403
    # Exposto apenas para debug/operador; mantém protegido por localhost.
    denied = _require_localhost()
    if denied is not None:
        return denied
    return jsonify(_ensure_mesas_file())


@app.post("/api/solicitacoes")
def api_create_solicitacao():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({"error": "json_invalido"}), 400

    mesa = body.get("mesa")
    token = body.get("token")
    try:
        logger.info(
            "api_create_solicitacao (remote=%s mesa=%s token_prefix=%s)",
            (request.remote_addr or "").strip(),
            mesa,
            str(token or "")[:8],
        )
    except Exception:
        pass
    ok, err = _validate_table_token(mesa=mesa, token=token)
    if not ok:
        return jsonify({"error": err}), 401

    pagamento = str(body.get("pagamento_preferido") or "").strip().upper()
    if pagamento not in ALLOWED_PAYMENT_METHODS:
        return jsonify({"error": "pagamento_invalido"}), 400

    cliente_nome = str(body.get("cliente_nome") or "").strip()
    if len(cliente_nome) > 60:
        return jsonify({"error": "cliente_nome_invalido"}), 400

    itens = body.get("itens")
    if not isinstance(itens, list) or len(itens) == 0:
        return jsonify({"error": "itens_obrigatorios"}), 400
    if len(itens) > 50:
        return jsonify({"error": "muitos_itens"}), 400

    norm_items: list[dict[str, Any]] = []
    for it in itens:
        if not isinstance(it, dict):
            return jsonify({"error": "item_invalido"}), 400
        code = str(it.get("product_code") or it.get("pdvCode") or "").strip().upper()
        if not code:
            return jsonify({"error": "product_code_obrigatorio"}), 400
        try:
            qty = float(it.get("qty") or it.get("quantidade") or 0)
        except Exception:
            qty = 0
        if qty <= 0:
            return jsonify({"error": "qty_invalida"}), 400
        norm_items.append({
            "product_code": code,
            "nome": str(it.get("nome") or "").strip(),
            "qty": qty,
        })

    total_estimado = body.get("total_estimado")
    try:
        total_estimado_f = float(total_estimado) if total_estimado is not None else None
    except Exception:
        total_estimado_f = None

    solicitacao_id = uuid.uuid4().hex
    rec: dict[str, Any] = {
        "id": solicitacao_id,
        "mesa": int(mesa),
        "status": "PENDENTE",
        "pagamento_preferido": pagamento,
        "cliente_nome": cliente_nome or None,
        "itens": norm_items,
        "total_estimado": total_estimado_f,
        "criado_em": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
        "atendida_em": None,
        "respondida_em": None,
        "pdv_status": None,
        "pdv_status_em": None,
        "pdv_id": None,
        "operator_user_id": None,
        "sale_id": None,
        "resposta": None,
    }

    data = _ensure_solicitacoes_file()
    if _pg_enabled():
        try:
            pg_store.save_solicitacao(record=rec)
        except Exception:
            pass
    else:
        data["solicitacoes"].append(rec)
        _save_solicitacoes(data)
    return jsonify({"id": solicitacao_id, "status": "PENDENTE"})


@app.get("/api/solicitacoes/<solicitacao_id>")
def api_get_solicitacao(solicitacao_id: str):
    mesa = request.args.get("mesa")
    token = request.args.get("token")
    ok, err = _validate_table_token(mesa=mesa, token=token)
    if not ok:
        return jsonify({"error": err}), 401

    data = _ensure_solicitacoes_file()
    _, s = _find_solicitacao(data, solicitacao_id=solicitacao_id)
    if s is None:
        return jsonify({"error": "nao_encontrado"}), 404
    if int(s.get("mesa") or 0) != int(mesa):
        return jsonify({"error": "forbidden"}), 403
    return jsonify(s)


@app.post("/api/public/pedidos")
def api_public_create_pedido():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({"error": "json_invalido"}), 400

    pagamento = str(body.get("pagamento_preferido") or "").strip().upper()
    if pagamento not in ALLOWED_PAYMENT_METHODS:
        return jsonify({"error": "pagamento_invalido"}), 400

    cliente_nome = str(body.get("cliente_nome") or "").strip()
    if not cliente_nome or len(cliente_nome) > 60:
        return jsonify({"error": "cliente_nome_invalido"}), 400

    cliente_whatsapp = str(body.get("cliente_whatsapp") or "").strip()
    if not _is_valid_whatsapp(cliente_whatsapp):
        return jsonify({"error": "whatsapp_invalido"}), 400

    tipo_entrega = str(body.get("tipo_entrega") or "").strip().upper()
    if tipo_entrega not in ("DELIVERY", "RETIRADA"):
        return jsonify({"error": "tipo_entrega_invalido"}), 400

    endereco = body.get("endereco")
    if tipo_entrega == "DELIVERY":
        if endereco is None:
            endereco = None
        elif isinstance(endereco, dict):
            required = ["rua", "numero", "bairro", "cidade"]
            for k in required:
                if not str(endereco.get(k) or "").strip():
                    return jsonify({"error": "endereco_incompleto"}), 400
        else:
            return jsonify({"error": "endereco_invalido"}), 400
    else:
        endereco = None

    troco_para = body.get("troco_para")
    if pagamento == "DINHEIRO" and troco_para is not None:
        try:
            troco_f = float(troco_para)
        except Exception:
            return jsonify({"error": "troco_invalido"}), 400
        if troco_f < 0 or troco_f > 10000:
            return jsonify({"error": "troco_invalido"}), 400

    itens = body.get("itens")
    if not isinstance(itens, list) or len(itens) == 0:
        return jsonify({"error": "itens_obrigatorios"}), 400
    if len(itens) > 80:
        return jsonify({"error": "muitos_itens"}), 400

    norm_items: list[dict[str, Any]] = []
    for it in itens:
        if not isinstance(it, dict):
            return jsonify({"error": "item_invalido"}), 400
        code = str(it.get("product_code") or it.get("pdvCode") or "").strip().upper()
        if not code:
            return jsonify({"error": "product_code_obrigatorio"}), 400
        try:
            qty = float(it.get("qty") or it.get("quantidade") or 0)
        except Exception:
            qty = 0
        if qty <= 0:
            return jsonify({"error": "qty_invalida"}), 400
        norm_items.append({
            "product_code": code,
            "nome": str(it.get("nome") or "").strip(),
            "qty": qty,
        })

    total_estimado = body.get("total_estimado")
    try:
        total_estimado_f = float(total_estimado) if total_estimado is not None else None
    except Exception:
        total_estimado_f = None

    access_token = secrets.token_urlsafe(24)
    solicitacao_id = uuid.uuid4().hex
    rec: dict[str, Any] = {
        "id": solicitacao_id,
        "kind": "DELIVERY",
        "access_token": access_token,
        "status": "PENDENTE",
        "pagamento_preferido": pagamento,
        "cliente_nome": cliente_nome,
        "cliente_whatsapp": cliente_whatsapp,
        "tipo_entrega": tipo_entrega,
        "endereco": endereco,
        "troco_para": troco_para,
        "observacoes": str(body.get("observacoes") or "").strip() or None,
        "itens": norm_items,
        "total_estimado": total_estimado_f,
        "criado_em": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
        "atendida_em": None,
        "respondida_em": None,
        "pdv_status": None,
        "pdv_status_em": None,
        "pdv_id": None,
        "operator_user_id": None,
        "sale_id": None,
        "resposta": None,
        "comprovante": None,
    }

    if _pg_enabled():
        try:
            pg_store.save_solicitacao(record=rec)
        except Exception:
            return jsonify({"error": "falha_ao_salvar"}), 500
    else:
        data = _ensure_solicitacoes_file()
        data["solicitacoes"].append(rec)
        _save_solicitacoes(data)

    return jsonify({"id": solicitacao_id, "token": access_token, "status": "PENDENTE"})


@app.get("/api/public/pedidos/<solicitacao_id>")
def api_public_get_pedido(solicitacao_id: str):
    token = (request.args.get("token") or "").strip()
    if not token:
        return jsonify({"error": "token_ausente"}), 401

    data = _ensure_solicitacoes_file()
    _, s = _find_solicitacao(data, solicitacao_id=solicitacao_id)
    if s is None:
        return jsonify({"error": "nao_encontrado"}), 404

    if str(s.get("kind") or "").upper() != "DELIVERY":
        return jsonify({"error": "forbidden"}), 403

    expected = str(s.get("access_token") or "").strip()
    if not expected or token != expected:
        return jsonify({"error": "unauthorized"}), 401
    return jsonify(s)


@app.get("/api/pdv/solicitacoes")
def api_pdv_list_solicitacoes():
    denied = _require_pdv_key()
    if denied is not None:
        return denied
    status = str(request.args.get("status") or "PENDENTE").strip().upper()

    if _pg_enabled():
        try:
            out = pg_store.list_by_status(status=status)
        except Exception:
            out = []
        return jsonify({"solicitacoes": out})

    data = _ensure_solicitacoes_file()
    arr = data.get("solicitacoes")
    if not isinstance(arr, list):
        arr = []
    out = [s for s in arr if isinstance(s, dict) and str(s.get("status") or "").upper() == status]
    return jsonify({"solicitacoes": out})


@app.post("/api/pdv/solicitacoes/<solicitacao_id>/atender")
def api_pdv_atender_solicitacao(solicitacao_id: str):
    denied = _require_pdv_key()
    if denied is not None:
        return denied

    body = request.get_json(silent=True)
    if body is None:
        body = {}
    if not isinstance(body, dict):
        return jsonify({"error": "json_invalido"}), 400

    data = _ensure_solicitacoes_file()
    idx, s = _find_solicitacao(data, solicitacao_id=solicitacao_id)
    if s is None or idx is None:
        return jsonify({"error": "nao_encontrado"}), 404

    cur_status = str(s.get("status") or "").upper()
    if cur_status != "PENDENTE":
        return jsonify({"error": "status_invalido", "status": cur_status}), 409

    s["status"] = "EM_ATENDIMENTO"
    s["pdv_id"] = body.get("pdv_id")
    s["operator_user_id"] = body.get("operator_user_id")
    s["atendida_em"] = __import__("datetime").datetime.now().isoformat(timespec="seconds")

    if _pg_enabled():
        try:
            pg_store.save_solicitacao(record=s)
        except Exception:
            return jsonify({"error": "falha_ao_salvar"}), 500
    else:
        data["solicitacoes"][idx] = s
        _save_solicitacoes(data)
    return jsonify(s)


@app.post("/api/pdv/solicitacoes/<solicitacao_id>/vincular")
def api_pdv_vincular_sale(solicitacao_id: str):
    denied = _require_pdv_key()
    if denied is not None:
        return denied

    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({"error": "json_invalido"}), 400
    sale_id = body.get("sale_id")
    try:
        sale_id_i = int(sale_id)
    except Exception:
        return jsonify({"error": "sale_id_invalido"}), 400

    data = _ensure_solicitacoes_file()
    idx, s = _find_solicitacao(data, solicitacao_id=solicitacao_id)
    if s is None or idx is None:
        return jsonify({"error": "nao_encontrado"}), 404

    s["sale_id"] = sale_id_i
    if _pg_enabled():
        try:
            pg_store.save_solicitacao(record=s)
        except Exception:
            return jsonify({"error": "falha_ao_salvar"}), 500
    else:
        data["solicitacoes"][idx] = s
        _save_solicitacoes(data)
    return jsonify({"ok": True})


@app.post("/api/pdv/solicitacoes/<solicitacao_id>/resposta")
def api_pdv_responder_solicitacao(solicitacao_id: str):
    denied = _require_pdv_key()
    if denied is not None:
        return denied

    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({"error": "json_invalido"}), 400

    tipo = str(body.get("tipo") or "").strip().upper()
    if tipo not in ("ENVIAR_PIX", "IR_CAIXA", "PAGAMENTO_CONFIRMADO", "PAGAR_NA_ENTREGA"):
        return jsonify({"error": "tipo_invalido"}), 400

    data = _ensure_solicitacoes_file()
    idx, s = _find_solicitacao(data, solicitacao_id=solicitacao_id)
    if s is None or idx is None:
        return jsonify({"error": "nao_encontrado"}), 404

    cur_status = str(s.get("status") or "").upper()
    prev_resposta = s.get("resposta") if isinstance(s.get("resposta"), dict) else None
    prev_tipo = str((prev_resposta or {}).get("tipo") or "").upper()

    if tipo == "PAGAMENTO_CONFIRMADO":
        # Confirmação só faz sentido após ENVIAR_PIX e com comprovante anexado
        if cur_status != "RESPONDIDA" or prev_tipo != "ENVIAR_PIX":
            return jsonify({"error": "status_invalido", "status": cur_status}), 409
        comp = s.get("comprovante") if isinstance(s.get("comprovante"), dict) else None
        if not comp or not str(comp.get("path") or "").strip():
            return jsonify({"error": "comprovante_ausente"}), 409
    else:
        if cur_status not in ("EM_ATENDIMENTO", "PENDENTE"):
            return jsonify({"error": "status_invalido", "status": cur_status}), 409

    resposta: dict[str, Any] = {
        "tipo": tipo,
        "mensagem": str(body.get("mensagem") or "").strip() or None,
        "pix": body.get("pix") if tipo == "ENVIAR_PIX" else None,
    }

    s["status"] = "RESPONDIDA"
    s["respondida_em"] = __import__("datetime").datetime.now().isoformat(timespec="seconds")
    s["resposta"] = resposta
    if _pg_enabled():
        try:
            pg_store.save_solicitacao(record=s)
        except Exception:
            return jsonify({"error": "falha_ao_salvar"}), 500
    else:
        data["solicitacoes"][idx] = s
        _save_solicitacoes(data)

    return jsonify({"ok": True})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5500"))
    app.run(host="0.0.0.0", port=port, debug=True)
