from __future__ import annotations

import logging
import os
import secrets
import sys
from pathlib import Path

from flask import Flask

from .core import build_context, init_pg_if_enabled
from .kds.routes import register_kds_routes
from .logistica.routes import register_logistica_routes
from .logistica.service import iniciar_processador_background
from .ops_auth.routes import register_ops_auth_routes
from .pagamento_online.service import iniciar_scheduler_background
from .routes import register_routes
from .taxa_entrega.routes import register_taxa_entrega_routes


def create_app() -> Flask:
    ctx = build_context()

    # Configurar logging para Railway (stdout)
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(name)s: %(message)s')
    handler.setFormatter(formatter)
    
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(handler)

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

    try:
        iniciar_processador_background(intervalo_segundos=30)
    except Exception:
        pass

    # Scheduler de pagamentos: expiração local (Bloco 4.3b) + reconciliação
    # Cardápio → PSP (Bloco 3.7). Thread daemon única.
    try:
        iniciar_scheduler_background(
            intervalo_expiracao_segundos=60,
            intervalo_reconciliacao_segundos=300,
        )
    except Exception:
        pass

    return app
