from __future__ import annotations

import os
import secrets
from pathlib import Path

from flask import Flask

from .core import build_context, init_pg_if_enabled
from .kds.routes import register_kds_routes
from .logistica.routes import register_logistica_routes
from .ops_auth.routes import register_ops_auth_routes
from .routes import register_routes
from .taxa_entrega.routes import register_taxa_entrega_routes


def create_app() -> Flask:
    ctx = build_context()

    app = Flask(
        __name__,
        static_folder=str(ctx.bundle_dir),
        static_url_path="",
    )
    app.secret_key = str(os.environ.get("CARDAPIO_SECRET_KEY") or os.environ.get("SECRET_KEY") or "").strip() or secrets.token_urlsafe(32)
    app.config["MAX_CONTENT_LENGTH"] = int(os.environ.get("MAX_CONTENT_LENGTH") or (12 * 1024 * 1024))
    app.config["CARDAPIO_CTX"] = ctx

    init_pg_if_enabled()
    register_routes(app)
    register_ops_auth_routes(app)
    register_kds_routes(app)
    register_logistica_routes(app)
    register_taxa_entrega_routes(app)

    return app
