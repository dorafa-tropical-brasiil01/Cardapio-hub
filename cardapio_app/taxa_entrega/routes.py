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
        core.save_catalogo_publicado(_ctx(), published2)
        return jsonify({"ok": True, "enabled": bool(enabled)})

    @app.post("/api/pdv/taxa_entrega/habilitar")
    def api_pdv_taxa_entrega_habilitar():
        return _set_enabled(True)

    @app.post("/api/pdv/taxa_entrega/desabilitar")
    def api_pdv_taxa_entrega_desabilitar():
        return _set_enabled(False)
