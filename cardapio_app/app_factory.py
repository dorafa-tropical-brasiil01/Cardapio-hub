from __future__ import annotations

import os
from pathlib import Path

from flask import Flask

from .core import build_context, init_pg_if_enabled
from .routes import register_routes


def create_app() -> Flask:
    ctx = build_context()

    app = Flask(
        __name__,
        static_folder=str(ctx.bundle_dir),
        static_url_path="",
    )
    app.config["MAX_CONTENT_LENGTH"] = int(os.environ.get("MAX_CONTENT_LENGTH") or (12 * 1024 * 1024))
    app.config["CARDAPIO_CTX"] = ctx

    init_pg_if_enabled()
    register_routes(app)

    return app
