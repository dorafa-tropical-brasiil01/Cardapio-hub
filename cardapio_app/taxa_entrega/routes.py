from __future__ import annotations

from typing import Any

from flask import Flask, jsonify, request

from .. import core
from . import service


def register_taxa_entrega_routes(app: Flask) -> None:
    def _ctx() -> core.AppContext:
        return app.config["CARDAPIO_CTX"]

    @app.get("/api/public/taxa_entrega")
    def api_public_taxa_entrega_preview():
        maps_url = str(request.args.get("maps_url") or "").strip()
        if not maps_url:
            return jsonify({"error": "maps_url_obrigatorio"}), 400

        published = core.read_catalogo_publicado(_ctx())
        ui = published.get("ui") if isinstance(published, dict) else {}
        calc = service.compute_delivery_fee(ui=ui, client_maps_url=maps_url)
        if not calc:
            return jsonify({"ok": False, "enabled": service.is_delivery_fee_enabled(ui), "reason": "nao_configurado"})
        return jsonify({"ok": True, "enabled": True, "fee": calc.get("fee"), "distance_km": calc.get("distance_km")})

    @app.get("/api/pdv/taxa_entrega/config")
    def api_pdv_taxa_entrega_config():
        denied = core.require_pdv_key()
        if denied is not None:
            return denied

        published = core.read_catalogo_publicado(_ctx())
        ui = published.get("ui") if isinstance(published, dict) else {}
        cfg = service.get_delivery_fee_config_from_ui(ui)
        return jsonify({"ok": True, "enabled": service.is_delivery_fee_enabled(ui), "config": cfg})

    @app.post("/api/pdv/taxa_entrega/config")
    def api_pdv_taxa_entrega_set_config():
        denied = core.require_pdv_key()
        if denied is not None:
            return denied

        body = request.get_json(silent=True)
        if body is None:
            body = {}
        if not isinstance(body, dict):
            return jsonify({"error": "json_invalido"}), 400

        published = core.read_catalogo_publicado(_ctx())
        if not isinstance(published, dict):
            published = {"categorias": [], "produtos": [], "ui": {}}

        ui = published.get("ui") if isinstance(published.get("ui"), dict) else {}
        ui2: dict[str, Any] = dict(ui)

        cfg = ui2.get("deliveryFee")
        if not isinstance(cfg, dict):
            cfg = {}
        cfg2 = dict(cfg)

        # Aceita payload tanto em formato novo quanto legado.
        if "enabled" in body:
            cfg2["enabled"] = bool(body.get("enabled"))
        if "origin_maps_url" in body or "deliveryFeeOriginMapsUrl" in body:
            cfg2["origin_maps_url"] = str(body.get("origin_maps_url") or body.get("deliveryFeeOriginMapsUrl") or "").strip() or None
        if "base" in body or "deliveryFeeBase" in body:
            cfg2["base"] = body.get("base") if "base" in body else body.get("deliveryFeeBase")
        if "per_km" in body or "deliveryFeePerKm" in body:
            cfg2["per_km"] = body.get("per_km") if "per_km" in body else body.get("deliveryFeePerKm")
        if "min" in body or "deliveryFeeMin" in body:
            cfg2["min"] = body.get("min") if "min" in body else body.get("deliveryFeeMin")
        if "max" in body or "deliveryFeeMax" in body:
            cfg2["max"] = body.get("max") if "max" in body else body.get("deliveryFeeMax")

        # Normalização básica para não salvar strings vazias.
        if cfg2.get("origin_maps_url") is not None and not str(cfg2.get("origin_maps_url") or "").strip():
            cfg2["origin_maps_url"] = None

        ui2["deliveryFee"] = cfg2
        published2 = dict(published)
        published2["ui"] = ui2
        core.save_catalogo_publicado(ctx=_ctx(), record=published2)
        return jsonify({"ok": True, "enabled": service.is_delivery_fee_enabled(ui2), "config": service.get_delivery_fee_config_from_ui(ui2)})

    def _set_enabled(enabled: bool):
        denied = core.require_pdv_key()
        if denied is not None:
            return denied

        published = core.read_catalogo_publicado(_ctx())
        if not isinstance(published, dict):
            published = {"categorias": [], "produtos": [], "ui": {}}

        ui = published.get("ui") if isinstance(published.get("ui"), dict) else {}
        ui2: dict[str, Any] = dict(ui)

        cfg = ui2.get("deliveryFee")
        if not isinstance(cfg, dict):
            cfg = {}
        cfg2 = dict(cfg)
        cfg2["enabled"] = bool(enabled)
        ui2["deliveryFee"] = cfg2

        published2 = dict(published)
        published2["ui"] = ui2
        core.save_catalogo_publicado(ctx=_ctx(), record=published2)
        return jsonify({"ok": True, "enabled": bool(enabled)})

    @app.post("/api/pdv/taxa_entrega/habilitar")
    def api_pdv_taxa_entrega_habilitar():
        return _set_enabled(True)

    @app.post("/api/pdv/taxa_entrega/desabilitar")
    def api_pdv_taxa_entrega_desabilitar():
        return _set_enabled(False)

    # ------------------------------------------------------------------
    # ZONAS DE COBERTURA — CRUD (independente do Cardápio)
    # ------------------------------------------------------------------

    @app.get("/api/pdv/taxa_entrega/zonas")
    def api_pdv_taxa_entrega_zonas_list():
        denied = core.require_pdv_key()
        if denied is not None:
            return denied
        if not core.pg_enabled():
            return jsonify({"ok": True, "zonas": []})
        try:
            ativo_only = str(request.args.get("ativo") or "1").strip().lower() in ("1", "true", "yes")
            zonas = core.pg_store.list_taxa_entrega_zonas(ativo_only=ativo_only)
        except Exception:
            zonas = []
        return jsonify({"ok": True, "zonas": zonas})

    @app.post("/api/pdv/taxa_entrega/zonas")
    def api_pdv_taxa_entrega_zonas_create():
        denied = core.require_pdv_key()
        if denied is not None:
            return denied
        if not core.pg_enabled():
            return jsonify({"error": "pg_disabled"}), 500
        body = request.get_json(silent=True) or {}
        nome = str(body.get("nome") or "").strip()
        if not nome:
            return jsonify({"error": "nome_obrigatorio"}), 400
        try:
            zona = core.pg_store.create_taxa_entrega_zona(
                nome=nome,
                cidade=str(body.get("cidade") or "").strip() or None,
                taxa=float(body.get("taxa") or 0),
                gratis=bool(body.get("gratis") or False),
                poligono=body.get("poligono"),
                cor=str(body.get("cor") or "#00d4aa").strip() or "#00d4aa",
            )
        except Exception:
            return jsonify({"error": "internal_error"}), 500
        if not isinstance(zona, dict):
            return jsonify({"error": "create_failed"}), 400
        return jsonify({"ok": True, "zona": zona})

    @app.put("/api/pdv/taxa_entrega/zonas/<int:zona_id>")
    def api_pdv_taxa_entrega_zonas_update(zona_id: int):
        denied = core.require_pdv_key()
        if denied is not None:
            return denied
        if not core.pg_enabled():
            return jsonify({"error": "pg_disabled"}), 500
        body = request.get_json(silent=True) or {}
        try:
            zona = core.pg_store.update_taxa_entrega_zona(
                zona_id=int(zona_id),
                nome=body.get("nome"),
                cidade=body.get("cidade"),
                taxa=float(body["taxa"]) if "taxa" in body and body["taxa"] is not None else None,
                gratis=body.get("gratis"),
                poligono=body.get("poligono"),
                cor=body.get("cor"),
                ativo=body.get("ativo"),
            )
        except Exception:
            return jsonify({"error": "internal_error"}), 500
        if not isinstance(zona, dict):
            return jsonify({"error": "not_found"}), 404
        return jsonify({"ok": True, "zona": zona})

    @app.delete("/api/pdv/taxa_entrega/zonas/<int:zona_id>")
    def api_pdv_taxa_entrega_zonas_delete(zona_id: int):
        denied = core.require_pdv_key()
        if denied is not None:
            return denied
        if not core.pg_enabled():
            return jsonify({"error": "pg_disabled"}), 500
        try:
            deleted = core.pg_store.delete_taxa_entrega_zona(zona_id=int(zona_id))
        except Exception:
            return jsonify({"error": "internal_error"}), 500
        if not deleted:
            return jsonify({"error": "not_found"}), 404
        return jsonify({"ok": True})
