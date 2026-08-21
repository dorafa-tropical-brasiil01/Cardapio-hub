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
    # ZONAS DE COBERTURA — espelha zonas da REMO, com taxas editáveis
    # ------------------------------------------------------------------

    @app.get("/api/pdv/taxa_entrega/zonas")
    def api_pdv_taxa_entrega_zonas_list():
        denied = core.require_pdv_key()
        if denied is not None:
            return denied
        if not core.pg_enabled():
            return jsonify({"ok": True, "zonas": []})
        try:
            zonas = core.pg_store.list_taxa_entrega_zonas(ativo_only=False)
        except Exception:
            zonas = []
        # Não expõe polígono para o PDV — é dado interno do sistema
        safe = []
        for z in zonas:
            safe.append({
                "id": z.get("id"),
                "nome": z.get("nome"),
                "cidade": z.get("cidade"),
                "taxa": z.get("taxa"),
                "gratis": z.get("gratis"),
                "cor": z.get("cor"),
                "ativo": z.get("ativo"),
            })
        return jsonify({"ok": True, "zonas": safe})

    @app.post("/api/pdv/taxa_entrega/zonas/importar_remo")
    def api_pdv_taxa_entrega_zonas_importar_remo():
        """Importa zonas da REMO para uma cidade, preservando taxas/grátis já editados."""
        denied = core.require_pdv_key()
        if denied is not None:
            return denied
        if not core.pg_enabled():
            return jsonify({"error": "pg_disabled"}), 500
        body = request.get_json(silent=True) or {}
        cidade = str(body.get("cidade") or "").strip()
        if not cidade:
            return jsonify({"error": "cidade_obrigatoria"}), 400

        # 1. Buscar zonas da REMO
        remo_url = str(core.central_logistica_webhook_url() or "").strip().rstrip("/")
        remo_key = str(core.central_logistica_api_key() or "").strip()
        if not remo_url or not remo_key:
            return jsonify({"error": "remo_nao_configurada"}), 500

        import urllib.parse as _up
        import urllib.request as _ur
        import json as _json

        qs = _up.urlencode({"cidade": cidade})
        url = f"{remo_url}/api/v1/zonas?{qs}"
        req = _ur.Request(url, headers={"x-api-key": remo_key, "User-Agent": "Cardapio/1.0"})
        try:
            with _ur.urlopen(req, timeout=15) as resp:
                data = _json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            return jsonify({"error": "remo_indisponivel", "detail": str(e)}), 502

        remo_zonas = data.get("zonas") if isinstance(data, dict) else None
        if not isinstance(remo_zonas, list):
            return jsonify({"error": "remo_resposta_invalida"}), 502

        # 2. Buscar zonas locais já cadastradas (para preservar taxa/grátis editados)
        try:
            locais = core.pg_store.list_taxa_entrega_zonas(ativo_only=False)
        except Exception:
            locais = []
        locais_by_nome = {str(z.get("nome") or "").strip().lower(): z for z in locais if isinstance(z, dict)}

        importados = 0
        atualizados = 0
        for rz in remo_zonas:
            if not isinstance(rz, dict):
                continue
            nome = str(rz.get("nome") or "").strip()
            if not nome:
                continue
            poligono = rz.get("poligono")
            cor = str(rz.get("cor") or "#00d4aa").strip() or "#00d4aa"
            existente = locais_by_nome.get(nome.lower())
            if existente:
                # Preserva taxa e grátis editados localmente; atualiza só polígono/cor
                try:
                    core.pg_store.update_taxa_entrega_zona(
                        zona_id=int(existente.get("id")),
                        poligono=poligono,
                        cor=cor,
                    )
                    atualizados += 1
                except Exception:
                    pass
            else:
                # Cria nova zona com a taxa da REMO
                try:
                    core.pg_store.create_taxa_entrega_zona(
                        nome=nome,
                        cidade=cidade,
                        taxa=float(rz.get("taxa") or 0),
                        gratis=False,
                        poligono=poligono,
                        cor=cor,
                    )
                    importados += 1
                except Exception:
                    pass

        return jsonify({
            "ok": True,
            "cidade": cidade,
            "importados": importados,
            "atualizados": atualizados,
            "total_remo": len(remo_zonas),
        })

    @app.put("/api/pdv/taxa_entrega/zonas/<int:zona_id>")
    def api_pdv_taxa_entrega_zonas_update(zona_id: int):
        """Atualiza apenas taxa, grátis e ativo (operador não edita polígono)."""
        denied = core.require_pdv_key()
        if denied is not None:
            return denied
        if not core.pg_enabled():
            return jsonify({"error": "pg_disabled"}), 500
        body = request.get_json(silent=True) or {}
        try:
            taxa_val = body.get("taxa")
            zona = core.pg_store.update_taxa_entrega_zona(
                zona_id=int(zona_id),
                taxa=float(taxa_val) if taxa_val is not None else None,
                gratis=body.get("gratis"),
                ativo=body.get("ativo"),
            )
        except Exception:
            return jsonify({"error": "internal_error"}), 500
        if not isinstance(zona, dict):
            return jsonify({"error": "not_found"}), 404
        # Não expõe polígono
        return jsonify({
            "ok": True,
            "zona": {
                "id": zona.get("id"),
                "nome": zona.get("nome"),
                "cidade": zona.get("cidade"),
                "taxa": zona.get("taxa"),
                "gratis": zona.get("gratis"),
                "cor": zona.get("cor"),
                "ativo": zona.get("ativo"),
            },
        })

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
