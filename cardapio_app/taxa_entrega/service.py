from __future__ import annotations

import math
import re
from datetime import datetime
from typing import Any

from .. import core


def _parse_float(v: Any) -> float | None:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    if not s:
        return None
    s = s.replace("R$", "").strip()
    s = s.replace(".", "").replace(",", ".") if "," in s else s
    try:
        return float(s)
    except Exception:
        return None


def _extract_lat_lng_from_text(s: str) -> tuple[float, float] | None:
    m = re.search(r"@(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)", s)
    if m:
        try:
            return float(m.group(1)), float(m.group(2))
        except Exception:
            return None

    m = re.search(r"q=(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)", s)
    if m:
        try:
            return float(m.group(1)), float(m.group(2))
        except Exception:
            return None

    # Formato comum em links longos do Google Maps:
    # ...!3d-16.75474!4d-48.5049903...
    m = re.search(r"!3d(-?\d+(?:\.\d+)?)!4d(-?\d+(?:\.\d+)?)", s)
    if m:
        try:
            return float(m.group(1)), float(m.group(2))
        except Exception:
            return None

    # Outro formato comum em URLs: ll=-16.75474,-48.5049903
    m = re.search(r"(?:\?|&|#)ll=(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)", s)
    if m:
        try:
            return float(m.group(1)), float(m.group(2))
        except Exception:
            return None

    # Alguns links trazem 'query=lat,lng' (ou query=... onde o lat/lng aparece)
    m = re.search(r"(?:\?|&|#)query=(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)", s)
    if m:
        try:
            return float(m.group(1)), float(m.group(2))
        except Exception:
            return None

    return None


def _haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1 = a
    lat2, lon2 = b
    r = 6371.0088
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    h = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def get_delivery_fee_config_from_ui(ui: Any) -> dict[str, Any]:
    if not isinstance(ui, dict):
        return {}

    cfg = ui.get("deliveryFee")
    if isinstance(cfg, dict):
        return cfg

    out: dict[str, Any] = {}
    for k in ("deliveryFeeEnabled", "deliveryFeeBase", "deliveryFeePerKm", "deliveryFeeMin", "deliveryFeeMax", "deliveryFeeOriginMapsUrl"):
        if k in ui:
            out[k] = ui.get(k)
    return out


def is_delivery_fee_enabled(ui: Any) -> bool:
    cfg = get_delivery_fee_config_from_ui(ui)
    if not cfg:
        return False

    enabled = cfg.get("enabled")
    if enabled is None and "deliveryFeeEnabled" in cfg:
        enabled = cfg.get("deliveryFeeEnabled")

    v = str(enabled or "").strip().lower()
    if v in ("1", "true", "yes", "y", "on"):
        return True
    if v in ("0", "false", "no", "n", "off", ""):
        return False

    return bool(enabled)


def compute_delivery_fee(*, ui: Any, client_maps_url: str) -> dict[str, Any] | None:
    cfg = get_delivery_fee_config_from_ui(ui)
    if not cfg:
        return None
    if not is_delivery_fee_enabled(ui):
        return None

    origin_maps_url = str(cfg.get("origin_maps_url") or cfg.get("deliveryFeeOriginMapsUrl") or "").strip()
    if not origin_maps_url:
        return None

    a = _extract_lat_lng_from_text(origin_maps_url)
    b = _extract_lat_lng_from_text(str(client_maps_url or "").strip())
    if a is None or b is None:
        return None

    dist_km = _haversine_km(a, b)

    base = _parse_float(cfg.get("base") if "base" in cfg else cfg.get("deliveryFeeBase")) or 0.0
    per_km = _parse_float(cfg.get("per_km") if "per_km" in cfg else cfg.get("deliveryFeePerKm")) or 0.0
    min_v = _parse_float(cfg.get("min") if "min" in cfg else cfg.get("deliveryFeeMin"))
    max_v = _parse_float(cfg.get("max") if "max" in cfg else cfg.get("deliveryFeeMax"))

    fee = float(base) + float(per_km) * float(dist_km)

    if min_v is not None:
        fee = max(fee, float(min_v))
    if max_v is not None:
        fee = min(fee, float(max_v))

    fee = round(fee + 1e-9, 2)
    dist_km = round(float(dist_km) + 1e-9, 3)

    return {
        "enabled": True,
        "fee": fee,
        "distance_km": dist_km,
        "origin_maps_url": origin_maps_url,
        "client_maps_url": str(client_maps_url or "").strip(),
        "computed_em": datetime.now().isoformat(timespec="seconds"),
        "method": "haversine",
    }


def apply_delivery_fee_to_order_record(*, ctx: core.AppContext, rec: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(rec, dict):
        return rec

    kind = str(rec.get("kind") or "").strip().upper()
    tipo_entrega = str(rec.get("tipo_entrega") or "").strip().upper()
    if kind != "DELIVERY" or tipo_entrega != "DELIVERY":
        return rec

    endereco = rec.get("endereco") if isinstance(rec.get("endereco"), dict) else {}
    maps_url = str((endereco or {}).get("maps_url") or "").strip()
    if not maps_url:
        return rec

    published = core.read_catalogo_publicado(ctx)
    ui = published.get("ui") if isinstance(published, dict) else {}

    calc = compute_delivery_fee(ui=ui, client_maps_url=maps_url)
    if not calc:
        return rec

    subtotal = rec.get("total_estimado")
    try:
        subtotal_f = float(subtotal) if subtotal is not None else None
    except Exception:
        subtotal_f = None

    if subtotal_f is None:
        return rec

    out = dict(rec)
    out["subtotal_estimado"] = subtotal_f
    out["taxa_entrega"] = float(calc["fee"])
    out["entrega_dist_km"] = float(calc["distance_km"])
    out["entrega_origem_maps_url"] = calc.get("origin_maps_url")
    out["entrega_cliente_maps_url"] = calc.get("client_maps_url")
    out["entrega_taxa_calculada_em"] = calc.get("computed_em")
    out["total_estimado"] = round(subtotal_f + float(calc["fee"]) + 1e-9, 2)
    return out
