from __future__ import annotations

from flask import Flask, make_response, request

from ..ops_auth.routes import require_ops_login


def register_kds_routes(app: Flask) -> None:
    @app.get("/cozinha")
    def cozinha_page():
        denied = require_ops_login(role="KDS")
        if denied is not None:
            return denied

        html = """<!doctype html>
<html lang=\"pt-BR\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>Cozinha</title>
  <style>
    body{font-family:Arial,Helvetica,sans-serif;margin:0;padding:14px;background:#0b0b0c;color:#fff}
    .wrap{max-width:520px;margin:0 auto}
    .card{background:#151518;border:1px solid rgba(255,255,255,0.08);border-radius:14px;padding:12px;margin:10px 0}
    .btns{display:flex;gap:10px;flex-wrap:wrap;margin-top:10px}
    button{flex:1;min-width:140px;font-size:16px;padding:12px;border-radius:12px;border:0;background:#fff;color:#111;font-weight:800}
    button.secondary{background:#2a2a2f;color:#fff;font-weight:700}
    .muted{opacity:.75}
  </style>
</head>
<body>
  <div class=\"wrap\">
    <div class=\"card\">
      <div style=\"display:flex;justify-content:space-between;align-items:center;\">
        <div>
          <div style=\"font-weight:900;font-size:18px\">Cozinha</div>
          <div class=\"muted\" style=\"font-size:13px\">Painel (em implantação)</div>
        </div>
        <form method=\"post\" action=\"/ops/logout\"><button class=\"secondary\" type=\"submit\" style=\"min-width:auto\">Sair</button></form>
      </div>
    </div>

    <div class=\"card\" id=\"pedido\">
      <div class=\"muted\">Fila e ações serão conectadas ao backend na próxima etapa.</div>
      <div class=\"btns\">
        <button type=\"button\">Preparar Pedido</button>
        <button type=\"button\" class=\"secondary\">Pedido Pronto</button>
        <button type=\"button\" class=\"secondary\">Próximo Pedido</button>
      </div>
    </div>
  </div>
</body>
</html>"""
        resp = make_response(html, 200)
        resp.headers["Cache-Control"] = "no-store"
        return resp
