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


def _point_in_polygon(point: tuple[float, float], polygon: list[list[float]]) -> bool:
    """Ray casting algorithm. polygon = [[lat,lng], ...] (fechado ou não)."""
    if not polygon or len(polygon) < 3:
        return False
    lat, lng = point
    n = len(polygon)
    inside = False
    j = n - 1
    for i in range(n):
        yi, xi = polygon[i][0], polygon[i][1]
        yj, xj = polygon[j][0], polygon[j][1]
        intersect = ((yi > lat) != (yj > lat)) and (
            lng < (xj - xi) * (lat - yi) / (yj - yi + 1e-30) + xi
        )
        if intersect:
            inside = not inside
        j = i
    return inside


def _load_zonas_ativas() -> list[dict[str, Any]]:
    """Carrega zonas de cobertura ativas do PostgreSQL."""
    try:
        from .. import core as _core
        if not _core.pg_enabled():
            return []
        return _core.pg_store.list_taxa_entrega_zonas(ativo_only=True)
    except Exception:
        return []


def _compute_fee_by_zone(
    *,
    client_coords: tuple[float, float],
    zonas: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Calcula taxa por zona (ponto dentro do polígono).

    Retorna a primeira zona que contém o ponto (menor taxa primeiro se empate).
    Se a zona for 'gratis', retorna taxa 0.
    """
    for zona in zonas:
        poligono = zona.get("poligono")
        if not poligono or len(poligono) < 3:
            continue
        if _point_in_polygon(client_coords, poligono):
            taxa = 0.0 if bool(zona.get("gratis")) else float(zona.get("taxa") or 0)
            return {
                "zone": zona.get("nome"),
                "cidade": zona.get("cidade"),
                "zone_fee": taxa,
                "gratis": bool(zona.get("gratis")),
            }
    return None


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

    # --- Cálculo por distância (haversine) ---
    distance_fee = float(base) + float(per_km) * float(dist_km)

    if min_v is not None:
        distance_fee = max(distance_fee, float(min_v))
    if max_v is not None:
        distance_fee = min(distance_fee, float(max_v))

    # --- Cálculo por zona (ponto no polígono) ---
    zone_result = _compute_fee_by_zone(client_coords=b, zonas=_load_zonas_ativas())
    zone_fee = zone_result["zone_fee"] if zone_result else None

    # --- Regra final: max(zona, distancia) ---
    # Se tem zona e a zona é grátis (taxa=0), o cliente paga 0.
    # Se tem zona e não é grátis, usa max(taxa_zona, taxa_distancia).
    # Se não tem zona, usa só distancia.
    if zone_result and zone_result.get("gratis"):
        fee = 0.0
        method = "zone_gratis"
    elif zone_fee is not None:
        fee = max(float(zone_fee), float(distance_fee))
        method = "zone_max_distance"
    else:
        fee = float(distance_fee)
        method = "haversine"

    # Regra de arredondamento para valor cheio em reais:
    # - até X,49: arredonda para baixo
    # - a partir de X,50: arredonda para cima
    # (Não arredonda se a zona é grátis — mantém 0.00)
    if method != "zone_gratis":
        try:
            floor_v = math.floor(float(fee))
            frac = float(fee) - float(floor_v)
            fee_int = int(floor_v + (1 if frac >= 0.5 else 0))
            fee = float(fee_int)
        except Exception:
            pass

    # Reaplica limites após arredondamento (exceto se grátis)
    if method != "zone_gratis":
        if min_v is not None:
            fee = max(fee, float(min_v))
        if max_v is not None:
            fee = min(fee, float(max_v))

    fee = round(fee + 1e-9, 2)
    dist_km = round(float(dist_km) + 1e-9, 3)

    result: dict[str, Any] = {
        "enabled": True,
        "fee": fee,
        "distance_km": dist_km,
        "origin_maps_url": origin_maps_url,
        "client_maps_url": str(client_maps_url or "").strip(),
        "computed_em": datetime.now().isoformat(timespec="seconds"),
        "method": method,
    }
    if zone_result:
        result["zone"] = zone_result.get("zone")
        result["zone_fee"] = zone_result.get("zone_fee")
        result["zone_gratis"] = zone_result.get("gratis")
    return result


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
