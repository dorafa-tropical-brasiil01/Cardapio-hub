from __future__ import annotations

from flask import Flask, make_response

from ..ops_auth.routes import require_ops_login


def register_logistica_routes(app: Flask) -> None:
    @app.get("/entregas")
    def entregas_page():
        denied = require_ops_login(role="LOGISTICA")
        if denied is not None:
            return denied

        html = """<!doctype html>
<html lang=\"pt-BR\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>Entregas</title>
  <style>
    body{font-family:Arial,Helvetica,sans-serif;margin:0;padding:14px;background:#0b0b0c;color:#fff}
    .wrap{max-width:720px;margin:0 auto}
    .card{background:#151518;border:1px solid rgba(255,255,255,0.08);border-radius:14px;padding:12px;margin:10px 0}
    h1{font-size:18px;margin:0}
    .muted{opacity:.75}
    .list{margin-top:10px;display:flex;flex-direction:column;gap:10px}
    .item{padding:12px;border:1px solid rgba(255,255,255,0.08);border-radius:12px;background:#0f0f12}
    button{font-size:16px;padding:10px 12px;border-radius:12px;border:0;background:#fff;color:#111;font-weight:800}
    button.secondary{background:#2a2a2f;color:#fff;font-weight:700}
  </style>
</head>
<body>
  <div class=\"wrap\">
    <div class=\"card\" style=\"display:flex;justify-content:space-between;align-items:center;\">
      <div>
        <h1>Entregas</h1>
        <div class=\"muted\" style=\"font-size:13px\">Fila e corridas (em implantação)</div>
      </div>
      <form method=\"post\" action=\"/ops/logout\"><button class=\"secondary\" type=\"submit\">Sair</button></form>
    </div>

    <div class=\"card\">
      <div class=\"muted\">Nesta etapa, a tela já existe e está protegida por login. A lógica de aceitar pedidos/corrida será conectada na próxima etapa.</div>
      <div class=\"list\">
        <div class=\"item\">
          <div style=\"font-weight:900\">Pedidos prontos para entrega</div>
          <div class=\"muted\">(lista será preenchida via API)</div>
          <div style=\"margin-top:10px\"><button type=\"button\">Aceitar</button></div>
        </div>
      </div>
    </div>

    <div class=\"card\">
      <div style=\"font-weight:900\">Minha Corrida</div>
      <div class=\"muted\">(em implantação)</div>
      <div style=\"margin-top:10px;display:flex;gap:10px;flex-wrap:wrap\">
        <button type=\"button\" class=\"secondary\">Iniciar Corrida</button>
        <button type=\"button\" class=\"secondary\">Finalizar Corrida</button>
      </div>
    </div>
  </div>
</body>
</html>"""
        resp = make_response(html, 200)
        resp.headers["Cache-Control"] = "no-store"
        return resp
